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
