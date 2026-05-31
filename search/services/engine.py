import re

from search.serializers import MentorSerializer, PaperSerializer
from dataset.models import Mentor
from dataset.services.paper_visibility import (
    collect_mentor_paper_ids as _collect_mentor_paper_ids,
    hidden_private_paper_ids as _hidden_private_paper_ids,
    visible_papers as _visible_papers,
)
from django.db.models import Case, IntegerField, Q, Value, When


DEFAULT_SEARCH_PAGE = 1
DEFAULT_SEARCH_PAGE_SIZE = 10
FUZZY_MIN_TOKEN_LENGTH = 2


def _name_variants(name: str) -> list[str]:
    normalized = " ".join(str(name).lower().strip().replace(",", " ").split())
    if normalized == "":
        return []

    variants = [normalized]
    parts = [part for part in re.split(r"[,\s]+", normalized) if part]
    if len(parts) == 2:
        variants.append(f"{parts[1]} {parts[0]}")
        variants.append(f"{parts[1]}, {parts[0]}")

    unique_variants = []
    seen = set()
    for variant in variants:
        if variant in seen:
            continue
        seen.add(variant)
        unique_variants.append(variant)
    return unique_variants


def _split_search_text(value: str) -> list[str]:
    return [
        token.strip()
        for token in re.split(r"[\s,，;；、]+", str(value).strip())
        if token.strip()
    ]


def _keyword_subterms(keyword: str) -> list[str]:
    terms = [keyword.strip()]
    split_terms = _split_search_text(keyword)
    if len(split_terms) > 1:
        terms.extend(
            term
            for term in split_terms
            if len(term) >= FUZZY_MIN_TOKEN_LENGTH or re.search(r"[\u4e00-\u9fff]", term)
        )

    unique_terms = []
    seen = set()
    for term in terms:
        normalized = term.lower()
        if term == "" or normalized in seen:
            continue
        seen.add(normalized)
        unique_terms.append(term)
    return unique_terms


def _split_keyword_logic(keyword: str) -> list[list[str]]:
    normalized_keyword = keyword.strip()
    if normalized_keyword == "":
        return []

    or_groups = [segment.strip() for segment in re.split(r"\s*(?:或|\|\|?)\s*", normalized_keyword) if segment.strip() != ""]
    if not or_groups:
        return [[normalized_keyword]]

    logic_groups: list[list[str]] = []
    for group in or_groups:
        and_terms = [term.strip() for term in re.split(r"\s*(?:且|&&?)\s*", group) if term.strip() != ""]
        logic_groups.append(and_terms if and_terms else [group])

    return logic_groups


class _KeywordLogicParseError(ValueError):
    pass


