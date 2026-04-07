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

    def test_create_mentor_get_method_not_allowed(self):
        response = self.client.get("/dataset/mentors")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)

    def test_create_mentor_rejects_empty_research_direction(self):
        response = self.post_json(
            "/dataset/mentors",
            {
                "Chinese_name": "张老师",
                "research_direction": "   ",
            },
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)

    def test_create_mentor_rejects_too_long_english_name(self):
        response = self.post_json(
            "/dataset/mentors",
            {
                "Chinese_name": "张老师",
                "English_name": "E" * 101,
                "research_direction": "自然语言处理",
            },
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)

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

    def test_update_mentor_not_found(self):
        response = self.put_json(
            "/dataset/mentors/99999",
            {
                "Chinese_name": "李老师",
                "research_direction": "计算机视觉",
            },
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 2)
        self.assertEqual(response.json()["info"], "Mentor not found")

    def test_update_mentor_rejects_invalid_email(self):
        mentor = Mentor.objects.create(
            Chinese_name="张老师",
            research_direction="自然语言处理",
            paper_ids="",
        )

        response = self.put_json(
            f"/dataset/mentors/{mentor.id}",
            {
                "Chinese_name": "张老师",
                "research_direction": "自然语言处理",
                "email": "bad-email",
            },
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)

    def test_update_mentor_rejects_too_long_research_direction(self):
        mentor = Mentor.objects.create(
            Chinese_name="张老师",
            research_direction="自然语言处理",
            paper_ids="",
        )

        response = self.put_json(
            f"/dataset/mentors/{mentor.id}",
            {
                "Chinese_name": "张老师",
                "research_direction": "x" * 256,
            },
            self.admin_headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)

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


class DatasetCrawlerServiceTests(SimpleTestCase):
    def test_fetch_html_uses_headers_and_returns_text(self):
        response = MagicMock()
        response.text = "<html>ok</html>"
        response.apparent_encoding = "utf-8"

        with patch("dataset.services.thu_crawler.requests.get", return_value=response) as mock_get:
            html = thu_crawler.fetch_html("https://example.com")

        mock_get.assert_called_once_with("https://example.com", headers=thu_crawler.BASE_HEADERS, timeout=15)
        response.raise_for_status.assert_called_once()
        self.assertEqual(response.encoding, "utf-8")
        self.assertEqual(html, "<html>ok</html>")

    def test_parse_mentor_list_uses_zip_and_urljoin(self):
        ch_html = """
        <html><body>
            <h2><a href="detail/zhang.htm">张三</a></h2>
            <h2><a href="detail/li.htm">李四</a></h2>
        </body></html>
        """
        en_html = """
        <html><body>
            <h2><a href="detail/zhang_en.htm">Zhang</a></h2>
        </body></html>
        """

        with patch("dataset.services.thu_crawler.fetch_html", side_effect=[ch_html, en_html]), patch(
            "dataset.services.thu_crawler.parse_mentor_detail",
            return_value={
                "Chinese_name": "张三",
                "English_name": "Zhang",
                "research_direction": "AI",
                "email": "zhang@example.com",
                "profile": "profile",
            },
        ) as mock_parse_detail:
            mentors = thu_crawler.parse_mentor_list(thu_crawler.url, thu_crawler.en_url)

        expected_ch_detail = urljoin(thu_crawler.url, "detail/zhang.htm")
        expected_en_detail = urljoin(thu_crawler.en_url, "detail/zhang_en.htm")
        mock_parse_detail.assert_called_once_with(expected_ch_detail, expected_en_detail)
        self.assertEqual(len(mentors), 1)

    def test_parse_mentor_detail_extracts_expected_fields(self):
        ch_detail_html = """
        <html>
            <head><title>张三-清华大学计算机系</title></head>
            <body>
                <p>研究领域</p>
                <p>自然语言处理</p>
                <p>信息检索</p>
                <h4>研究概况</h4>

                <p>邮箱：zhangsan@example.com</p>

                <p>教育背景</p>
                <p>清华博士</p>
                <p>学术成果</p>

                <p>研究概况</p>
                <p>专注大模型</p>
                <p>代表性论文</p>

                <p>奖励与荣誉</p>
                <p>国家奖学金</p>
                <p><strong>结束</strong></p>
            </body>
        </html>
        """
        en_detail_html = """
        <html>
            <head><title>Zhang San-Tsinghua University</title></head>
            <body></body>
        </html>
        """

        with patch("dataset.services.thu_crawler.fetch_html", side_effect=[ch_detail_html, en_detail_html]):
            detail = thu_crawler.parse_mentor_detail("https://example.com/ch", "https://example.com/en")

        self.assertEqual(detail["Chinese_name"], "张三")
        self.assertEqual(detail["English_name"], "Zhang San")
        self.assertIn("自然语言处理", detail["research_direction"])
        self.assertIn("信息检索", detail["research_direction"])
        self.assertEqual(detail["email"], "zhangsan@example.com")
        self.assertIn("教育背景", detail["profile"])
        self.assertIn("研究概况", detail["profile"])
        self.assertIn("奖励与荣誉", detail["profile"])

    def test_parse_mentor_detail_without_email_returns_none(self):
        ch_detail_html = """
        <html>
            <head><title>李四-清华大学计算机系</title></head>
            <body>
                <p>研究领域</p>
                <p>系统安全</p>
                <h4>研究概况</h4>
            </body>
        </html>
        """
        en_detail_html = """
        <html>
            <head><title>Li Si-Tsinghua University</title></head>
            <body></body>
        </html>
        """

        with patch("dataset.services.thu_crawler.fetch_html", side_effect=[ch_detail_html, en_detail_html]):
            detail = thu_crawler.parse_mentor_detail("https://example.com/ch", "https://example.com/en")

        self.assertEqual(detail["Chinese_name"], "李四")
        self.assertIsNone(detail["email"])


