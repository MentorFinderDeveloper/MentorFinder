import json

from django.contrib.auth.hashers import check_password
from django.test import TestCase

from account.models import User, MentorFollow
from dataset.models import Mentor
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
