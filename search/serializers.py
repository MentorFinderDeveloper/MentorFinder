# search/serializers.py
from rest_framework import serializers
from dataset.models import Mentor, Paper

class MentorSerializer(serializers.ModelSerializer):
    paperTitles = serializers.SerializerMethodField()
    
    class Meta:
        model = Mentor
        fields = ['id', 'name', 'research_direction', 'email', 'profile', 'paperTitles']
        
    def get_paperTitles(self, obj):
        return [paper.title for paper in obj.papers.all()]

class PaperSerializer(serializers.ModelSerializer):
    
    mentorNames = serializers.SerializerMethodField()

    class Meta:
        model = Paper
        fields = ['id', 'title', 'abstract', 'publish_date', 'mentorNames']

    def get_mentorNames(self, obj):
        return [mentor.name for mentor in obj.mentors.all()]