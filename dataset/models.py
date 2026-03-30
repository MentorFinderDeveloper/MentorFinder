from django.db import models
#导师表
class Mentor(models.Model):
    name = models.CharField(max_length=100, verbose_name="姓名")
    research_direction = models.CharField(max_length=255, verbose_name="研究方向")
    email = models.EmailField(blank=True, null=True, verbose_name="导师邮箱")
    profile = models.TextField(blank=True, null=True, verbose_name="导师画像")

    class Meta:
        verbose_name = "导师"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name

#论文表
class Paper(models.Model):
    title = models.CharField(max_length=255, verbose_name="论文题目")
    abstract = models.TextField(blank=True, null=True, verbose_name="摘要")
    publish_date = models.DateField(blank=True, null=True, verbose_name="发表日期")
    
    # 多对多关联导师
    mentors = models.ManyToManyField(Mentor, related_name="papers", verbose_name="所属导师")

    class Meta:
        verbose_name = "论文"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title