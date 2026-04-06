import json

from django.test import TestCase

from account.models import User
from dataset.models import Mentor, Paper
from utils.utils_jwt import generate_jwt_token


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
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="dataset_admin",
            password="abc12345",
            email="dataset_admin@example.com",
            role="admin",
        )
        self.student_user = User.objects.create_user(
            username="dataset_student",
            password="abc12345",
            email="dataset_student@example.com",
            role="student",
        )
        self.admin_headers = {
            "HTTP_AUTHORIZATION": f"Bearer {generate_jwt_token(self.admin_user.username)}",
        }
        self.student_headers = {
            "HTTP_AUTHORIZATION": f"Bearer {generate_jwt_token(self.student_user.username)}",
        }

    def post_json(self, path: str, payload: dict, headers: dict | None = None):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
            **(headers or {}),
        )

    def put_json(self, path: str, payload: dict, headers: dict | None = None):
        return self.client.put(
            path,
            data=json.dumps(payload),
            content_type="application/json",
            **(headers or {}),
        )

    def delete_json(self, path: str, headers: dict | None = None):
        return self.client.delete(path, **(headers or {}))

    def test_create_paper_requires_admin(self):
        payload = {
            "title": "A Survey on Mentor Matching",
            "abstract": "This paper studies mentor matching.",
            "publish_date": "2024-05-01",
            "author_names": "张三, John Smith",
        }

        response_without_auth = self.post_json("/dataset/papers", payload)
        response_with_student = self.post_json("/dataset/papers", payload, self.student_headers)

        self.assertEqual(response_without_auth.status_code, 401)
        self.assertEqual(response_without_auth.json()["code"], 2)
        self.assertEqual(response_with_student.status_code, 403)
        self.assertEqual(response_with_student.json()["code"], 3)
        self.assertEqual(Paper.objects.count(), 0)

    def test_create_paper_success(self):
        response = self.post_json(
            "/dataset/papers",
            {
                "title": "A Survey on Mentor Matching",
                "abstract": "This paper studies mentor matching.",
                "publish_date": "2024-05-01",
                "author_names": "张三, John Smith",
            },
            self.admin_headers,
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

    def test_update_paper_success(self):
        mentor = Mentor.objects.create(
            Chinese_name="张三",
            research_direction="人工智能",
            paper_ids="",
        )
        paper = Paper.objects.create(title="Old Title", author_names="李四")

        response = self.put_json(
            f"/dataset/papers/{paper.id}",
            {
                "title": "New Title",
                "abstract": "updated",
                "publish_date": "2024-06-01",
                "author_names": "张三",
            },
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        paper.refresh_from_db()
        mentor.refresh_from_db()
        self.assertEqual(paper.title, "New Title")
        self.assertIn(paper.id, mentor.get_paper_id_list())

    def test_delete_paper_success(self):
        mentor = Mentor.objects.create(
            Chinese_name="张三",
            research_direction="人工智能",
            paper_ids="",
        )
        paper = Paper.objects.create(title="Will Be Deleted", author_names="张三")
        mentor.add_paper(paper.id)

        response = self.delete_json(f"/dataset/papers/{paper.id}", self.admin_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        self.assertFalse(Paper.objects.filter(id=paper.id).exists())

        mentor.refresh_from_db()
        self.assertNotIn(paper.id, mentor.get_paper_id_list())

    def test_create_mentor_success(self):
        Paper.objects.create(title="Paper", author_names="张老师")

        response = self.post_json(
            "/dataset/mentors",
            {
                "Chinese_name": "张老师",
                "English_name": "Zhang",
                "research_direction": "自然语言处理",
                "email": "zhang@example.com",
                "profile": "专注大模型与信息检索",
            },
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        mentor = Mentor.objects.get(id=data["mentor"]["id"])
        self.assertEqual(mentor.Chinese_name, "张老师")
        self.assertEqual(mentor.English_name, "Zhang")
        self.assertEqual(mentor.research_direction, "自然语言处理")
        self.assertEqual(mentor.email, "zhang@example.com")
        self.assertEqual(mentor.profile, "专注大模型与信息检索")
        self.assertEqual(len(mentor.get_paper_id_list()), 1)

    def test_create_mentor_rejects_non_admin(self):
        response = self.post_json(
            "/dataset/mentors",
            {
                "Chinese_name": "张老师",
                "research_direction": "自然语言处理",
            },
            self.student_headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], 3)
        self.assertEqual(Mentor.objects.count(), 0)

    def test_update_mentor_success(self):
        Paper.objects.create(title="Paper", author_names="李老师")
        mentor = Mentor.objects.create(
            Chinese_name="张老师",
            English_name="Zhang",
            research_direction="自然语言处理",
            paper_ids="",
        )

        response = self.put_json(
            f"/dataset/mentors/{mentor.id}",
            {
                "Chinese_name": "李老师",
                "English_name": "Li",
                "research_direction": "计算机视觉",
                "email": "li@example.com",
                "profile": "CV",
            },
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)

        mentor.refresh_from_db()
        self.assertEqual(mentor.Chinese_name, "李老师")
        self.assertEqual(mentor.research_direction, "计算机视觉")
        self.assertIn("li@example.com", mentor.email)
        self.assertEqual(len(mentor.get_paper_id_list()), 1)

    def test_delete_mentor_success(self):
        mentor = Mentor.objects.create(
            Chinese_name="张老师",
            research_direction="自然语言处理",
            paper_ids="",
        )

        response = self.delete_json(f"/dataset/mentors/{mentor.id}", self.admin_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        self.assertFalse(Mentor.objects.filter(id=mentor.id).exists())

    def test_create_mentor_rejects_invalid_email(self):
        response = self.post_json(
            "/dataset/mentors",
            {
                "Chinese_name": "张老师",
                "research_direction": "自然语言处理",
                "email": "invalid-email",
            },
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(Mentor.objects.count(), 0)

    def test_detail_rejects_get(self):
        mentor_response = self.client.get("/dataset/mentors/1")
        paper_response = self.client.get("/dataset/papers/1")

        self.assertEqual(mentor_response.status_code, 405)
        self.assertEqual(mentor_response.json()["code"], -3)
        self.assertEqual(paper_response.status_code, 405)
        self.assertEqual(paper_response.json()["code"], -3)