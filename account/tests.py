import json
from datetime import date
from unittest.mock import patch

from django.contrib.auth.hashers import check_password
from django.test import TestCase

from account.models import User, MentorFollow
from account.services.weekly_push import (
    build_weekly_push_digest,
    render_weekly_push_email,
    send_weekly_push_email,
)
from dataset.models import Mentor, Paper
from utils.utils_jwt import generate_jwt_token


class AccountAuthTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="Ashitemaru", password="abc12345", email="ashitemaru@example.com")

    def post_json(self, path: str, payload: dict):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def test_login_existing_user_correct_password(self):
        res = self.post_json("/login", {"username": "Ashitemaru", "password": "abc12345"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(res.json()["token"].count(".") == 2)
        self.assertEqual(res.json()["role"], "student")

    def test_login_with_email_correct_password(self):
        res = self.post_json("/login", {"username": "ashitemaru@example.com", "password": "abc12345"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(res.json()["token"].count(".") == 2)
        self.assertEqual(res.json()["role"], "student")

    def test_login_non_existing_user(self):
        res = self.post_json("/login", {"username": "NewUser", "password": "abc12345"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)
        self.assertEqual(res.json()["info"], "User not found")

    def test_login_wrong_password(self):
        res = self.post_json("/login", {"username": "Ashitemaru", "password": "wrongpassword"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)
        self.assertEqual(res.json()["info"], "Wrong password")

    def test_login_with_email_wrong_password(self):
        res = self.post_json("/login", {"username": "ashitemaru@example.com", "password": "wrongpassword"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)
        self.assertEqual(res.json()["info"], "Wrong password")

    def test_register_success(self):
        res = self.post_json(
            "/register",
            {"username": "NewUser", "password": "abc12345", "email": "newuser@example.com"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(res.json()["token"].count(".") == 2)
        self.assertEqual(res.json()["role"], "student")
        user = User.objects.filter(username="NewUser", email="newuser@example.com").first()
        self.assertIsNotNone(user)
        self.assertNotEqual(user.password, "abc12345")
        self.assertTrue(check_password("abc12345", user.password))

    def test_register_success_with_underscore_and_hyphen_username(self):
        res = self.post_json(
            "/register",
            {"username": "new_user-1", "password": "abc12345", "email": "new-user@example.com"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(User.objects.filter(username="new_user-1", email="new-user@example.com").exists())

    def test_register_invalid_username_characters(self):
        res = self.post_json(
            "/register",
            {"username": "Bad User!", "password": "abc12345", "email": "baduser@example.com"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertFalse(User.objects.filter(email="baduser@example.com").exists())

    def test_register_password_too_short(self):
        res = self.post_json(
            "/register",
            {"username": "ShortPwdUser", "password": "ab123", "email": "shortpwd@example.com"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_register_password_without_digit(self):
        res = self.post_json(
            "/register",
            {"username": "NoDigitUser", "password": "abcdefgh", "email": "nodigit@example.com"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_register_password_without_letter(self):
        res = self.post_json(
            "/register",
            {"username": "NoLetterUser", "password": "12345678", "email": "noletter@example.com"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_register_missing_email(self):
        res = self.post_json("/register", {"username": "NewUser", "password": "abc12345"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_register_invalid_email(self):
        res = self.post_json(
            "/register",
            {"username": "NewUser", "password": "abc12345", "email": "not-an-email"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_register_invalid_email_without_valid_domain(self):
        res = self.post_json(
            "/register",
            {"username": "AnotherNewUser", "password": "abc12345", "email": "user@invalid"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_register_valid_email_with_plus_tag(self):
        res = self.post_json(
            "/register",
            {"username": "PlusTagUser", "password": "abc12345", "email": "user+tag@example.com"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)

    def test_register_email_with_surrounding_spaces(self):
        res = self.post_json(
            "/register",
            {"username": "TrimEmailUser", "password": "abc12345", "email": "  trim@example.com  "},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(User.objects.filter(username="TrimEmailUser", email="trim@example.com").exists())

    def test_register_invalid_email_double_at(self):
        res = self.post_json(
            "/register",
            {"username": "BadEmailUser", "password": "abc12345", "email": "user@@example.com"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_register_duplicate_username(self):
        res = self.post_json(
            "/register",
            {"username": "Ashitemaru", "password": "abc12345", "email": "new@example.com"},
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], 3)

    def test_register_duplicate_email(self):
        res = self.post_json(
            "/register",
            {"username": "AnotherUser", "password": "abc12345", "email": "ashitemaru@example.com"},
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], 4)

    def test_login_bad_method(self):
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    def test_register_bad_method(self):
        res = self.client.get("/register")
        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)


class MentorFollowViewTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student1",
            email="student1@example.com",
            password="abc12345",
            role="student",
        )
        self.student_token = generate_jwt_token("student1")

        self.other_student = User.objects.create_user(
            username="student2",
            email="student2@example.com",
            password="abc12345",
            role="student",
        )
        self.other_student_token = generate_jwt_token("student2")

        self.admin = User.objects.create_user(
            username="admin1",
            email="admin1@example.com",
            password="abc12345",
            role="admin",
        )
        self.admin_token = generate_jwt_token("admin1")

        self.mentor = Mentor.objects.create(
            Chinese_name="张三",
            English_name="Zhang San",
            research_direction="机器学习",
            email="zhangsan@example.com",
            profile="主要研究机器学习。",
        )

        self.other_mentor = Mentor.objects.create(
            Chinese_name="李四",
            English_name="Li Si",
            research_direction="自然语言处理",
            email="lisi@example.com",
            profile="主要研究自然语言处理。",
        )

        self.private_mentor = Mentor.objects.create(
            Chinese_name="王五",
            English_name="Wang Wu",
            research_direction="强化学习",
            email="wangwu@example.com",
            profile="私有导师",
            owner=self.other_student,
        )

    def auth_headers(self, token: str):
        return {
            "HTTP_AUTHORIZATION": f"Bearer {token}",
        }

    def test_student_can_follow_mentor(self):
        res = self.client.post(
            f"/follow/mentors/{self.mentor.id}",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["followed"], True)
        self.assertTrue(
            MentorFollow.objects.filter(
                student=self.student,
                mentor=self.mentor,
            ).exists()
        )

    def test_follow_mentor_requires_login(self):
        res = self.client.post(f"/follow/mentors/{self.mentor.id}")

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)

    def test_only_student_can_follow_mentor(self):
        res = self.client.post(
            f"/follow/mentors/{self.mentor.id}",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], 3)
        self.assertFalse(
            MentorFollow.objects.filter(
                student=self.admin,
                mentor=self.mentor,
            ).exists()
        )

    def test_follow_non_existing_mentor_returns_404(self):
        res = self.client.post(
            "/follow/mentors/999999",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["code"], 2)
        self.assertEqual(res.json()["info"], "Mentor not found")

    def test_student_cannot_follow_other_students_private_mentor(self):
        res = self.client.post(
            f"/follow/mentors/{self.private_mentor.id}",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["code"], 2)
        self.assertFalse(
            MentorFollow.objects.filter(
                student=self.student,
                mentor=self.private_mentor,
            ).exists()
        )

    def test_duplicate_follow_is_idempotent(self):
        first_res = self.client.post(
            f"/follow/mentors/{self.mentor.id}",
            **self.auth_headers(self.student_token),
        )
        second_res = self.client.post(
            f"/follow/mentors/{self.mentor.id}",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(first_res.status_code, 200)
        self.assertEqual(second_res.status_code, 200)
        self.assertEqual(
            MentorFollow.objects.filter(
                student=self.student,
                mentor=self.mentor,
            ).count(),
            1,
        )

    def test_student_can_unfollow_mentor(self):
        MentorFollow.objects.create(
            student=self.student,
            mentor=self.mentor,
        )

        res = self.client.delete(
            f"/follow/mentors/{self.mentor.id}",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["followed"], False)
        self.assertFalse(
            MentorFollow.objects.filter(
                student=self.student,
                mentor=self.mentor,
            ).exists()
        )

    def test_unfollow_not_followed_mentor_is_ok(self):
        res = self.client.delete(
            f"/follow/mentors/{self.mentor.id}",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["followed"], False)

    def test_get_followed_mentors_requires_login(self):
        res = self.client.get("/follow/mentors")

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)

    def test_get_followed_mentors_returns_current_students_follows(self):
        MentorFollow.objects.create(
            student=self.student,
            mentor=self.mentor,
        )
        MentorFollow.objects.create(
            student=self.student,
            mentor=self.other_mentor,
        )
        MentorFollow.objects.create(
            student=self.other_student,
            mentor=self.other_mentor,
        )

        res = self.client.get(
            "/follow/mentors",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)

        mentors = res.json()["mentors"]
        mentor_names = {mentor["Chinese_name"] for mentor in mentors}

        self.assertEqual(mentor_names, {"张三", "李四"})
        self.assertEqual(len(mentors), 2)

    def test_get_followed_mentors_returns_empty_list(self):
        res = self.client.get(
            "/follow/mentors",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["mentors"], [])

    def test_follow_mentor_bad_method(self):
        res = self.client.get(
            f"/follow/mentors/{self.mentor.id}",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    def test_followed_mentors_bad_method(self):
        res = self.client.post(
            "/follow/mentors",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)


class UserProfileViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profile_user",
            email="profile_user@example.com",
            password="abc12345",
            role="student",
        )
        self.token = generate_jwt_token("profile_user")

    def auth_headers(self, token: str):
        return {
            "HTTP_AUTHORIZATION": f"Bearer {token}",
        }

    def test_get_profile_requires_login(self):
        res = self.client.get("/profile/me")

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)

    def test_get_profile_returns_default_profile(self):
        res = self.client.get(
            "/profile/me",
            **self.auth_headers(self.token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["profile"]["researchExperience"], "")
        self.assertEqual(res.json()["profile"]["honors"], "")
        self.assertEqual(res.json()["profile"]["projectExperience"], "")

    def test_put_profile_updates_fields(self):
        res = self.client.put(
            "/profile/me",
            data=json.dumps(
                {
                    "researchExperience": "发表2篇CCF论文",
                    "honors": "国家奖学金",
                    "projectExperience": "参与导师课题系统开发",
                }
            ),
            content_type="application/json",
            **self.auth_headers(self.token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["profile"]["researchExperience"], "发表2篇CCF论文")
        self.assertEqual(res.json()["profile"]["honors"], "国家奖学金")
        self.assertEqual(res.json()["profile"]["projectExperience"], "参与导师课题系统开发")

    def test_put_profile_rejects_non_string_field(self):
        res = self.client.put(
            "/profile/me",
            data=json.dumps(
                {
                    "researchExperience": ["wrong type"],
                    "honors": "ok",
                    "projectExperience": "ok",
                }
            ),
            content_type="application/json",
            **self.auth_headers(self.token),
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_profile_bad_method(self):
        res = self.client.post(
            "/profile/me",
            data=json.dumps({}),
            content_type="application/json",
            **self.auth_headers(self.token),
        )

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)


class WeeklyPushDigestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="digest_user",
            email="digest_user@example.com",
            password="abc12345",
            role="student",
        )
        self.other_user = User.objects.create_user(
            username="other_digest_user",
            email="other_digest_user@example.com",
            password="abc12345",
            role="student",
        )

        self.followed_mentor = Mentor.objects.create(
            Chinese_name="张三",
            English_name="Zhang San",
            research_direction="机器学习",
        )
        self.private_mentor = Mentor.objects.create(
            Chinese_name="李四",
            English_name="Li Si",
            research_direction="自然语言处理",
            owner=self.user,
        )
        self.unrelated_mentor = Mentor.objects.create(
            Chinese_name="王五",
            English_name="Wang Wu",
            research_direction="数据库",
            owner=self.other_user,
        )

        MentorFollow.objects.create(student=self.user, mentor=self.followed_mentor)
        MentorFollow.objects.create(student=self.user, mentor=self.private_mentor)

        self.followed_paper = Paper.objects.create(
            title="机器学习方法研究",
            abstract="第一行摘要\n第二行摘要\n第三行摘要\n第四行摘要",
            publish_date=date(2026, 4, 16),
            author_names="张三, Alice",
            subjects="cs.LG, cs.AI",
        )
        self.private_paper = Paper.objects.create(
            title="大语言模型在问答系统中的应用",
            abstract="私有导师论文摘要",
            publish_date=date(2026, 4, 17),
            author_names="李四, Bob",
            subjects="cs.CL",
        )
        self.unrelated_paper = Paper.objects.create(
            title="不应推送的论文",
            abstract="无关摘要",
            publish_date=date(2026, 4, 18),
            author_names="王五",
            subjects="cs.DB",
        )

        self.followed_mentor.add_paper(self.followed_paper.id)
        self.private_mentor.add_paper(self.private_paper.id)
        self.unrelated_mentor.add_paper(self.unrelated_paper.id)

    def test_build_weekly_digest_groups_followed_and_private_mentor_papers(self):
        digest = build_weekly_push_digest(
            self.user,
            [
                [self.followed_paper],
                [],
                [self.private_paper, self.unrelated_paper],
                [],
                [self.followed_paper],
                [],
                [],
            ],
        )

        self.assertEqual(digest["hasUpdates"], True)
        self.assertEqual(digest["totalPaperCount"], 2)
        self.assertEqual(
            digest["title"],
            "[MentorFinder]你关注的导师本周有 2 篇新论文",
        )

        mentor_names = {
            group["mentorName"]
            for group in digest["mentorGroups"]
        }
        self.assertEqual(mentor_names, {"张三", "李四"})
        self.assertEqual(len(digest["mentorGroups"]), 2)

        all_paper_titles = {
            paper["title"]
            for group in digest["mentorGroups"]
            for paper in group["papers"]
        }
        self.assertEqual(
            all_paper_titles,
            {"机器学习方法研究", "大语言模型在问答系统中的应用"},
        )

        followed_group = next(
            group
            for group in digest["mentorGroups"]
            if group["mentorName"] == "张三"
        )
        followed_paper = followed_group["papers"][0]
        self.assertEqual(
            followed_paper["abstractPreview"],
            "第一行摘要\n第二行摘要\n第三行摘要",
        )
        self.assertEqual(followed_paper["subjects"], ["cs.LG", "cs.AI"])

    def test_build_weekly_digest_deduplicates_private_mentor_follow(self):
        digest = build_weekly_push_digest(
            self.user,
            [
                [self.private_paper],
                [self.private_paper],
                [],
                [],
                [],
                [],
                [],
            ],
        )

        private_groups = [
            group
            for group in digest["mentorGroups"]
            if group["mentorName"] == "李四"
        ]
        self.assertEqual(len(private_groups), 1)
        self.assertEqual(private_groups[0]["paperCount"], 1)
        self.assertEqual(digest["totalPaperCount"], 1)

    def test_build_weekly_digest_counts_subject_distribution(self):
        digest = build_weekly_push_digest(
            self.user,
            [
                [self.followed_paper, self.private_paper],
                [],
                [],
                [],
                [],
                [],
                [],
            ],
        )

        self.assertEqual(
            digest["subjectDistribution"],
            [
                {"subject": "cs.AI", "count": 1},
                {"subject": "cs.CL", "count": 1},
                {"subject": "cs.LG", "count": 1},
            ],
        )

    def test_build_weekly_digest_returns_empty_summary_without_updates(self):
        digest = build_weekly_push_digest(
            self.user,
            [
                [self.unrelated_paper],
                [],
                [],
                [],
                [],
                [],
                [],
            ],
        )

        self.assertEqual(digest["hasUpdates"], False)
        self.assertEqual(digest["title"], "[MentorFinder]本周无论文更新")
        self.assertEqual(digest["summary"], "本周无论文更新")
        self.assertEqual(digest["totalPaperCount"], 0)
        self.assertEqual(digest["mentorGroups"], [])
        self.assertEqual(digest["subjectDistribution"], [])

    def test_render_weekly_push_email_includes_digest_sections(self):
        digest = build_weekly_push_digest(
            self.user,
            [
                [self.followed_paper],
                [self.private_paper],
                [],
                [],
                [],
                [],
                [],
            ],
        )

        email_content = render_weekly_push_email(digest)

        self.assertEqual(
            email_content["subject"],
            "[MentorFinder]你关注的导师本周有 2 篇新论文",
        )
        self.assertIn("按导师分组：", email_content["body"])
        self.assertIn("- 张三：1 篇", email_content["body"])
        self.assertIn("- 李四（私有导师）：1 篇", email_content["body"])
        self.assertIn("1. 机器学习方法研究", email_content["body"])
        self.assertIn("1. 大语言模型在问答系统中的应用", email_content["body"])
        self.assertIn("分类：cs.LG, cs.AI", email_content["body"])
        self.assertIn("研究方向分布：", email_content["body"])
        self.assertIn("- cs.AI：1 篇", email_content["body"])
        self.assertIn("- cs.CL：1 篇", email_content["body"])

    def test_render_weekly_push_email_without_updates(self):
        digest = build_weekly_push_digest(
            self.user,
            [
                [self.unrelated_paper],
                [],
                [],
                [],
                [],
                [],
                [],
            ],
        )

        email_content = render_weekly_push_email(digest)

        self.assertEqual(email_content["subject"], "[MentorFinder]本周无论文更新")
        self.assertIn("本周无论文更新", email_content["body"])
        self.assertIn(
            "系统当前未检测到你关注的导师或私有导师有新增论文。",
            email_content["body"],
        )

    @patch("account.services.weekly_push.send_mail")
    def test_send_weekly_push_email_sends_rendered_digest(self, mock_send_mail):
        mock_send_mail.return_value = 1

        result = send_weekly_push_email(
            self.user,
            [
                [self.followed_paper],
                [self.private_paper],
                [],
                [],
                [],
                [],
                [],
            ],
        )

        self.assertEqual(result["sent"], True)
        self.assertEqual(result["sentCount"], 1)
        self.assertEqual(result["digest"]["totalPaperCount"], 2)
        self.assertIn("机器学习方法研究", result["email"]["body"])

        mock_send_mail.assert_called_once()
        send_kwargs = mock_send_mail.call_args.kwargs
        self.assertEqual(
            send_kwargs["subject"],
            "[MentorFinder]你关注的导师本周有 2 篇新论文",
        )
        self.assertEqual(send_kwargs["recipient_list"], ["digest_user@example.com"])
        self.assertEqual(send_kwargs["fail_silently"], False)
        self.assertIn("大语言模型在问答系统中的应用", send_kwargs["message"])

    @patch("account.services.weekly_push.send_mail")
    def test_send_weekly_push_email_reports_send_failure(self, mock_send_mail):
        mock_send_mail.return_value = 0

        result = send_weekly_push_email(
            self.user,
            [
                [self.unrelated_paper],
                [],
                [],
                [],
                [],
                [],
                [],
            ],
        )

        self.assertEqual(result["sent"], False)
        self.assertEqual(result["sentCount"], 0)
        self.assertEqual(result["digest"]["hasUpdates"], False)
        mock_send_mail.assert_called_once()
