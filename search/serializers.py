from rest_framework import serializers
from dataset.models import Mentor, Paper


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
        return obj.get_author_mentor_ids()
