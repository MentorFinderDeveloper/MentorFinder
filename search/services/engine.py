from search.serializers import MentorSerializer, PaperSerializer
from dataset.models import Mentor, Paper
from django.db.models import Q

def search_mentors(keyword: str) -> list[dict]:
    # keyword is promised to be non-empty by the caller
    
    mentors = Mentor.objects.filter(
        Q(name__iexact=keyword) |
        Q(research_direction__iexact=keyword)
    ).prefetch_related('papers').distinct()
    
    mentor_serializer = MentorSerializer(mentors, many=True)
    
    return mentor_serializer.data


def search_papers(keyword: str) -> list[dict]:
    # keyword is promised to be non-empty by the caller
    
    papers = Paper.objects.filter(
        Q(title__iexact=keyword) |
        Q(mentors__name__iexact=keyword) |
        Q(mentors__research_direction__iexact=keyword)
    ).prefetch_related('mentors').distinct()

    return PaperSerializer(papers, many=True).data
