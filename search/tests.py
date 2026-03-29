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
        self.assertEqual(res.json()["mentors"], [])

    def test_search_papers_success(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["keyword"], "机器学习")
        self.assertEqual(res.json()["papers"], [])

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
