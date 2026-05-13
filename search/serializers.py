from django.db.models import Q
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
        author_list = obj.get_author_list() # 所有作者列表
        if not author_list:
            return []

        bound_mentor_ids = obj.get_mentor_id_list() # 已绑定的导师ID列表
        if bound_mentor_ids: # mentor_ids 字段有效，直接查询这些导师的姓名（性能较好）
            mentors = Mentor.objects.filter(id__in=bound_mentor_ids).only("id", "Chinese_name", "English_name")
        else: # mentor_ids 字段缺失或为空字符串，尝试通过作者名单匹配导师（性能较差）
            author_match_query = Q()
            for author_name in author_list:
                author_match_query |= Q(Chinese_name__iexact=author_name) | Q(English_name__iexact=author_name)
            mentors = Mentor.objects.filter(author_match_query).only("id", "Chinese_name", "English_name")

        # 仅基于已绑定的导师建立索引
        mentor_id_by_name = {}
        for mentor in mentors:
            chinese_name = (mentor.Chinese_name or "").strip().lower()
            english_name = (mentor.English_name or "").strip().lower()

            if chinese_name:
                mentor_id_by_name.setdefault(chinese_name, mentor.pk)
            if english_name:
                mentor_id_by_name.setdefault(english_name, mentor.pk)

        return [mentor_id_by_name.get(author_name.lower(), 0) for author_name in author_list]
