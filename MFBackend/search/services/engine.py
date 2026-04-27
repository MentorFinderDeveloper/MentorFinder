from search.serializers import MentorSerializer, PaperSerializer
from dataset.models import Mentor, Paper
from django.db.models import Q, Subquery


def _order_papers(papers, sort_mode: str):
    if sort_mode == "early":
        return papers.order_by("publish_date", "id")
    if sort_mode == "late":
        return papers.order_by("-publish_date", "-id")
    return papers


def _visible_mentors(user):
    if user is None:
        return Mentor.objects.filter(owner__isnull=True)
    if getattr(user, "role", "") == "admin":
        return Mentor.objects.all()
    return Mentor.objects.filter(Q(owner__isnull=True) | Q(owner_id=user.id))


def _collect_mentor_paper_ids(mentors) -> list[int]:
    paper_ids: set[int] = set()
    for mentor in mentors.iterator(chunk_size=200):
        paper_ids.update(mentor.get_paper_id_list())
    return list(paper_ids)


def search_mentors(keyword: str, user=None) -> list[dict]:
    mentors = _visible_mentors(user).filter(
        Q(Chinese_name__iexact=keyword) |
        Q(English_name__iexact=keyword) |
        Q(research_direction__iexact=keyword)
    ).distinct()

    return MentorSerializer(mentors, many=True).data

def search_mentors_fuzzy(keyword: str, user=None) -> list[dict]:
    mentors = _visible_mentors(user).filter(
        Q(Chinese_name__icontains=keyword) |
        Q(English_name__icontains=keyword) |
        Q(research_direction__icontains=keyword)
    ).distinct()

    return MentorSerializer(mentors, many=True).data


def search_papers(keyword: str, user=None, sort_mode: str = "default") -> list[dict]:
    # accurate search
    
    # keyword is title
    papers = Paper.objects.filter(Q(title__iexact=keyword) | Q(subjects__iexact=keyword)).distinct()

    # keyword is mentor name or research direction
    # (assume that a mentor's name or research direction is not the title of any paper)
    if not papers.exists():
        mentor_ids: list[int] = []
        for mentor in _visible_mentors(user).filter(
            Q(Chinese_name__iexact=keyword) |
            Q(English_name__iexact=keyword) |
            Q(research_direction__iexact=keyword)
            ):
            mentor_ids.extend(mentor.get_paper_id_list())

        if mentor_ids:
            papers = Paper.objects.filter(id__in=mentor_ids).distinct()

    ordered_papers = _order_papers(papers, sort_mode)
    return PaperSerializer(ordered_papers, many=True).data

def search_papers_fuzzy(keyword: str, user=None, sort_mode: str = "default") -> list[dict]:
    # fuzzy search

    # keyword is title (use subquery instead of collecting IDs in Python)
    title_match_ids_subquery = (
        Paper.objects
        .filter(title__icontains=keyword)
        .values("id")
    )

    # keyword is mentor name or research direction
    mentor_ids = _collect_mentor_paper_ids(_visible_mentors(user).filter(
        Q(Chinese_name__icontains=keyword) |
        Q(English_name__icontains=keyword) |
        Q(research_direction__icontains=keyword)
        ))

    paper_filters = Q(id__in=Subquery(title_match_ids_subquery))
    if mentor_ids:
        paper_filters |= Q(id__in=mentor_ids)

    papers = Paper.objects.filter(paper_filters).distinct()
    ordered_papers = _order_papers(papers, sort_mode)

    return PaperSerializer(ordered_papers, many=True).data
