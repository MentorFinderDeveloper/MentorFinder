import re

from django.db.models import Q
from rest_framework import serializers
from dataset.models import Mentor, Paper


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


class MentorSerializer(serializers.ModelSerializer):
    paperTitles = serializers.SerializerMethodField()
    is_private = serializers.SerializerMethodField()

    class Meta:
        model = Mentor
        fields = ["id", "Chinese_name", "English_name", "research_direction", "email", "profile", "paperTitles", "is_private"]

    def get_paperTitles(self, obj):
        return [paper.title for paper in obj.get_papers()]

    def get_is_private(self, obj):
        return obj.is_private


class PaperSerializer(serializers.ModelSerializer):
    mentorNames = serializers.SerializerMethodField()
    mentor_ids = serializers.SerializerMethodField()

    class Meta:
        model = Paper
        fields = ["id", "title", "abstract", "publish_date", "author_names", "subjects", "arxiv_id", "arxiv_url", "mentorNames", "mentor_ids"]

    def get_mentorNames(self, obj):
        return obj.get_author_list()

    def get_mentor_ids(self, obj):
        author_list = obj.get_author_list()
        if not author_list:
            return []

        bound_mentor_ids = obj.get_mentor_id_list()
        if bound_mentor_ids:
            mentors = Mentor.objects.filter(id__in=bound_mentor_ids).only("id", "Chinese_name", "English_name")
        else:
            author_match_query = Q()
            for author_name in author_list:
                for variant in _name_variants(author_name):
                    author_match_query |= Q(Chinese_name__iexact=variant) | Q(English_name__iexact=variant)
            mentors = Mentor.objects.filter(author_match_query).only("id", "Chinese_name", "English_name")

        mentor_id_by_name = {}
        for mentor in mentors:
            for variant in _name_variants(mentor.Chinese_name or ""):
                mentor_id_by_name.setdefault(variant, mentor.pk)
            for variant in _name_variants(mentor.English_name or ""):
                mentor_id_by_name.setdefault(variant, mentor.pk)

        return [next((mentor_id_by_name.get(variant) for variant in _name_variants(author_name) if variant in mentor_id_by_name), 0) for author_name in author_list]
