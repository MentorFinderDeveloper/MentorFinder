from django.test import TestCase


class SearchSmokeTests(TestCase):
    def test_search_health(self):
        res = self.client.get("/search/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["module"], "search")

    def test_search_mentors_success(self):
        res = self.client.get("/search/mentors", {"keyword": "张三"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["keyword"], "张三")
        self.assertIsInstance(res.json()["mentors"], list)
        self.assertGreater(len(res.json()["mentors"]), 0)
        mentor = res.json()["mentors"][0]
        self.assertEqual(
            set(mentor.keys()),
            {"id", "name", "researchDirection", "email", "profile", "paperTitles"},
        )
        self.assertIsInstance(mentor["paperTitles"], list)

    def test_search_papers_success(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["keyword"], "机器学习")
        self.assertIsInstance(res.json()["papers"], list)
        self.assertGreater(len(res.json()["papers"]), 0)
        paper = res.json()["papers"][0]
        self.assertEqual(
            set(paper.keys()),
            {"id", "title", "abstract", "publishDate", "mentorNames"},
        )
        self.assertIsInstance(paper["mentorNames"], list)

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
