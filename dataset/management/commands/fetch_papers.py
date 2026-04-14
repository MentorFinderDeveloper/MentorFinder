import arxiv
import time
from scholarly import scholarly
from django.core.management.base import BaseCommand
from dataset.models import Mentor, Paper
class Command(BaseCommand):
    help = '从 arXiv 和 Google Scholar 抓取导师的论文'

    def handle(self, *args, **kwargs):
        mentors = Mentor.objects.all()

        for mentor in mentors:
            self.stdout.write(f"正在处理导师: {mentor.Chinese_name} ({mentor.English_name})")
            
            # 由于外文期刊主要用英文名，如果没有英文名则跳过（或者你可以引入拼音转换库）
            if not mentor.English_name:
                self.stdout.write(self.style.WARNING(f"缺少英文名，跳过 {mentor.Chinese_name}"))
                continue

            # 1. 从 arXiv 获取论文
            self.fetch_from_arxiv(mentor)

            # 2. 从 Google Scholar 获取论文 (取消注释以启用，但注意可能被Google暂时封IP)
            # self.fetch_from_scholar(mentor)
            time.sleep(3)

    def fetch_from_arxiv(self, mentor):
        self.stdout.write(f"  -> 正在 arXiv 搜索: {mentor.English_name}...")
        
        try:
            client = arxiv.Client()
            # 构建查询：au 代表 author (作者)
            search = arxiv.Search(
                query=f'au:"{mentor.English_name}"',
                max_results=10,  # 限制抓取数量，避免一次性过多
                sort_by=arxiv.SortCriterion.SubmittedDate
            )

            for result in client.results(search):
                title = result.title
                abstract = result.summary.replace('\n', ' ')
                publish_date = result.published.date()
                authors = ", ".join([author.name for author in result.authors])
                subjects_str = ", ".join(result.categories)
                # 使用 get_or_create 防止论文重复录入数据库
                paper, created = Paper.objects.get_or_create(
                    title=title,
                    defaults={
                        'abstract': abstract,
                        'publish_date': publish_date,
                        'author_names': authors,
                        'subjects': subjects_str
                    }
                )

                if created:
                    self.stdout.write(self.style.SUCCESS(f"    [新增论文] {title} (分类: {subjects_str})"))
                else:
                    # 如果论文已经存在，检查是否之前没有爬取 subjects
                    if not paper.subjects and subjects_str:
                        paper.subjects = subjects_str
                        paper.save()
                        self.stdout.write(self.style.SUCCESS(f"    [更新旧论文分类] {title} (分类: {subjects_str})"))
                
                paper.bind_to_mentors_by_authors()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  arXiv 抓取报错: {e}"))


    def fetch_from_scholar(self, mentor):
        self.stdout.write(f"  -> 正在 Google Scholar 搜索: {mentor.English_name}...")
        try:
            # 搜索作者
            search_query = scholarly.search_author(mentor.English_name)
            author = next(search_query) # 获取第一个匹配的作者
            author = scholarly.fill(author) # 填充该作者的详细信息（包括论文列表）

            for pub in author['publications'][:10]: # 限制前10篇
                pub_filled = scholarly.fill(pub) # 填充单篇论文详细信息获取摘要和作者
                
                title = pub_filled['bib'].get('title', '')
                abstract = pub_filled['bib'].get('abstract', '')
                authors = pub_filled['bib'].get('author', '')
                
                # 处理年份 (Scholar 通常只有年份)
                pub_year = pub_filled['bib'].get('pub_year')
                publish_date = f"{pub_year}-01-01" if pub_year else None

                paper, created = Paper.objects.get_or_create(
                    title=title,
                    defaults={
                        'abstract': abstract,
                        'publish_date': publish_date,
                        'author_names': authors
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f"    [新增论文] {title}"))
                paper.bind_to_mentors_by_authors()

        except StopIteration:
            self.stdout.write(self.style.WARNING(f"    在 Scholar 未找到该作者"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Scholar 抓取报错: {e}"))