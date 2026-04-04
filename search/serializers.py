from rest_framework import serializers
from dataset.models import Mentor, Paper


class MentorSerializer(serializers.ModelSerializer):
    paperTitles = serializers.SerializerMethodField()

    class Meta:
        model = Mentor
        fields = ["id", "Chinese_name", "English_name", "research_direction", "email", "profile", "paperTitles"]

    def get_paperTitles(self, obj):
        return [paper.title for paper in obj.get_papers()]


class PaperSerializer(serializers.ModelSerializer):
    mentorNames = serializers.SerializerMethodField()

    class Meta:
        model = Paper
        fields = ["id", "title", "abstract", "publish_date", "author_names", "mentorNames"]

    def get_mentorNames(self, obj):
        return obj.get_author_list()