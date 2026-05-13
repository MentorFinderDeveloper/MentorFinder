import re

from search.serializers import MentorSerializer, PaperSerializer
from dataset.models import Mentor, Paper
from django.db.models import Q, Subquery


DEFAULT_SEARCH_PAGE = 1
DEFAULT_SEARCH_PAGE_SIZE = 10


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


def _mentor_fuzzy_query(keyword: str) -> Q:
    query = Q(Chinese_name__icontains=keyword) | Q(research_direction__icontains=keyword)
    for variant in _name_variants(keyword):
        query |= Q(English_name__icontains=variant)
    return query


def _mentor_exact_query(keyword: str) -> Q:
    query = Q(Chinese_name__iexact=keyword) | Q(research_direction__iexact=keyword)
    for variant in _name_variants(keyword):
        query |= Q(English_name__iexact=variant)
    return query


def _order_papers(papers, sort_mode: str):
    if sort_mode == "early":
        return papers.order_by("publish_date", "id")
    if sort_mode == "late":
        return papers.order_by("-publish_date", "-id")
    return papers


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


def _collect_mentor_paper_ids(mentors) -> list[int]:
    paper_ids: set[int] = set()
    for mentor in mentors.iterator(chunk_size=200):
        paper_ids.update(mentor.get_paper_id_list())
    return list(paper_ids)


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

    if fuzzy:
        return _visible_mentors(user, visibility=visibility).filter(_mentor_fuzzy_query(keyword)).distinct()

    return _visible_mentors(user, visibility=visibility).filter(_mentor_exact_query(keyword)).distinct()


def _search_papers_exact_queryset(keyword: str, user=None):
    if keyword.strip() == "":
        return Paper.objects.all().distinct()

    # keyword is title
    papers = Paper.objects.filter(Q(title__iexact=keyword) | Q(subjects__iexact=keyword)).distinct()

    # keyword is mentor name or research direction
    # (assume that a mentor's name or research direction is not the title of any paper)
    if not papers.exists():
        mentor_ids: list[int] = []
        for mentor in _visible_mentors(user).filter(_mentor_exact_query(keyword)):
            mentor_ids.extend(mentor.get_paper_id_list())

        if mentor_ids:
            papers = Paper.objects.filter(id__in=mentor_ids).distinct()

    return papers


def _search_papers_fuzzy_queryset(keyword: str, user=None):
    if keyword.strip() == "":
        return Paper.objects.all().distinct()

    # keyword is title (use subquery instead of collecting IDs in Python)
    title_match_ids_subquery = (
        Paper.objects
        .filter(title__icontains=keyword)
        .values("id")
    )

    # keyword is mentor name or research direction
    mentor_ids = _collect_mentor_paper_ids(_visible_mentors(user).filter(_mentor_fuzzy_query(keyword)))

    paper_filters = Q(id__in=Subquery(title_match_ids_subquery))
    if mentor_ids:
        paper_filters |= Q(id__in=mentor_ids)

    return Paper.objects.filter(paper_filters).distinct()


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
    ordered_papers = _order_papers(papers, sort_mode)
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
    ordered_papers = _order_papers(papers, sort_mode)

    return [dict(item) for item in PaperSerializer(ordered_papers, many=True).data]
