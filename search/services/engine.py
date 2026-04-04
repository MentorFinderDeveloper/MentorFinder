from search.serializers import MentorSerializer, PaperSerializer
from dataset.models import Mentor, Paper
from django.db.models import Q


def search_mentors(keyword: str) -> list[dict]:
    mentors = Mentor.objects.filter(
        Q(Chinese_name__iexact=keyword) |
        Q(English_name__iexact=keyword) |
        Q(research_direction__iexact=keyword)
    ).distinct()

    return MentorSerializer(mentors, many=True).data


def search_papers(keyword: str) -> list[dict]:
    # accurate search
    
    # keyword is title
    papers = Paper.objects.filter(title__iexact=keyword)

    # keyword is mentor name or research direction
    # (assume that a mentor's name or research direction is not the title of any paper)
    if not papers.exists():
        mentor_ids: list[int] = []
        for mentor in Mentor.objects.filter(
            Q(Chinese_name__iexact=keyword) |
            Q(English_name__iexact=keyword) |
            Q(research_direction__iexact=keyword)
            ):
            mentor_ids.extend(mentor.get_paper_id_list())

        if mentor_ids:
            papers = Paper.objects.filter(id__in=mentor_ids).distinct()

    return PaperSerializer(papers, many=True).data

def search_papers_fuzzy(keyword: str) -> list[dict]:
    # fuzzy search
    
    # keyword is title
    title_match_papers = Paper.objects.filter(title__icontains=keyword)
    title_match_ids = set(paper.id for paper in title_match_papers)
    
    # keyword is mentor name or research direction
    mentor_ids: set[int] = set()
    for mentor in Mentor.objects.filter(
        Q(Chinese_name__icontains=keyword) |
        Q(English_name__icontains=keyword) |
        Q(research_direction__icontains=keyword)
        ):
        mentor_ids.update(mentor.get_paper_id_list())

    # combine all matching paper IDs (no garantee of order)
    all_match_ids = list(set(title_match_ids | mentor_ids))
    papers = Paper.objects.filter(id__in=all_match_ids).distinct()

    return PaperSerializer(papers, many=True).data