def _tokenize_keyword_logic(keyword: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    term_chars: list[str] = []

    def flush_term() -> None:
        if not term_chars:
            return
        term = "".join(term_chars).strip()
        term_chars.clear()
        if term != "":
            tokens.append(("TERM", term))

    index = 0
    while index < len(keyword):
        if keyword.startswith("&&", index):
            flush_term()
            tokens.append(("AND", "&&"))
            index += 2
            continue
        if keyword.startswith("||", index):
            flush_term()
            tokens.append(("OR", "||"))
            index += 2
            continue

        char = keyword[index]
        if char in "(（":
            flush_term()
            tokens.append(("LPAREN", char))
            index += 1
            continue
        if char in ")）":
            flush_term()
            tokens.append(("RPAREN", char))
            index += 1
            continue
        if char == "&":
            flush_term()
            tokens.append(("AND", char))
            index += 1
            continue
        if char == "|":
            flush_term()
            tokens.append(("OR", char))
            index += 1
            continue
        if char == "且":
            flush_term()
            tokens.append(("AND", char))
            index += 1
            continue
        if char == "或":
            flush_term()
            tokens.append(("OR", char))
            index += 1
            continue

        term_chars.append(char)
        index += 1

    flush_term()
    return tokens


def _build_flat_logic_query(keyword: str, build_term_query) -> Q:
    logic_groups = _split_keyword_logic(keyword)
    if not logic_groups:
        return Q()

    logic_query = Q()
    for group in logic_groups:
        group_query = Q()
        first_term = True
        for term in group:
            term_query = build_term_query(term)
            if first_term:
                group_query = term_query
                first_term = False
            else:
                group_query &= term_query
        logic_query |= group_query

    return logic_query


def _build_logic_query(keyword: str, build_term_query) -> Q:
    tokens = _tokenize_keyword_logic(keyword.strip())
    if not tokens:
        return Q()

    position = 0

    def peek() -> tuple[str, str] | None:
        return tokens[position] if position < len(tokens) else None

    def consume(expected_type: str | None = None) -> tuple[str, str]:
        nonlocal position
        token = peek()
        if token is None:
            raise _KeywordLogicParseError()
        if expected_type is not None and token[0] != expected_type:
            raise _KeywordLogicParseError()
        position += 1
        return token

    def parse_primary() -> Q:
        token = peek()
        if token is None:
            raise _KeywordLogicParseError()

        token_type, token_value = token
        if token_type == "TERM":
            consume("TERM")
            return build_term_query(token_value)
        if token_type == "LPAREN":
            consume("LPAREN")
            expression = parse_or()
            if peek() is None or peek()[0] != "RPAREN":
                raise _KeywordLogicParseError()
            consume("RPAREN")
            return expression

        raise _KeywordLogicParseError()

    def parse_and() -> Q:
        expression = parse_primary()
        while peek() is not None and peek()[0] == "AND":
            consume("AND")
            expression &= parse_primary()
        return expression

    def parse_or() -> Q:
        expression = parse_and()
        while peek() is not None and peek()[0] == "OR":
            consume("OR")
            expression |= parse_and()
        return expression

    try:
        logic_query = parse_or()
        if position != len(tokens):
            raise _KeywordLogicParseError()
        return logic_query
    except _KeywordLogicParseError:
        return _build_flat_logic_query(keyword, build_term_query)


def _extract_logic_terms(keyword: str) -> list[str]:
    tokens = _tokenize_keyword_logic(keyword.strip())
    terms = [token_value for token_type, token_value in tokens if token_type == "TERM"]
    if not terms and keyword.strip() != "":
        terms = [keyword.strip()]

    unique_terms = []
    seen = set()
    for term in terms:
        normalized = term.strip().lower()
        if normalized == "" or normalized in seen:
            continue
        seen.add(normalized)
        unique_terms.append(term.strip())
    return unique_terms


def _or_icontains(fields: list[str], term: str) -> Q:
    query = Q()
    for field in fields:
        query |= Q(**{f"{field}__icontains": term})
    return query


def _and_tokenized_icontains(fields: list[str], term: str) -> Q:
    subterms = _keyword_subterms(term)
    if len(subterms) <= 1:
        return _or_icontains(fields, term)

    query = Q()
    first_token = True
    for subterm in subterms[1:]:
        token_query = _or_icontains(fields, subterm)
        if first_token:
            query = token_query
            first_token = False
        else:
            query &= token_query

    return query


def _score_case(query: Q, score: int):
    return Case(
        When(query, then=Value(score)),
        default=Value(0),
        output_field=IntegerField(),
    )


def _sum_score_cases(cases):
    score = Value(0, output_field=IntegerField())
    for case in cases:
        score = score + case
    return score


def _mentor_fuzzy_query(keyword: str) -> Q:
    searchable_fields = ["Chinese_name", "English_name", "research_direction", "email", "profile"]
    query = _or_icontains(searchable_fields, keyword) | _and_tokenized_icontains(searchable_fields, keyword)
    for variant in _name_variants(keyword):
        query |= Q(English_name__icontains=variant)
    return query


def _mentor_exact_query(keyword: str) -> Q:
    query = Q(Chinese_name__iexact=keyword) | Q(research_direction__iexact=keyword)
    for variant in _name_variants(keyword):
        query |= Q(English_name__iexact=variant)
    return query


def _paper_exact_term_query(term: str, user=None) -> Q:
    query = Q(title__iexact=term) | Q(subjects__icontains=term)

    mentor_ids: list[int] = []
    for mentor in _visible_mentors(user).filter(_mentor_exact_query(term)):
        mentor_ids.extend(mentor.get_paper_id_list())
    if mentor_ids:
        query |= Q(id__in=mentor_ids)

    return query


def _paper_fuzzy_term_query(term: str, user=None) -> Q:
    searchable_fields = ["title", "abstract", "tldr", "subjects", "author_names", "arxiv_id"]
    query = _or_icontains(searchable_fields, term) | _and_tokenized_icontains(searchable_fields, term)

    mentor_ids = _collect_mentor_paper_ids(_visible_mentors(user).filter(_mentor_fuzzy_query(term)))
    if mentor_ids:
        query |= Q(id__in=mentor_ids)

    return query


def _mentor_fuzzy_score(keyword: str):
    cases = []
    for term in _extract_logic_terms(keyword):
        cases.extend(
            [
                _score_case(Q(Chinese_name__iexact=term), 120),
                _score_case(Q(Chinese_name__istartswith=term), 80),
                _score_case(Q(Chinese_name__icontains=term), 60),
                _score_case(Q(research_direction__icontains=term), 36),
                _score_case(Q(email__icontains=term), 20),
                _score_case(Q(profile__icontains=term), 12),
            ]
        )
        for variant in _name_variants(term):
            cases.extend(
                [
                    _score_case(Q(English_name__iexact=variant), 110),
                    _score_case(Q(English_name__istartswith=variant), 70),
                    _score_case(Q(English_name__icontains=variant), 48),
                ]
            )

        for subterm in _keyword_subterms(term)[1:]:
            cases.extend(
                [
                    _score_case(Q(Chinese_name__icontains=subterm), 28),
                    _score_case(Q(English_name__icontains=subterm), 24),
                    _score_case(Q(research_direction__icontains=subterm), 18),
                    _score_case(Q(profile__icontains=subterm), 6),
                ]
            )

    return _sum_score_cases(cases)


def _paper_fuzzy_score(keyword: str, user=None):
    cases = []
    for term in _extract_logic_terms(keyword):
        cases.extend(
            [
                _score_case(Q(title__iexact=term), 150),
                _score_case(Q(title__istartswith=term), 95),
                _score_case(Q(title__icontains=term), 70),
                _score_case(Q(author_names__icontains=term), 42),
                _score_case(Q(subjects__icontains=term), 36),
                _score_case(Q(arxiv_id__icontains=term), 32),
                _score_case(Q(tldr__icontains=term), 24),
                _score_case(Q(abstract__icontains=term), 16),
            ]
        )

        mentor_paper_ids = _collect_mentor_paper_ids(_visible_mentors(user).filter(_mentor_fuzzy_query(term)))
        if mentor_paper_ids:
            cases.append(_score_case(Q(id__in=mentor_paper_ids), 50))

        for subterm in _keyword_subterms(term)[1:]:
            cases.extend(
                [
                    _score_case(Q(title__icontains=subterm), 32),
                    _score_case(Q(author_names__icontains=subterm), 18),
                    _score_case(Q(subjects__icontains=subterm), 14),
                    _score_case(Q(tldr__icontains=subterm), 10),
                    _score_case(Q(abstract__icontains=subterm), 6),
                ]
            )

    return _sum_score_cases(cases)


def _order_papers(papers, sort_mode: str):
    if sort_mode == "early":
        return papers.order_by("publish_date", "id")
    if sort_mode == "late":
        return papers.order_by("-publish_date", "-id")
    return papers


def _order_fuzzy_papers(papers, keyword: str, user=None, sort_mode: str = "default"):
    if sort_mode != "default":
        return _order_papers(papers, sort_mode)

    return (
        papers
        .annotate(search_score=_paper_fuzzy_score(keyword, user=user))
        .order_by("-search_score", "-publish_date", "-id")
    )


def _visible_mentors(user, visibility="all"):
    if user is None:
        return Mentor.objects.filter(owner__isnull=True)
    if getattr(user, "role", "") == "admin":
        base = Mentor.objects.all()
    else:
        base = Mentor.objects.filter(Q(owner__isnull=True) | Q(owner_id=user.id))

    if visibility == "mine":
        if user is None:
            return Mentor.objects.none()
        return base.filter(owner_id=user.id)
    if visibility == "public":
        return base.filter(owner__isnull=True)
    return base


def _normalize_page(page) -> int:
    try:
        normalized = int(page)
    except (TypeError, ValueError):
        return DEFAULT_SEARCH_PAGE
    return normalized if normalized > 0 else DEFAULT_SEARCH_PAGE


def _normalize_page_size(page_size) -> int:
    try:
        normalized = int(page_size)
    except (TypeError, ValueError):
        return DEFAULT_SEARCH_PAGE_SIZE
    return normalized if normalized > 0 else DEFAULT_SEARCH_PAGE_SIZE


def _paginate_queryset(queryset, page, page_size):
    normalized_page = _normalize_page(page)
    normalized_page_size = _normalize_page_size(page_size)
    total = queryset.count()
    total_pages = (total + normalized_page_size - 1) // normalized_page_size if total > 0 else 0

    if total_pages == 0:
        return queryset.none(), {
            "page": DEFAULT_SEARCH_PAGE,
            "page_size": normalized_page_size,
            "total": 0,
            "total_pages": 0,
            "has_previous": False,
            "has_next": False,
        }

    normalized_page = min(normalized_page, total_pages)
    start = (normalized_page - 1) * normalized_page_size
    end = start + normalized_page_size

    return queryset[start:end], {
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "total_pages": total_pages,
        "has_previous": normalized_page > 1,
        "has_next": normalized_page < total_pages,
    }


def search_mentors_queryset(keyword: str, user=None, fuzzy: bool = False, visibility: str = "all"):
    if keyword.strip() == "":
        return _visible_mentors(user, visibility=visibility).distinct()

    term_query_builder = _mentor_fuzzy_query if fuzzy else _mentor_exact_query
    logic_query = _build_logic_query(keyword, term_query_builder)
    mentors = _visible_mentors(user, visibility=visibility).filter(logic_query).distinct()
    if not fuzzy:
        return mentors
    return mentors.annotate(search_score=_mentor_fuzzy_score(keyword)).order_by("-search_score", "id")


def _search_papers_exact_queryset(keyword: str, user=None):
    if keyword.strip() == "":
        return _visible_papers(user).distinct()

    # Priority: if any paper title exactly matches the keyword logic, return only those.
    # Build a title-only logic query (each term matches title__iexact) and check.
    def _paper_title_exact_query(term: str) -> Q:
        return Q(title__iexact=term)

    title_logic_query = _build_logic_query(keyword, _paper_title_exact_query)
    base_papers = _visible_papers(user)
    title_qs = base_papers.filter(title_logic_query).distinct()
    if title_qs.exists():
        return title_qs

    logic_query = _build_logic_query(keyword, lambda term: _paper_exact_term_query(term, user=user))
    return base_papers.filter(logic_query).distinct()


def _search_papers_fuzzy_queryset(keyword: str, user=None):
    if keyword.strip() == "":
        return _visible_papers(user).distinct()

    logic_query = _build_logic_query(keyword, lambda term: _paper_fuzzy_term_query(term, user=user))
    return _visible_papers(user).filter(logic_query).distinct()


def search_mentors_page(keyword: str, user=None, fuzzy: bool = False, page: int = 1, page_size: int = DEFAULT_SEARCH_PAGE_SIZE, visibility: str = "all"):
    mentors = search_mentors_queryset(keyword, user=user, fuzzy=fuzzy, visibility=visibility)
    paged_queryset, pagination = _paginate_queryset(mentors, page, page_size)
    return [dict(item) for item in MentorSerializer(paged_queryset, many=True).data], pagination


def search_papers_page(
    keyword: str,
    user=None,
    search_mode: str = "exact",
    sort_mode: str = "default",
    page: int = 1,
    page_size: int = DEFAULT_SEARCH_PAGE_SIZE,
):
    papers = _search_papers_fuzzy_queryset(keyword, user=user) if search_mode == "fuzzy" else _search_papers_exact_queryset(keyword, user=user)
    ordered_papers = _order_fuzzy_papers(papers, keyword, user=user, sort_mode=sort_mode) if search_mode == "fuzzy" else _order_papers(papers, sort_mode)
    paged_queryset, pagination = _paginate_queryset(ordered_papers, page, page_size)
    return [dict(item) for item in PaperSerializer(paged_queryset, many=True).data], pagination


def search_mentors(keyword: str, user=None) -> list[dict]:
    mentors = search_mentors_queryset(keyword, user=user, fuzzy=False)

    return [dict(item) for item in MentorSerializer(mentors, many=True).data]


def search_mentors_fuzzy(keyword: str, user=None) -> list[dict]:
    mentors = search_mentors_queryset(keyword, user=user, fuzzy=True)

    return [dict(item) for item in MentorSerializer(mentors, many=True).data]


def search_papers(keyword: str, user=None, sort_mode: str = "default") -> list[dict]:
    papers = _search_papers_exact_queryset(keyword, user=user)
    ordered_papers = _order_papers(papers, sort_mode)
    return [dict(item) for item in PaperSerializer(ordered_papers, many=True).data]


def search_papers_fuzzy(keyword: str, user=None, sort_mode: str = "default") -> list[dict]:
    papers = _search_papers_fuzzy_queryset(keyword, user=user)
    ordered_papers = _order_fuzzy_papers(papers, keyword, user=user, sort_mode=sort_mode)

    return [dict(item) for item in PaperSerializer(ordered_papers, many=True).data]
