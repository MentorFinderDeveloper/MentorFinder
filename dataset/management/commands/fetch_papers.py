import os
import re
import arxiv
import time
import requests
from scholarly import scholarly
from django.core.management.base import BaseCommand
from dataset.models import Mentor, Paper


class Command(BaseCommand):
    help = '从 arXiv 和 Google Scholar 抓取导师的论文'
    S2_API_URL = "https://api.semanticscholar.org/graph/v1/paper/ARXIV:{arxiv_id}"
    S2_FIELDS = "s2FieldsOfStudy,tldr"

    SEMANTIC_SCHOLAR_API_TEMPLATE = "https://api.semanticscholar.org/graph/v1/paper/ARXIV:{arxiv_id}"
    SEMANTIC_SCHOLAR_FIELDS = "s2FieldsOfStudy,tldr"
    _ARXIV_VERSION_PATTERN = re.compile(r"v\d+$", re.IGNORECASE)

    def __init__(self):
        super().__init__()
        self.semantic_scholar_cache: dict[str, tuple[list[str], str]] = {}

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

    def _extract_arxiv_id(self, entry_id: str) -> str:
        # arXiv entry_id examples:
        # - http://arxiv.org/abs/2504.12345v1
        # - http://arxiv.org/abs/cs/0112017v1
        if not entry_id:
            return ""
        arxiv_part = entry_id.rsplit("/abs/", 1)[-1].strip()
        if arxiv_part == "":
            return ""
        return arxiv_part.split("v", 1)[0]

    def _build_arxiv_url(self, arxiv_id: str) -> str:
        if arxiv_id == "":
            return ""
        return f"https://arxiv.org/abs/{arxiv_id}"

    def _fetch_s2_metadata(self, arxiv_id: str) -> tuple[str, str]:
        if arxiv_id == "":
            return "", ""

        url = self.S2_API_URL.format(arxiv_id=arxiv_id)
        try:
            response = requests.get(
                url,
                params={"fields": self.S2_FIELDS},
                timeout=15,
                headers={"User-Agent": "MentorFinder/1.0"},
            )
            if response.status_code != 200:
                return "", ""

            payload = response.json()

            fields = payload.get("s2FieldsOfStudy") or []
            field_names = []
            for field_item in fields:
                category = str(field_item.get("category", "")).strip()
                if category:
                    field_names.append(category)
            # 去重并保留顺序
            unique_field_names = list(dict.fromkeys(field_names))
            subjects_str = ", ".join(unique_field_names)

            tldr_data = payload.get("tldr") or {}
            tldr_text = str(tldr_data.get("text", "")).strip()
            return subjects_str, tldr_text
        except Exception:
            return "", ""

    def fetch_from_arxiv(self, mentor):
        self.stdout.write(f"  -> 正在 arXiv 搜索: {mentor.English_name}...")
        
        try:
            client = arxiv.Client()
            # 构建查询：au 代表 author (作者)
            search = arxiv.Search(
                query=f'au:"{mentor.English_name}"',
                sort_by=arxiv.SortCriterion.SubmittedDate
            )

            for result in client.results(search):
                title = result.title
                abstract = result.summary.replace('\n', ' ').strip()
                publish_date = result.published.date()
                authors = ", ".join([author.name for author in result.authors])
                arxiv_id = self._extract_arxiv_id(result.entry_id)
                arxiv_url = self._build_arxiv_url(arxiv_id)
                arxiv_subjects = ", ".join(result.categories)
                s2_subjects, s2_tldr = self._fetch_s2_metadata(arxiv_id)
                subjects_str = s2_subjects or arxiv_subjects

                # 使用 get_or_create 防止论文重复录入数据库
                paper = None
                created = False
                if arxiv_id:
                    paper = Paper.objects.filter(arxiv_id=arxiv_id).first()

                if paper is None:
                    paper, created = Paper.objects.get_or_create(
                        title=title,
                        defaults={
                            "abstract": abstract,
                            "publish_date": publish_date,
                            "author_names": authors,
                            "subjects": subjects_str,
                            "arxiv_id": arxiv_id,
                            "arxiv_url": arxiv_url or None,
                            "tldr": s2_tldr or None,
                        },
                    )
                else:
                    changed = False
                    if paper.title != title:
                        paper.title = title
                        changed = True
                    if not paper.abstract and abstract:
                        paper.abstract = abstract
                        changed = True
                    if paper.publish_date is None and publish_date:
                        paper.publish_date = publish_date
                        changed = True
                    if not paper.author_names and authors:
                        paper.author_names = authors
                        changed = True
                    if not paper.subjects and subjects_str:
                        paper.subjects = subjects_str
                        changed = True
                    if not paper.arxiv_id and arxiv_id:
                        paper.arxiv_id = arxiv_id
                        changed = True
                    if not paper.arxiv_url and arxiv_url:
                        paper.arxiv_url = arxiv_url
                        changed = True
                    if not paper.tldr and s2_tldr:
                        paper.tldr = s2_tldr
                        changed = True
                    if changed:
                        paper.save()

                if created:
                    self.stdout.write(self.style.SUCCESS(f"    [新增论文] {title} (分类: {subjects_str})"))
                else:
                    updated = False
                    if not paper.subjects and subjects_str:
                        paper.subjects = subjects_str
                        updated = True
                    if not paper.tldr and s2_tldr:
                        paper.tldr = s2_tldr
                        updated = True
                    if not paper.arxiv_id and arxiv_id:
                        paper.arxiv_id = arxiv_id
                        updated = True
                    if not paper.arxiv_url and arxiv_url:
                        paper.arxiv_url = arxiv_url
                        updated = True
                    if updated:
                        paper.save()
                        self.stdout.write(self.style.SUCCESS(f"    [更新论文元数据] {title} (分类: {subjects_str})"))
                
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

            for pub in author['publications']:
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
