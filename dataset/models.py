import re

from django.conf import settings
from django.db import models


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


class Paper(models.Model):
    title = models.CharField(max_length=255, verbose_name="论文题目")
    abstract = models.TextField(blank=True, null=True, verbose_name="摘要")
    publish_date = models.DateField(blank=True, null=True, verbose_name="发表日期")
    author_names = models.TextField(blank=True, default="", verbose_name="作者名单")
    subjects = models.CharField(max_length=255, blank=True, default="", verbose_name="学科/分类")
    arxiv_id = models.CharField(max_length=64, blank=True, default="", verbose_name="arXiv ID")
    arxiv_url = models.URLField(blank=True, null=True, verbose_name="arXiv 链接")
    tldr = models.TextField(blank=True, null=True, verbose_name="一句话总结")
    mentor_ids = models.TextField(blank=True, default="", verbose_name="导师ID列表")
    class Meta:
        verbose_name = "论文"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title

    def get_author_list(self):
        if self.author_names == "":
            return []
        return [name.strip() for name in self.author_names.split(",")]

    def get_mentor_id_list(self):
        if self.mentor_ids == "":
            return []
        return [int(mid) for mid in self.mentor_ids.split(",")]

    def get_author_mentor_ids(self):
        author_list = self.get_author_list()
        if not author_list:
            return []

        bound_mentor_ids = self.get_mentor_id_list()
        if bound_mentor_ids:
            mentors = Mentor.objects.filter(id__in=bound_mentor_ids).only("id", "Chinese_name", "English_name")
        else:
            mentors = Mentor.objects.none()

        matched_ids = self._resolve_author_mentor_ids(author_list, mentors)
        if any(mentor_id == 0 for mentor_id in matched_ids):
            author_match_query = models.Q()
            for author_name in author_list:
                for variant in _name_variants(author_name):
                    author_match_query |= models.Q(Chinese_name__iexact=variant) | models.Q(English_name__iexact=variant)
            fallback_mentors = Mentor.objects.filter(author_match_query).only("id", "Chinese_name", "English_name") if author_match_query else Mentor.objects.none()
            matched_ids = self._resolve_author_mentor_ids(author_list, fallback_mentors, matched_ids)

        return matched_ids

    @staticmethod
    def _resolve_author_mentor_ids(author_list, mentors, base_matches=None):
        mentor_id_by_name = {}
        for mentor in mentors:
            for variant in _name_variants(mentor.Chinese_name or ""):
                mentor_id_by_name.setdefault(variant, mentor.pk)
            for variant in _name_variants(mentor.English_name or ""):
                mentor_id_by_name.setdefault(variant, mentor.pk)

        resolved_matches = list(base_matches) if base_matches is not None else [0] * len(author_list)
        for idx, author_name in enumerate(author_list):
            if idx < len(resolved_matches) and resolved_matches[idx] > 0:
                continue
            mentor_id = next(
                (mentor_id_by_name.get(variant) for variant in _name_variants(author_name) if variant in mentor_id_by_name),
                0,
            )
            if idx < len(resolved_matches):
                resolved_matches[idx] = mentor_id
            else:
                resolved_matches.append(mentor_id)

        return resolved_matches

    def set_mentor_id_list(self, id_list):
        unique_ids = []
        seen_ids = set()
        for mentor_id in id_list:
            if mentor_id in seen_ids:
                continue
            seen_ids.add(mentor_id)
            unique_ids.append(mentor_id)
        self.mentor_ids = ",".join(str(mid) for mid in unique_ids)

    def add_mentor(self, mentor_id):
        mentor_id_list = self.get_mentor_id_list()
        if mentor_id in mentor_id_list:
            return
        mentor_id_list.append(mentor_id)
        self.set_mentor_id_list(mentor_id_list)
        self.save(update_fields=["mentor_ids"])

    def bind_to_mentors_by_authors(self):
        matched_mentor_ids = []

        # 1. 获取原作者列表，并生成一个小写的作者列表，方便后续不区分大小写比对
        author_list = self.get_author_list()
        lower_authors = [author.lower() for author in author_list]

        for mentor in Mentor.objects.all():
            match_found = False

            # 2. 检查中文名是否匹配（中文名通常格式固定，直接精确匹配即可）
            if mentor.Chinese_name in author_list:
                match_found = True

            # 3. 检查英文名是否匹配（需要处理大小写和颠倒顺序）
            elif mentor.English_name:
                eng_name = mentor.English_name.lower().strip()
                name_parts = eng_name.split()

                # 构建可能的英文名格式列表
                possible_names = [eng_name] # 正常格式: "wei xue"
                if len(name_parts) == 2:
                    # 如果英文名是两个词，加入颠倒后的格式
                    possible_names.append(f"{name_parts[1]} {name_parts[0]}")  # "xue wei"
                    possible_names.append(f"{name_parts[1]}, {name_parts[0]}") # "xue, wei"

                # 只要上述任意一种格式，包含在论文作者名单的某一个作者名中，即视为匹配
                for author in lower_authors:
                    if any(possible_name in author for possible_name in possible_names):
                        match_found = True
                        break

            # 4. 如果找到匹配，执行绑定
            if match_found:
                paper_ids = mentor.get_paper_id_list()
                if self.id not in paper_ids:
                    mentor.add_paper(self.id)
                matched_mentor_ids.append(mentor.id)

        self.set_mentor_id_list(matched_mentor_ids)
        self.save(update_fields=["mentor_ids"])

