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

    def _build_semantic_scholar_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": "MentorFinder/1.0",
            "Accept": "application/json",
        }
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    def _split_subjects(self, subjects_str: str) -> list[str]:
        if not subjects_str:
            return []
        return [s.strip() for s in subjects_str.split(",") if s.strip()]

    def _deduplicate_terms(self, terms: list[str]) -> list[str]:
        deduplicated = []
        seen = set()
        for term in terms:
            cleaned = str(term).strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(cleaned)
        return deduplicated

    def _merge_subjects(self, *subject_groups: list[str]) -> str:
        merged = []
        for group in subject_groups:
            merged.extend(group)
        return ", ".join(self._deduplicate_terms(merged))

    def _normalize_arxiv_id(self, raw_arxiv_id: str) -> str:
        normalized = (raw_arxiv_id or "").strip()
        if normalized == "":
            return ""

        normalized = normalized.replace("ARXIV:", "").replace("arXiv:", "")
        normalized = normalized.replace(".pdf", "")

        if "/abs/" in normalized:
            normalized = normalized.split("/abs/", 1)[1]
        if "/pdf/" in normalized:
            normalized = normalized.split("/pdf/", 1)[1]

        normalized = normalized.split("?", 1)[0].strip("/")
        normalized = self._ARXIV_VERSION_PATTERN.sub("", normalized)
        return normalized

    def _extract_arxiv_id(self, result) -> str:
        entry_id = getattr(result, "entry_id", "")
        normalized_from_entry = self._normalize_arxiv_id(entry_id)
        if normalized_from_entry:
            return normalized_from_entry

        get_short_id = getattr(result, "get_short_id", None)
        if callable(get_short_id):
            return self._normalize_arxiv_id(get_short_id())
        return ""

    def fetch_semantic_scholar_metadata(self, arxiv_id: str) -> tuple[list[str], str]:
        normalized_arxiv_id = self._normalize_arxiv_id(arxiv_id)
        if normalized_arxiv_id == "":
            return [], ""

        cached = self.semantic_scholar_cache.get(normalized_arxiv_id)
        if cached is not None:
            return cached

        url = self.SEMANTIC_SCHOLAR_API_TEMPLATE.format(arxiv_id=normalized_arxiv_id)

        try:
            resp = requests.get(
                url,
                params={"fields": self.SEMANTIC_SCHOLAR_FIELDS},
                headers=self._build_semantic_scholar_headers(),
                timeout=10,
            )
            if resp.status_code == 404:
                result = ([], "")
                self.semantic_scholar_cache[normalized_arxiv_id] = result
                return result

            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            self.stdout.write(
                self.style.WARNING(
                    f"    [Semantic Scholar 请求失败] {normalized_arxiv_id}: {exc}"
                )
            )
            result = ([], "")
            self.semantic_scholar_cache[normalized_arxiv_id] = result
            return result
        except ValueError as exc:
            self.stdout.write(
                self.style.WARNING(
                    f"    [Semantic Scholar 响应解析失败] {normalized_arxiv_id}: {exc}"
                )
            )
            result = ([], "")
            self.semantic_scholar_cache[normalized_arxiv_id] = result
            return result

        fields = []
        for item in payload.get("s2FieldsOfStudy") or []:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category", "")).strip()
            if category:
                fields.append(category)

        fields = self._deduplicate_terms(fields)

        tldr_text = ""
        tldr = payload.get("tldr")
        if isinstance(tldr, dict):
            tldr_text = str(tldr.get("text", "")).strip()

        result = (fields, tldr_text)
        self.semantic_scholar_cache[normalized_arxiv_id] = result
        return result

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
                arxiv_categories = list(result.categories)
                arxiv_id = self._extract_arxiv_id(result)
                s2_fields, s2_tldr = self.fetch_semantic_scholar_metadata(arxiv_id)

                if not abstract and s2_tldr:
                    abstract = s2_tldr

                subjects_str = self._merge_subjects(arxiv_categories, s2_fields)
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
                    changed = False
                    existing_subjects = self._split_subjects(paper.subjects)
                    merged_subjects = self._merge_subjects(existing_subjects, arxiv_categories, s2_fields)

                    if merged_subjects and merged_subjects != paper.subjects:
                        paper.subjects = merged_subjects
                        changed = True

                    if not paper.abstract and abstract:
                        paper.abstract = abstract
                        changed = True

                    if paper.publish_date is None and publish_date is not None:
                        paper.publish_date = publish_date
                        changed = True

                    if not paper.author_names and authors:
                        paper.author_names = authors
                        changed = True

                    if changed:
                        paper.save()
                        self.stdout.write(self.style.SUCCESS(f"    [更新旧论文] {title} (分类: {paper.subjects})"))
                
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