import json
from io import StringIO
from urllib.parse import urljoin
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from account.models import User
from dataset.models import Mentor, Paper
from dataset.services import thu_crawler
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


class DatasetModelTest(TestCase):
    def test_get_author_list_handles_empty_and_spaces(self):
        paper = Paper.objects.create(title="Author Test", author_names="Alice, Bob ,  Carol")
        self.assertEqual(paper.get_author_list(), ["Alice", "Bob", "Carol"])

        empty_paper = Paper.objects.create(title="Empty Authors", author_names="")
        self.assertEqual(empty_paper.get_author_list(), [])

    def test_get_papers_preserves_id_order(self):
        p1 = Paper.objects.create(title="P1")
        p2 = Paper.objects.create(title="P2")
        mentor = Mentor.objects.create(
            Chinese_name="导师甲",
            research_direction="AI",
            paper_ids="",
        )
        mentor.set_paper_id_list([p2.id, p1.id])
        mentor.save()

        ordered_papers = mentor.get_papers()
        self.assertEqual([paper.id for paper in ordered_papers], [p2.id, p1.id])

    def test_remove_paper_updates_id_list(self):
        p1 = Paper.objects.create(title="P1")
        p2 = Paper.objects.create(title="P2")
        mentor = Mentor.objects.create(
            Chinese_name="导师乙",
            research_direction="NLP",
            paper_ids="",
        )
        mentor.set_paper_id_list([p1.id, p2.id])
        mentor.save()

        mentor.remove_paper(p1.id)
        mentor.refresh_from_db()
        self.assertEqual(mentor.get_paper_id_list(), [p2.id])

    def test_bind_to_mentors_by_authors_matches_english_name(self):
        mentor = Mentor.objects.create(
            Chinese_name="导师丙",
            English_name="Alan Turing",
            research_direction="Theory",
            paper_ids="",
        )
        paper = Paper.objects.create(title="Computability", author_names="Someone, Alan Turing")

        paper.bind_to_mentors_by_authors()
        mentor.refresh_from_db()
        self.assertIn(paper.id, mentor.get_paper_id_list())


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

    def test_create_paper_success_with_bare_token(self):
        response = self.post_json(
            "/dataset/papers",
            {
                "title": "Token Format Test",
                "abstract": "bare token auth",
                "author_names": "Alice",
            },
            {"HTTP_AUTHORIZATION": generate_jwt_token(self.admin_user.username)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        self.assertEqual(Paper.objects.count(), 1)

    def test_create_paper_rejects_invalid_token(self):
        response = self.post_json(
            "/dataset/papers",
            {"title": "X"},
            {"HTTP_AUTHORIZATION": "Bearer invalid-token"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], 2)
        self.assertEqual(response.json()["info"], "Unauthorized")

    def test_create_paper_rejects_token_user_not_found(self):
        response = self.post_json(
            "/dataset/papers",
            {"title": "X"},
            {"HTTP_AUTHORIZATION": f"Bearer {generate_jwt_token('ghost_user')}"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], 2)
        self.assertEqual(response.json()["info"], "User not found")

    def test_create_paper_get_method_not_allowed(self):
        response = self.client.get("/dataset/papers")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)

    def test_create_paper_rejects_empty_title(self):
        response = self.post_json(
            "/dataset/papers",
            {"title": "   ", "author_names": "A"},
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)

    def test_create_paper_rejects_too_long_title(self):
        response = self.post_json(
            "/dataset/papers",
            {"title": "a" * 256},
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)

    def test_create_paper_rejects_too_long_abstract(self):
        response = self.post_json(
            "/dataset/papers",
            {"title": "Valid Title", "abstract": "a" * 5001},
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)

    def test_create_paper_rejects_too_long_author_names(self):
        response = self.post_json(
            "/dataset/papers",
            {"title": "Valid Title", "author_names": "a" * 5001},
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)

    def test_create_paper_allows_missing_optional_fields(self):
        response = self.post_json(
            "/dataset/papers",
            {"title": "Only Title"},
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["paper"]
        self.assertIsNone(data["abstract"])
        self.assertIsNone(data["publish_date"])
        self.assertEqual(data["author_names"], "")

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

    def test_update_paper_not_found(self):
        response = self.put_json(
            "/dataset/papers/99999",
            {
                "title": "New Title",
                "author_names": "张三",
            },
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 2)
        self.assertEqual(response.json()["info"], "Paper not found")

    def test_delete_paper_requires_admin(self):
        paper = Paper.objects.create(title="Need Auth")

        response = self.delete_json(f"/dataset/papers/{paper.id}")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], 2)
        self.assertTrue(Paper.objects.filter(id=paper.id).exists())

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