class Mentor(models.Model):
    Chinese_name = models.CharField(max_length=100, verbose_name="中文姓名")
    English_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="英文名")
    research_direction = models.CharField(max_length=255, verbose_name="研究方向")
    email = models.EmailField(blank=True, null=True, verbose_name="导师邮箱")
    profile = models.TextField(blank=True, null=True, verbose_name="导师画像")
    paper_ids = models.TextField(blank=True, default="", verbose_name="论文ID列表") # 论文列表以字符串形式保存
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="private_mentors",
        null=True,
        blank=True,
        verbose_name="所属用户",
    )
    class Meta:
        verbose_name = "导师"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.Chinese_name

    @property
    def is_private(self) -> bool:
        return self.owner_id is not None

    def is_visible_to(self, user) -> bool:
        if self.owner_id is None:
            return True
        if user is None:
            return False
        return self.owner_id == user.id or getattr(user, "role", "") == "admin"

    def get_paper_id_list(self): # 将逗号分隔的字符串转换为整数列表 
        if self.paper_ids == "":
            return []
        return [int(pid) for pid in self.paper_ids.split(",")]

    def set_paper_id_list(self, id_list): # 将整数列表转换为逗号分隔的字符串并保存
        self.paper_ids = ",".join(str(pid) for pid in id_list)

    def get_papers(self): # 获取导师关联的论文
        id_list = self.get_paper_id_list()
        papers = Paper.objects.filter(id__in=id_list)
        paper_map = {paper.id: paper for paper in papers}
        return [paper_map[pid] for pid in id_list]

    def add_paper(self, paper_id): # 添加一篇关联的论文
        id_list = self.get_paper_id_list()
        id_list.append(paper_id)
        self.set_paper_id_list(id_list)
        self.save()

    def remove_paper(self, paper_id): # 删除一篇关联的论文
        id_list = self.get_paper_id_list()
        id_list.remove(paper_id)
        self.set_paper_id_list(id_list)
        self.save()


class WeeklyPaperPush(models.Model):
    week_start = models.DateField(unique=True, verbose_name="周开始日期")
    week_end = models.DateField(verbose_name="周结束日期")
    paper_count = models.IntegerField(default=0, verbose_name="论文数量")
    title = models.CharField(max_length=255, verbose_name="推送标题")
    fixed_summary = models.TextField(blank=True, default="", verbose_name="固定模板总结")
    ai_summary = models.TextField(blank=True, default="", verbose_name="AI生成总结")
    content = models.TextField(blank=True, default="", verbose_name="完整推送内容")
    papers = models.JSONField(blank=True, default=list, verbose_name="本周论文列表")
    generated_by = models.CharField(max_length=32, default="rule", verbose_name="生成方式")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "每周论文推送"
        verbose_name_plural = verbose_name
        ordering = ["-week_start"]

    def serialize(self):
        return {
            "id": self.id,
            "weekStart": self.week_start.isoformat(),
            "weekEnd": self.week_end.isoformat(),
            "paperCount": self.paper_count,
            "title": self.title,
            "fixedSummary": self.fixed_summary,
            "aiSummary": self.ai_summary,
            "content": self.content,
            "papers": self.papers,
            "generatedBy": self.generated_by,
            "updatedAt": self.updated_at.isoformat(sep=" ", timespec="seconds"),
        }
