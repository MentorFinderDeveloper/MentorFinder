from django.test import TestCase
from .models import Mentor, Paper

import json


class SeparateMaintenanceTest(TestCase):
    def setUp(self):
        self.paper1 = Paper.objects.create(title="论文1")
        self.paper2 = Paper.objects.create(title="论文2")
        self.paper3 = Paper.objects.create(title="论文3")
        self.mentor = Mentor.objects.create(
            Chinese_name="张老师",
            English_name="Dr. Zhang",
            research_direction="自然语言处理",
            email="zhang@example.com",
        )

    def test_add_paper(self):
        self.mentor.add_paper(self.paper2.id)
        self.mentor.add_paper(self.paper1.id)
        self.assertEqual(self.mentor.get_paper_id_list(), [self.paper2.id, self.paper1.id])

class DatasetViewTest(TestCase):
    def test_create_paper_success(self):
        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "title": "A Survey on Mentor Matching",
                "abstract": "This paper studies mentor matching.",
                "publish_date": "2024-05-01",
                "author_names": "张三, John Smith"
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["code"], 0)
        self.assertIn("paper", data)
        self.assertEqual(data["paper"]["title"], "A Survey on Mentor Matching")
        self.assertEqual(data["paper"]["abstract"], "This paper studies mentor matching.")
        self.assertEqual(data["paper"]["author_names"], "张三, John Smith")
        self.assertEqual(data["paper"]["publish_date"], "2024-05-01")

        paper = Paper.objects.get(id=data["paper"]["id"])
        self.assertEqual(paper.title, "A Survey on Mentor Matching")
        self.assertEqual(paper.abstract, "This paper studies mentor matching.")
        self.assertEqual(str(paper.publish_date), "2024-05-01")
        self.assertEqual(paper.author_names, "张三, John Smith")

    def test_create_paper_requires_title(self):
        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "abstract": "No title here"
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["code"], -2)
        self.assertEqual(Paper.objects.count(), 0)

    def test_create_paper_rejects_empty_title(self):
        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "title": "   ",
                "abstract": "No title here"
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["code"], -2)
        self.assertEqual(Paper.objects.count(), 0)

    def test_create_paper_rejects_get(self):
        response = self.client.get("/dataset/papers")

        self.assertEqual(response.status_code, 405)
        data = response.json()
        self.assertEqual(data["code"], -3)

    def test_create_mentor_success(self):
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "张老师",
                "English_name": "Zhang",
                "research_direction": "自然语言处理",
                "email": "zhang@example.com",
                "profile": "专注大模型与信息检索",
                "paper_ids": "1,2,3"
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        mentor = Mentor.objects.get(id=data["mentor"]["id"])
        self.assertEqual(mentor.Chinese_name, "张老师")
        self.assertEqual(mentor.English_name, "Zhang")
        self.assertEqual(mentor.research_direction, "自然语言处理")
        self.assertEqual(mentor.email, "zhang@example.com")
        self.assertEqual(mentor.profile, "专注大模型与信息检索")

    def test_create_mentor_requires_chinese_name(self):
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "research_direction": "自然语言处理"
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["code"], -2)
        self.assertEqual(Mentor.objects.count(), 0)

    def test_create_mentor_requires_research_direction(self):
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "张老师"
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["code"], -2)
        self.assertEqual(Mentor.objects.count(), 0)

    def test_create_mentor_rejects_empty_required_fields(self):
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "   ",
                "research_direction": "   "
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["code"], -2)
        self.assertEqual(Mentor.objects.count(), 0)

    def test_create_mentor_rejects_invalid_email(self):
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "张老师",
                "research_direction": "自然语言处理",
                "email": "invalid-email"
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["code"], -2)
        self.assertEqual(Mentor.objects.count(), 0)

    def test_create_mentor_rejects_get(self):
        response = self.client.get("/dataset/mentors")

        self.assertEqual(response.status_code, 405)
        data = response.json()
        self.assertEqual(data["code"], -3)