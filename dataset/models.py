from django.db import models


class Paper(models.Model):
    title = models.CharField(max_length=255, verbose_name="论文题目")
    abstract = models.TextField(blank=True, null=True, verbose_name="摘要")
    publish_date = models.DateField(blank=True, null=True, verbose_name="发表日期")
    author_names = models.TextField(blank=True, default="", verbose_name="作者名单")

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
        author_list = self.get_author_list()

        for mentor in Mentor.objects.all():
            if mentor.Chinese_name in author_list or mentor.English_name in author_list:
                paper_ids = mentor.get_paper_id_list()
                if self.id not in paper_ids:
                    mentor.add_paper(self.id)
                    mentor.save()


class Mentor(models.Model):
    Chinese_name = models.CharField(max_length=100, verbose_name="中文姓名")
    English_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="英文名")
    research_direction = models.CharField(max_length=255, verbose_name="研究方向")
    email = models.EmailField(blank=True, null=True, verbose_name="导师邮箱")
    profile = models.TextField(blank=True, null=True, verbose_name="导师画像")
    paper_ids = models.TextField(blank=True, default="", verbose_name="论文ID列表") # 论文列表以字符串形式保存

    class Meta:
        verbose_name = "导师"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.Chinese_name

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