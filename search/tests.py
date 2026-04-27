from django.test import TestCase

from account.models import User
from dataset.models import Mentor, Paper
from search.services.engine import search_papers_fuzzy
from utils.utils_jwt import generate_jwt_token


class SearchTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner1",
            email="owner1@example.com",
            password="abc12345",
            role="student",
        )
        self.owner_token = generate_jwt_token("owner1")

        self.other_user = User.objects.create_user(
            username="other1",
            email="other1@example.com",
            password="abc12345",
            role="student",
        )
        self.other_token = generate_jwt_token("other1")

        self.zs = Mentor.objects.create(
            Chinese_name="张三",
            English_name="Zhang San",
            research_direction="机器学习",
            email="zhangsan@example.com",
            profile="主要研究机器学习与数据挖掘。",
        )
        self.ls = Mentor.objects.create(
            Chinese_name="李四",
            English_name="Li Si",
            research_direction="自然语言处理",
            email="lisi@example.com",
            profile="主要研究自然语言处理与大模型应用。",
        )

        self.paper1 = Paper.objects.create(
            title="机器学习方法研究",
            abstract="本文讨论常见机器学习方法及其应用场景。",
            publish_date="2024-05-01",
            author_names="张三",
            subjects="cs.LG, cs.AI",
        )
        self.paper2 = Paper.objects.create(
            title="大语言模型在问答系统中的应用",
            abstract="本文介绍大语言模型在智能问答中的实践。",
            publish_date="2024-06-15",
            author_names="李四,张三",
            subjects="cs.CL",
        )

        self.private_paper = Paper.objects.create(
            title="隐私导师论文",
            abstract="仅用于测试私有导师检索可见性。",
            publish_date="2024-07-01",
            author_names="王五",
            subjects="cs.CR",
        )

        self.private_mentor = Mentor.objects.create(
            Chinese_name="王五",
            English_name="Wang Wu",
            research_direction="强化学习",
            email="wangwu@example.com",
            profile="私有导师",
            owner=self.owner,
        )

        self.zs.add_paper(self.paper1.id)
        self.zs.add_paper(self.paper2.id)
        self.ls.add_paper(self.paper2.id)
        self.private_mentor.add_paper(self.private_paper.id)

    def auth_headers(self, token: str):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_search_health(self):
        res = self.client.get("/search/health")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["module"], "search")

    def test_search_health_bad_method(self):
        res = self.client.post("/search/health")

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    def test_search_mentors_by_name(self):
        res = self.client.get("/search/mentors", {"keyword": "张三"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["keyword"], "张三")
        self.assertEqual(len(res.json()["mentors"]), 1)

        mentor = res.json()["mentors"][0]
        self.assertEqual(
            set(mentor.keys()),
            {"id", "Chinese_name", "English_name", "research_direction", "email", "profile", "paperTitles", "is_private"},
        )
        self.assertEqual(mentor["Chinese_name"], "张三")
        self.assertEqual(mentor["English_name"], "Zhang San")
        self.assertEqual(mentor["research_direction"], "机器学习")
        self.assertEqual(mentor["paperTitles"], ["机器学习方法研究", "大语言模型在问答系统中的应用"])
        self.assertEqual(mentor["is_private"], False)

    def test_search_mentors_by_research_direction(self):
        res = self.client.get("/search/mentors", {"keyword": "机器学习"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "张三")

    def test_search_mentors_by_english_name(self):
        res = self.client.get("/search/mentors", {"keyword": "Zhang San"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "张三")

    def test_search_mentors_by_english_name_case_insensitive(self):
        res = self.client.get("/search/mentors", {"keyword": "zhang san"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "张三")

    def test_search_papers_by_exact_title(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习方法研究"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["keyword"], "机器学习方法研究")
        self.assertEqual(len(res.json()["papers"]), 1)

        paper = res.json()["papers"][0]
        self.assertEqual(
            set(paper.keys()),
            {"id", "title", "abstract", "publish_date", "author_names", "subjects", "mentorNames"},
        )
        self.assertEqual(paper["title"], "机器学习方法研究")
        self.assertEqual(paper["subjects"], "cs.LG, cs.AI")
        self.assertEqual(paper["mentorNames"], ["张三"])
        self.assertEqual(paper["author_names"], "张三")

    def test_search_papers_by_mentor_research_direction(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(
            {paper["title"] for paper in res.json()["papers"]},
            {"机器学习方法研究", "大语言模型在问答系统中的应用"},
        )

    def test_search_papers_by_mentor_name(self):
        res = self.client.get("/search/papers", {"keyword": "李四"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["大语言模型在问答系统中的应用"])

    def test_search_papers_by_mentor_english_name(self):
        res = self.client.get("/search/papers", {"keyword": "Li Si"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["大语言模型在问答系统中的应用"])

    def test_search_papers_by_author_names(self):
        res = self.client.get("/search/papers", {"keyword": "张三"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(
            {paper["title"] for paper in res.json()["papers"]},
            {"机器学习方法研究", "大语言模型在问答系统中的应用"},
        )

    def test_search_papers_deduplicate_multi_source_matches(self):
        res = self.client.get("/search/papers", {"keyword": "张三"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)

        paper_titles = [paper["title"] for paper in res.json()["papers"]]
        self.assertEqual(
            set(paper_titles),
            {"机器学习方法研究", "大语言模型在问答系统中的应用"},
        )
        self.assertEqual(len(paper_titles), len(set(paper_titles)))

    def test_search_papers_title_match_has_priority_over_mentor_match(self):
        mentor_same_as_title = Mentor.objects.create(
            Chinese_name="机器学习方法研究",
            English_name="Title Name",
            research_direction="知识图谱",
            email="titlementor@example.com",
            profile="用于验证标题优先级。",
        )
        mentor_same_as_title.add_paper(self.paper2.id)

        res = self.client.get("/search/papers", {"keyword": "机器学习方法研究"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["机器学习方法研究"])

    def test_search_papers_title_does_not_support_fuzzy_match(self):
        res = self.client.get("/search/papers", {"keyword": "语言模型"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["papers"], [])

    def test_search_papers_fuzzy_by_title_substring(self):
        papers = search_papers_fuzzy("语言模型")

        self.assertEqual([paper["title"] for paper in papers], ["大语言模型在问答系统中的应用"])

    def test_search_papers_fuzzy_by_mentor_chinese_name_substring(self):
        papers = search_papers_fuzzy("张")

        self.assertEqual(
            {paper["title"] for paper in papers},
            {"机器学习方法研究", "大语言模型在问答系统中的应用"},
        )

    def test_search_papers_fuzzy_by_mentor_english_name_substring(self):
        papers = search_papers_fuzzy("Li")

        self.assertEqual([paper["title"] for paper in papers], ["大语言模型在问答系统中的应用"])

    def test_search_papers_fuzzy_by_research_direction_substring(self):
        papers = search_papers_fuzzy("自然语言")

        self.assertEqual([paper["title"] for paper in papers], ["大语言模型在问答系统中的应用"])

    def test_search_papers_fuzzy_deduplicates_results(self):
        papers = search_papers_fuzzy("张")

        paper_titles = [paper["title"] for paper in papers]
        self.assertEqual(len(paper_titles), len(set(paper_titles)))

    def test_search_papers_fuzzy_no_match_returns_empty_list(self):
        papers = search_papers_fuzzy("量子拓扑星舰")

        self.assertEqual(papers, [])

    def test_search_mentors_api_fuzzy_mode(self):
        res = self.client.get("/search/mentors", {"keyword": "张", "search_mode": "fuzzy"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["search_mode"], "fuzzy")
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "张三")

    def test_search_papers_api_fuzzy_mode(self):
        res = self.client.get("/search/papers", {"keyword": "语言模型", "search_mode": "fuzzy"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["search_mode"], "fuzzy")
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["大语言模型在问答系统中的应用"])

    def test_search_papers_default_sort_mode(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["sort_mode"], "default")

    def test_search_papers_sort_mode_early(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习", "sort_mode": "early"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["sort_mode"], "early")
        self.assertEqual(
            [paper["title"] for paper in res.json()["papers"]],
            ["机器学习方法研究", "大语言模型在问答系统中的应用"],
        )

    def test_search_papers_sort_mode_late(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习", "sort_mode": "late"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["sort_mode"], "late")
        self.assertEqual(
            [paper["title"] for paper in res.json()["papers"]],
            ["大语言模型在问答系统中的应用", "机器学习方法研究"],
        )

    def test_search_mentors_supports_pagination(self):
        Mentor.objects.create(
            Chinese_name="张六",
            English_name="Zhang Liu",
            research_direction="机器学习工程",
            email="zhangliu@example.com",
            profile="用于分页测试",
        )

        page1 = self.client.get(
            "/search/mentors",
            {
                "keyword": "学习",
                "search_mode": "fuzzy",
                "page": 1,
                "page_size": 1,
            },
        )
        page2 = self.client.get(
            "/search/mentors",
            {
                "keyword": "学习",
                "search_mode": "fuzzy",
                "page": 2,
                "page_size": 1,
            },
        )

        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page2.status_code, 200)

        page1_data = page1.json()
        page2_data = page2.json()

        self.assertEqual(page1_data["total"], 2)
        self.assertEqual(page1_data["total_pages"], 2)
        self.assertEqual(page1_data["page"], 1)
        self.assertTrue(page1_data["has_next"])
        self.assertFalse(page1_data["has_previous"])
        self.assertEqual(len(page1_data["mentors"]), 1)

        self.assertEqual(page2_data["total"], 2)
        self.assertEqual(page2_data["total_pages"], 2)
        self.assertEqual(page2_data["page"], 2)
        self.assertFalse(page2_data["has_next"])
        self.assertTrue(page2_data["has_previous"])
        self.assertEqual(len(page2_data["mentors"]), 1)

    def test_search_papers_supports_pagination(self):
        page1 = self.client.get(
            "/search/papers",
            {
                "keyword": "张",
                "search_mode": "fuzzy",
                "sort_mode": "early",
                "page": 1,
                "page_size": 1,
            },
        )
        page2 = self.client.get(
            "/search/papers",
            {
                "keyword": "张",
                "search_mode": "fuzzy",
                "sort_mode": "early",
                "page": 2,
                "page_size": 1,
            },
        )

        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page2.status_code, 200)

        page1_data = page1.json()
        page2_data = page2.json()

        self.assertEqual(page1_data["total"], 2)
        self.assertEqual(page1_data["total_pages"], 2)
        self.assertEqual(page1_data["page"], 1)
        self.assertEqual(page1_data["papers"][0]["title"], "机器学习方法研究")
        self.assertTrue(page1_data["has_next"])
        self.assertFalse(page1_data["has_previous"])

        self.assertEqual(page2_data["total"], 2)
        self.assertEqual(page2_data["total_pages"], 2)
        self.assertEqual(page2_data["page"], 2)
        self.assertEqual(page2_data["papers"][0]["title"], "大语言模型在问答系统中的应用")
        self.assertFalse(page2_data["has_next"])
        self.assertTrue(page2_data["has_previous"])

    def test_search_api_invalid_search_mode(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习", "search_mode": "partial"})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_search_api_invalid_sort_mode(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习", "sort_mode": "random"})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_search_no_match_returns_empty_list(self):
        mentor_res = self.client.get("/search/mentors", {"keyword": "量子拓扑星舰"})
        paper_res = self.client.get("/search/papers", {"keyword": "量子拓扑星舰"})

        self.assertEqual(mentor_res.status_code, 200)
        self.assertEqual(mentor_res.json()["mentors"], [])
        self.assertEqual(paper_res.status_code, 200)
        self.assertEqual(paper_res.json()["papers"], [])

    def test_search_mentors_excludes_private_mentor_without_auth(self):
        res = self.client.get("/search/mentors", {"keyword": "王五"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["mentors"], [])

    def test_search_mentors_includes_private_mentor_for_owner(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": "王五"},
            **self.auth_headers(self.owner_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "王五")

    def test_search_mentors_excludes_private_mentor_for_other_user(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": "王五"},
            **self.auth_headers(self.other_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["mentors"], [])

    def test_search_keyword_missing(self):
        res = self.client.get("/search/mentors")

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_search_keyword_empty(self):
        res = self.client.get("/search/papers", {"keyword": "   "})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_search_keyword_too_long_for_mentors(self):
        res = self.client.get("/search/mentors", {"keyword": "x" * 256})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_search_keyword_too_long_for_papers(self):
        res = self.client.get("/search/papers", {"keyword": "x" * 256})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_search_keyword_trimmed_before_search(self):
        mentor_res = self.client.get("/search/mentors", {"keyword": "  张三  "})
        paper_res = self.client.get("/search/papers", {"keyword": "  李四  "})

        self.assertEqual(mentor_res.status_code, 200)
        self.assertEqual(mentor_res.json()["keyword"], "张三")
        self.assertEqual(len(mentor_res.json()["mentors"]), 1)

        self.assertEqual(paper_res.status_code, 200)
        self.assertEqual(paper_res.json()["keyword"], "李四")
        self.assertEqual([paper["title"] for paper in paper_res.json()["papers"]], ["大语言模型在问答系统中的应用"])

    def test_search_bad_method(self):
        res = self.client.post("/search/mentors", {"keyword": "张三"})

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    def test_search_papers_bad_method(self):
        res = self.client.post("/search/papers", {"keyword": "张三"})

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)
