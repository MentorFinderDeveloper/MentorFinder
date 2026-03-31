from django.test import TestCase

from dataset.models import Mentor, Paper


class SearchTests(TestCase):
    def setUp(self):
        self.zs = Mentor.objects.create(
            name="张三",
            research_direction="机器学习",
            email="zhangsan@example.com",
            profile="主要研究机器学习与数据挖掘。",
        )
        self.ls = Mentor.objects.create(
            name="李四",
            research_direction="自然语言处理",
            email="lisi@example.com",
            profile="主要研究自然语言处理与大模型应用。",
        )

        self.paper1 = Paper.objects.create(
            title="机器学习方法研究",
            abstract="本文讨论常见机器学习方法及其应用场景。",
            publish_date="2024-05-01",
        )
        self.paper2 = Paper.objects.create(
            title="大语言模型在问答系统中的应用",
            abstract="本文介绍大语言模型在智能问答中的实践。",
            publish_date="2024-06-15",
        )

        self.paper1.mentors.add(self.zs)
        self.paper2.mentors.add(self.ls, self.zs)

    def test_search_health(self):
        res = self.client.get("/search/health")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["module"], "search")

    def test_search_mentors_by_name(self):
        res = self.client.get("/search/mentors", {"keyword": "张三"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["keyword"], "张三")
        self.assertEqual(len(res.json()["mentors"]), 1)

        mentor = res.json()["mentors"][0]
        self.assertEqual(
            set(mentor.keys()),
            {"id", "name", "research_direction", "email", "profile", "paperTitles"},
        )
        self.assertEqual(mentor["name"], "张三")
        self.assertEqual(mentor["research_direction"], "机器学习")
        self.assertEqual(mentor["paperTitles"], ["机器学习方法研究", "大语言模型在问答系统中的应用"])

    def test_search_mentors_by_research_direction(self):
        res = self.client.get("/search/mentors", {"keyword": "机器学习"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["name"], "张三")

    def test_search_papers_by_exact_title(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习方法研究"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["keyword"], "机器学习方法研究")
        self.assertEqual(len(res.json()["papers"]), 1)

        paper = res.json()["papers"][0]
        self.assertEqual(
            set(paper.keys()),
            {"id", "title", "abstract", "publish_date", "mentorNames"},
        )
        self.assertEqual(paper["title"], "机器学习方法研究")
        self.assertEqual(paper["mentorNames"], ["张三"])

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

    def test_search_no_match_returns_empty_list(self):
        mentor_res = self.client.get("/search/mentors", {"keyword": "量子拓扑星舰"})
        paper_res = self.client.get("/search/papers", {"keyword": "量子拓扑星舰"})

        self.assertEqual(mentor_res.status_code, 200)
        self.assertEqual(mentor_res.json()["mentors"], [])
        self.assertEqual(paper_res.status_code, 200)
        self.assertEqual(paper_res.json()["papers"], [])

    def test_search_keyword_missing(self):
        res = self.client.get("/search/mentors")

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_search_keyword_empty(self):
        res = self.client.get("/search/papers", {"keyword": "   "})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_search_bad_method(self):
        res = self.client.post("/search/mentors", {"keyword": "张三"})

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)
