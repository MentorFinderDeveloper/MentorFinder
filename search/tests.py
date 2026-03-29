from django.test import TestCase


class SearchSmokeTests(TestCase):
    def test_search_health(self):
        res = self.client.get("/search/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["module"], "search")