class DatasetImportMentorsCommandTests(TestCase):
    @patch("dataset.management.commands.import_mentors.parse_mentor_list")
    def test_import_mentors_creates_new_records(self, mock_parse_mentor_list):
        mock_parse_mentor_list.return_value = [
            {
                "Chinese_name": "张老师",
                "English_name": "Zhang",
                "research_direction": "自然语言处理",
                "email": "zhang@example.com",
                "profile": "导师画像",
            }
        ]

        out = StringIO()
        call_command("import_mentors", stdout=out)

        self.assertEqual(Mentor.objects.count(), 1)
        mentor = Mentor.objects.get(Chinese_name="张老师")
        self.assertEqual(mentor.English_name, "Zhang")
        self.assertEqual(mentor.research_direction, "自然语言处理")
        self.assertEqual(mentor.email, "zhang@example.com")
        self.assertIn("Imported 1 mentors", out.getvalue())

    @patch("dataset.management.commands.import_mentors.parse_mentor_list")
    def test_import_mentors_updates_existing_record(self, mock_parse_mentor_list):
        Mentor.objects.create(
            Chinese_name="王老师",
            English_name="Old Name",
            research_direction="Old Direction",
            email="old@example.com",
            profile="old",
            paper_ids="",
        )
        mock_parse_mentor_list.return_value = [
            {
                "Chinese_name": "王老师",
                "English_name": "New Name",
                "research_direction": "New Direction",
                "email": "new@example.com",
                "profile": "new",
            }
        ]

        call_command("import_mentors")

        self.assertEqual(Mentor.objects.filter(Chinese_name="王老师").count(), 1)
        mentor = Mentor.objects.get(Chinese_name="王老师")
        self.assertEqual(mentor.English_name, "New Name")
        self.assertEqual(mentor.research_direction, "New Direction")
        self.assertEqual(mentor.email, "new@example.com")
