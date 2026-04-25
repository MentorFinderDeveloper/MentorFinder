from django.conf import settings
from django.db import models


class Paper(models.Model):
    title = models.CharField(max_length=255, verbose_name="论文题目")
    abstract = models.TextField(blank=True, null=True, verbose_name="摘要")
    publish_date = models.DateField(blank=True, null=True, verbose_name="发表日期")
    author_names = models.TextField(blank=True, default="", verbose_name="作者名单")
    subjects = models.CharField(max_length=255, blank=True, default="", verbose_name="学科/分类")
    arxiv_id = models.CharField(max_length=64, blank=True, default="", verbose_name="arXiv ID")
    arxiv_url = models.URLField(blank=True, null=True, verbose_name="arXiv 链接")
    tldr = models.TextField(blank=True, null=True, verbose_name="一句话总结")
    class Meta:
        verbose_name = "论文"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title

    def get_author_list(self):
        if self.author_names == "":
            return []
        return [name.strip() for name in self.author_names.split(",")]

    def bind_to_mentors_by_authors(self):
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
