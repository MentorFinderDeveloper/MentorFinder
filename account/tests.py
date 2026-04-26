import json
import tempfile
from io import StringIO
from datetime import date
from unittest.mock import patch
from pathlib import Path

from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from account.models import MentorVerificationRequest, User, MentorFollow
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
        User.objects.create_user(
            username="banned_user",
            password="abc12345",
            email="banned@example.com",
            role=User.ROLE_BANNED,
        )

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

    def test_login_banned_user_rejected(self):
        res = self.post_json("/login", {"username": "banned_user", "password": "abc12345"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], 3)
        self.assertEqual(res.json()["info"], "User is banned")

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
        self.assertIsNone(res.json()["mentorVerificationRequest"])

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

    def test_student_can_submit_mentor_verification_request(self):
        res = self.client.post(
            "/profile/mentor-verification-request",
            data=json.dumps({
                "submittedName": "张老师",
            }),
            content_type="application/json",
            **self.auth_headers(self.token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["mentorVerificationRequest"]["submittedName"], "张老师")
        self.assertTrue(
            MentorVerificationRequest.objects.filter(
                user=self.user,
                submitted_name="张老师",
                status=MentorVerificationRequest.STATUS_PENDING,
            ).exists()
        )

    def test_cannot_submit_duplicate_pending_mentor_verification_request(self):
        MentorVerificationRequest.objects.create(
            user=self.user,
            submitted_name="张老师",
            status=MentorVerificationRequest.STATUS_PENDING,
        )

        res = self.client.post(
            "/profile/mentor-verification-request",
            data=json.dumps({
                "submittedName": "李老师",
            }),
            content_type="application/json",
            **self.auth_headers(self.token),
        )

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], 3)
        self.assertEqual(res.json()["info"], "A pending mentor verification request already exists")


class AdminUserManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_manager",
            email="admin_manager@example.com",
            password="abc12345",
            role=User.ROLE_ADMIN,
        )
        self.admin_token = generate_jwt_token("admin_manager")

        self.student = User.objects.create_user(
            username="managed_student",
            email="managed_student@example.com",
            password="abc12345",
            role=User.ROLE_STUDENT,
        )
        self.student_token = generate_jwt_token("managed_student")

        self.public_mentor = Mentor.objects.create(
            Chinese_name="公共导师",
            English_name="Public Mentor",
            research_direction="机器学习",
            email="mentor@example.com",
            profile="公共导师档案",
        )

    def auth_headers(self, token: str):
        return {
            "HTTP_AUTHORIZATION": f"Bearer {token}",
        }

    def test_admin_can_list_users(self):
        res = self.client.get(
            "/management/users",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        usernames = {user["username"] for user in res.json()["users"]}
        self.assertIn("admin_manager", usernames)
        self.assertIn("managed_student", usernames)

    def test_non_admin_cannot_list_users(self):
        res = self.client.get(
            "/management/users",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], 3)

    def test_admin_can_promote_student_to_admin(self):
        res = self.client.put(
            f"/management/users/{self.student.id}",
            data=json.dumps({"role": User.ROLE_ADMIN}),
            content_type="application/json",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.ROLE_ADMIN)
        self.assertIsNone(self.student.mentor_profile)

    def test_admin_can_bind_public_mentor_and_set_role_to_mentor(self):
        res = self.client.put(
            f"/management/users/{self.student.id}",
            data=json.dumps({"role": User.ROLE_MENTOR, "mentorId": self.public_mentor.id}),
            content_type="application/json",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.ROLE_MENTOR)
        self.assertEqual(self.student.mentor_profile_id, self.public_mentor.id)
        self.assertEqual(res.json()["user"]["mentorProfile"]["id"], self.public_mentor.id)

    def test_mentor_role_requires_public_mentor_binding(self):
        res = self.client.put(
            f"/management/users/{self.student.id}",
            data=json.dumps({"role": User.ROLE_MENTOR}),
            content_type="application/json",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], 3)
        self.assertEqual(res.json()["info"], "Mentor binding is required for mentor role")

    def test_non_mentor_role_cannot_bind_mentor_profile(self):
        res = self.client.put(
            f"/management/users/{self.student.id}",
            data=json.dumps({"role": User.ROLE_STUDENT, "mentorId": self.public_mentor.id}),
            content_type="application/json",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], 3)
        self.assertEqual(res.json()["info"], "Only mentor role can bind a mentor profile")

    def test_admin_can_ban_user(self):
        res = self.client.put(
            f"/management/users/{self.student.id}",
            data=json.dumps({"role": User.ROLE_BANNED}),
            content_type="application/json",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.ROLE_BANNED)
        self.assertIsNone(self.student.mentor_profile)

    def test_banned_user_cannot_access_profile(self):
        self.student.role = User.ROLE_BANNED
        self.student.save(update_fields=["role"])

        res = self.client.get(
            "/profile/me",
            **self.auth_headers(self.student_token),
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], 3)
        self.assertEqual(res.json()["info"], "User is banned")

    def test_admin_cannot_ban_self(self):
        res = self.client.put(
            f"/management/users/{self.admin.id}",
            data=json.dumps({"role": User.ROLE_BANNED}),
            content_type="application/json",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], 3)
        self.assertEqual(res.json()["info"], "Admin cannot ban self")

    def test_admin_can_search_users_by_email_and_real_name(self):
        self.student.real_name = "张同学"
        self.student.save(update_fields=["real_name"])

        email_res = self.client.get(
            "/management/users",
            {"keyword": "managed_student@example.com"},
            **self.auth_headers(self.admin_token),
        )
        self.assertEqual(email_res.status_code, 200)
        self.assertEqual(
            [user["username"] for user in email_res.json()["users"]],
            ["managed_student"],
        )

        real_name_res = self.client.get(
            "/management/users",
            {"keyword": "张同学"},
            **self.auth_headers(self.admin_token),
        )
        self.assertEqual(real_name_res.status_code, 200)
        self.assertEqual(
            [user["username"] for user in real_name_res.json()["users"]],
            ["managed_student"],
        )

    def test_admin_can_filter_users_by_role(self):
        mentor_user = User.objects.create_user(
            username="mentor_user",
            email="mentor_user@example.com",
            password="abc12345",
            role=User.ROLE_MENTOR,
            mentor_profile=self.public_mentor,
        )

        res = self.client.get(
            "/management/users",
            {"role": User.ROLE_MENTOR},
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["roleFilter"], User.ROLE_MENTOR)
        self.assertEqual(
            [user["username"] for user in res.json()["users"]],
            [mentor_user.username],
        )

    def test_admin_can_view_verification_request_list(self):
        request_obj = MentorVerificationRequest.objects.create(
            user=self.student,
            submitted_name="待认证导师姓名",
            status=MentorVerificationRequest.STATUS_PENDING,
        )

        res = self.client.get(
            "/management/users",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        verification_requests = res.json()["verificationRequests"]
        self.assertEqual(len(verification_requests), 1)
        self.assertEqual(verification_requests[0]["id"], request_obj.id)
        self.assertEqual(verification_requests[0]["username"], "managed_student")
        self.assertEqual(verification_requests[0]["submittedName"], "待认证导师姓名")
        self.assertEqual(verification_requests[0]["status"], MentorVerificationRequest.STATUS_PENDING)

    def test_admin_can_approve_verification_request_with_public_mentor_binding(self):
        request_obj = MentorVerificationRequest.objects.create(
            user=self.student,
            submitted_name="待认证导师姓名",
            status=MentorVerificationRequest.STATUS_PENDING,
        )

        res = self.client.put(
            f"/management/verification-requests/{request_obj.id}",
            data=json.dumps({
                "status": MentorVerificationRequest.STATUS_APPROVED,
                "mentorId": self.public_mentor.id,
            }),
            content_type="application/json",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        request_obj.refresh_from_db()
        self.student.refresh_from_db()
        self.assertEqual(request_obj.status, MentorVerificationRequest.STATUS_APPROVED)
        self.assertEqual(self.student.role, User.ROLE_MENTOR)
        self.assertEqual(self.student.mentor_profile_id, self.public_mentor.id)

    def test_approving_verification_request_requires_public_mentor_binding(self):
        request_obj = MentorVerificationRequest.objects.create(
            user=self.student,
            submitted_name="待认证导师姓名",
            status=MentorVerificationRequest.STATUS_PENDING,
        )

        res = self.client.put(
            f"/management/verification-requests/{request_obj.id}",
            data=json.dumps({
                "status": MentorVerificationRequest.STATUS_APPROVED,
            }),
            content_type="application/json",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], 3)
        self.assertEqual(res.json()["info"], "Mentor binding is required for approval")

    def test_admin_can_reject_verification_request(self):
        request_obj = MentorVerificationRequest.objects.create(
            user=self.student,
            submitted_name="待认证导师姓名",
            status=MentorVerificationRequest.STATUS_PENDING,
        )

        res = self.client.put(
            f"/management/verification-requests/{request_obj.id}",
            data=json.dumps({
                "status": MentorVerificationRequest.STATUS_REJECTED,
            }),
            content_type="application/json",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        request_obj.refresh_from_db()
        self.student.refresh_from_db()
        self.assertEqual(request_obj.status, MentorVerificationRequest.STATUS_REJECTED)
        self.assertEqual(self.student.role, User.ROLE_STUDENT)
        self.assertIsNone(self.student.mentor_profile)

    def test_cannot_review_verification_request_twice(self):
        request_obj = MentorVerificationRequest.objects.create(
            user=self.student,
            submitted_name="待认证导师姓名",
            status=MentorVerificationRequest.STATUS_APPROVED,
        )

        res = self.client.put(
            f"/management/verification-requests/{request_obj.id}",
            data=json.dumps({
                "status": MentorVerificationRequest.STATUS_REJECTED,
            }),
            content_type="application/json",
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], 3)
        self.assertEqual(res.json()["info"], "Verification request has already been reviewed")


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


class MockWeeklyPushCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="command_user",
            email="command_user@example.com",
            password="abc12345",
            role="student",
        )
        self.other_user = User.objects.create_user(
            username="other_command_user",
            email="other_command_user@example.com",
            password="abc12345",
            role="student",
        )
        self.mentor = Mentor.objects.create(
            Chinese_name="周报导师",
            English_name="Weekly Mentor",
            research_direction="机器学习",
        )
        MentorFollow.objects.create(student=self.user, mentor=self.mentor)

        self.paper = Paper.objects.create(
            title="周报命令测试论文",
            abstract="命令测试摘要",
            publish_date=date(2026, 4, 15),
            author_names="周报导师",
            subjects="cs.LG",
        )
        self.mentor.add_paper(self.paper.id)

    @patch("account.management.commands.send_weekly_push_mock.send_weekly_push_email")
    def test_mock_weekly_push_command_sends_to_users(self, mock_send_weekly_push_email):
        mock_send_weekly_push_email.return_value = {
            "sent": True,
            "digest": {
                "totalPaperCount": 1,
            },
        }
        out = StringIO()

        call_command("send_weekly_push_mock", stdout=out)

        self.assertEqual(mock_send_weekly_push_email.call_count, 2)
        called_users = {
            call.args[0].username
            for call in mock_send_weekly_push_email.call_args_list
        }
        self.assertEqual(called_users, {"command_user", "other_command_user"})
        self.assertIn("Prepared 7 mocked daily paper lists with 1 papers.", out.getvalue())
        self.assertIn("command_user: sent, 1 matched paper(s).", out.getvalue())

    @patch("account.management.commands.send_weekly_push_mock.send_weekly_push_email")
    def test_mock_weekly_push_command_filters_by_username(self, mock_send_weekly_push_email):
        mock_send_weekly_push_email.return_value = {
            "sent": True,
            "digest": {
                "totalPaperCount": 1,
            },
        }

        call_command("send_weekly_push_mock", "--user", "command_user", stdout=StringIO())

        mock_send_weekly_push_email.assert_called_once()
        self.assertEqual(mock_send_weekly_push_email.call_args.args[0].username, "command_user")

    @patch("account.management.commands.send_weekly_push_mock.send_weekly_push_email")
    def test_mock_weekly_push_command_dry_run_does_not_send(self, mock_send_weekly_push_email):
        out = StringIO()

        call_command("send_weekly_push_mock", "--dry-run", stdout=out)

        mock_send_weekly_push_email.assert_not_called()
        self.assertIn("[DRY RUN] command_user: 1 matched paper(s).", out.getvalue())

    @patch("account.management.commands.send_weekly_push_mock.send_weekly_push_email")
    def test_mock_weekly_push_command_loads_papers_from_json_file(self, mock_send_weekly_push_email):
        mock_send_weekly_push_email.return_value = {
            "sent": True,
            "digest": {
                "totalPaperCount": 1,
            },
        }

        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as fp:
            json.dump(
                {
                    "thursday": [self.paper.id],
                    "friday": [],
                    "saturday": [],
                    "sunday": [],
                    "monday": [],
                    "tuesday": [],
                    "wednesday": [],
                },
                fp,
            )
            file_path = fp.name

        call_command(
            "send_weekly_push_mock",
            "--user",
            "command_user",
            "--paper-file",
            file_path,
            stdout=StringIO(),
        )

        mock_send_weekly_push_email.assert_called_once()
        passed_lists = mock_send_weekly_push_email.call_args.args[1]
        self.assertEqual(len(passed_lists), 7)
        self.assertEqual([paper.id for paper in passed_lists[0]], [self.paper.id])
        self.assertEqual(passed_lists[1], [])

    def test_mock_weekly_push_command_rejects_missing_paper_file(self):
        with self.assertRaises(CommandError):
            call_command(
                "send_weekly_push_mock",
                "--paper-file",
                "/tmp/not-found-weekly-papers.json",
                stdout=StringIO(),
            )


class WeeklyPushCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="weekly_user",
            email="weekly_user@example.com",
            password="abc12345",
            role="student",
        )
        self.other_user = User.objects.create_user(
            username="other_weekly_user",
            email="other_weekly_user@example.com",
            password="abc12345",
            role="student",
        )
        self.mentor = Mentor.objects.create(
            Chinese_name="正式周报导师",
            English_name="Formal Weekly Mentor",
            research_direction="自然语言处理",
        )
        MentorFollow.objects.create(student=self.user, mentor=self.mentor)
        self.paper = Paper.objects.create(
            title="正式周报论文",
            abstract="正式周报摘要",
            publish_date=date(2026, 4, 22),
            author_names="正式周报导师",
            subjects="cs.CL",
        )
        self.mentor.add_paper(self.paper.id)

    @patch("account.management.commands.send_weekly_push.send_weekly_push_email")
    def test_weekly_push_command_sends_and_resets_after_archive(self, mock_send_weekly_push_email):
        mock_send_weekly_push_email.return_value = {
            "sent": True,
            "digest": {
                "totalPaperCount": 1,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            paper_file = Path(tmpdir) / "weekly_papers.json"
            archive_dir = Path(tmpdir) / "archive"
            with paper_file.open("w", encoding="utf-8") as fp:
                json.dump(
                    {
                        "thursday": [self.paper.id],
                        "friday": [],
                        "saturday": [],
                        "sunday": [],
                        "monday": [],
                        "tuesday": [],
                        "wednesday": [],
                    },
                    fp,
                )

            out = StringIO()
            call_command(
                "send_weekly_push",
                "--paper-file",
                str(paper_file),
                "--archive-dir",
                str(archive_dir),
                stdout=out,
            )

            self.assertEqual(mock_send_weekly_push_email.call_count, 2)
            archive_files = list(archive_dir.glob("weekly_push_*.json"))
            self.assertEqual(len(archive_files), 1)

            with archive_files[0].open("r", encoding="utf-8") as fp:
                archive_payload = json.load(fp)
            self.assertEqual(archive_payload["thursday"], [self.paper.id])

            with paper_file.open("r", encoding="utf-8") as fp:
                reset_payload = json.load(fp)
            self.assertTrue(all(day_payload == [] for day_payload in reset_payload.values()))

            self.assertIn("Loaded 7 recorded daily paper lists with 1 paper ID(s).", out.getvalue())
            self.assertIn("Archived weekly push paper records", out.getvalue())

    @patch("account.management.commands.send_weekly_push.send_weekly_push_email")
    def test_weekly_push_command_dry_run_keeps_weekly_file(self, mock_send_weekly_push_email):
        with tempfile.TemporaryDirectory() as tmpdir:
            paper_file = Path(tmpdir) / "weekly_papers.json"
            archive_dir = Path(tmpdir) / "archive"
            original_payload = {
                "thursday": [self.paper.id],
                "friday": [],
                "saturday": [],
                "sunday": [],
                "monday": [],
                "tuesday": [],
                "wednesday": [],
            }
            with paper_file.open("w", encoding="utf-8") as fp:
                json.dump(original_payload, fp)

            out = StringIO()
            call_command(
                "send_weekly_push",
                "--paper-file",
                str(paper_file),
                "--archive-dir",
                str(archive_dir),
                "--dry-run",
                stdout=out,
            )

            mock_send_weekly_push_email.assert_not_called()
            with paper_file.open("r", encoding="utf-8") as fp:
                current_payload = json.load(fp)
            self.assertEqual(current_payload, original_payload)
            self.assertFalse(archive_dir.exists())
            self.assertIn("[DRY RUN] weekly_user: 1 matched paper(s).", out.getvalue())

    @patch("account.management.commands.send_weekly_push.send_weekly_push_email")
    def test_weekly_push_command_stops_when_send_fails(self, mock_send_weekly_push_email):
        mock_send_weekly_push_email.return_value = {
            "sent": False,
            "digest": {
                "totalPaperCount": 0,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            paper_file = Path(tmpdir) / "weekly_papers.json"
            archive_dir = Path(tmpdir) / "archive"
            with paper_file.open("w", encoding="utf-8") as fp:
                json.dump(
                    {
                        "thursday": [self.paper.id],
                        "friday": [],
                        "saturday": [],
                        "sunday": [],
                        "monday": [],
                        "tuesday": [],
                        "wednesday": [],
                    },
                    fp,
                )

            with self.assertRaises(CommandError):
                call_command(
                    "send_weekly_push",
                    "--user",
                    "weekly_user",
                    "--paper-file",
                    str(paper_file),
                    "--archive-dir",
                    str(archive_dir),
                    stdout=StringIO(),
                )

            with paper_file.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)
            self.assertEqual(payload["thursday"], [self.paper.id])
            self.assertFalse(archive_dir.exists())

    @patch("account.management.commands.send_weekly_push.send_weekly_push_email")
    def test_weekly_push_command_promotes_staged_next_cycle_file(self, mock_send_weekly_push_email):
        mock_send_weekly_push_email.return_value = {
            "sent": True,
            "digest": {
                "totalPaperCount": 1,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            paper_file = Path(tmpdir) / "weekly_papers.json"
            next_paper_file = Path(tmpdir) / "weekly_papers_next.json"
            archive_dir = Path(tmpdir) / "archive"
            with paper_file.open("w", encoding="utf-8") as fp:
                json.dump(
                    {
                        "thursday": [self.paper.id],
                        "friday": [],
                        "saturday": [],
                        "sunday": [],
                        "monday": [],
                        "tuesday": [],
                        "wednesday": [],
                    },
                    fp,
                )
            with next_paper_file.open("w", encoding="utf-8") as fp:
                json.dump(
                    {
                        "thursday": [],
                        "friday": [self.paper.id],
                        "saturday": [],
                        "sunday": [],
                        "monday": [],
                        "tuesday": [],
                        "wednesday": [],
                    },
                    fp,
                )

            out = StringIO()
            call_command(
                "send_weekly_push",
                "--paper-file",
                str(paper_file),
                "--next-paper-file",
                str(next_paper_file),
                "--archive-dir",
                str(archive_dir),
                stdout=out,
            )

            with paper_file.open("r", encoding="utf-8") as fp:
                current_payload = json.load(fp)

            self.assertEqual(current_payload["friday"], [self.paper.id])
            self.assertFalse(next_paper_file.exists())
            self.assertIn("promoted staged records", out.getvalue())


class WeeklyPushSchedulerCommandTests(TestCase):
    @patch("account.management.commands.run_weekly_push_scheduler.BlockingScheduler")
    def test_run_weekly_push_scheduler_uses_default_thursday_noon(self, mock_scheduler_cls):
        mock_scheduler = mock_scheduler_cls.return_value
        out = StringIO()

        call_command("run_weekly_push_scheduler", stdout=out)

        mock_scheduler.add_job.assert_called_once()
        add_job_kwargs = mock_scheduler.add_job.call_args.kwargs
        self.assertEqual(add_job_kwargs["id"], "weekly_push_job")
        self.assertEqual(add_job_kwargs["replace_existing"], True)
        self.assertEqual(add_job_kwargs["coalesce"], True)
        self.assertEqual(add_job_kwargs["max_instances"], 1)
        self.assertEqual(add_job_kwargs["misfire_grace_time"], 3600)
        self.assertIn("已启动每周周报推送任务：每周 thu 12:00", out.getvalue())
        mock_scheduler.start.assert_called_once()


class RecordWeeklyPushPapersCommandTests(TestCase):
    def setUp(self):
        self.paper = Paper.objects.create(
            title="每日增量论文",
            abstract="每日增量摘要",
            publish_date=date(2026, 4, 16),
            author_names="Crawler",
            subjects="cs.AI",
        )
        self.other_paper = Paper.objects.create(
            title="另一篇每日增量论文",
            abstract="另一篇每日增量摘要",
            publish_date=date(2026, 4, 17),
            author_names="Crawler",
            subjects="cs.LG",
        )

    def test_record_weekly_push_papers_creates_weekly_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = f"{tmpdir}/weekly_papers.json"
            out = StringIO()

            call_command(
                "record_weekly_push_papers",
                "--day",
                "monday",
                "--paper-ids",
                f"{self.paper.id},{self.other_paper.id}",
                "--paper-file",
                file_path,
                stdout=out,
            )

            with open(file_path, "r", encoding="utf-8") as fp:
                payload = json.load(fp)

            self.assertEqual(payload["monday"], [self.paper.id, self.other_paper.id])
            self.assertEqual(payload["thursday"], [])
            self.assertIn("Recorded 2 new paper ID(s) for monday", out.getvalue())

    def test_record_weekly_push_papers_appends_unique_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = f"{tmpdir}/weekly_papers.json"

            call_command(
                "record_weekly_push_papers",
                "--day",
                "friday",
                "--paper-ids",
                str(self.paper.id),
                "--paper-file",
                file_path,
                stdout=StringIO(),
            )
            call_command(
                "record_weekly_push_papers",
                "--day",
                "friday",
                "--paper-ids",
                f"{self.paper.id},{self.other_paper.id}",
                "--paper-file",
                file_path,
                stdout=StringIO(),
            )

            with open(file_path, "r", encoding="utf-8") as fp:
                payload = json.load(fp)

            self.assertEqual(payload["friday"], [self.paper.id, self.other_paper.id])

    def test_record_weekly_push_papers_rejects_unknown_paper_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(CommandError):
                call_command(
                    "record_weekly_push_papers",
                    "--day",
                    "tuesday",
                    "--paper-ids",
                    "999999",
                    "--paper-file",
                    f"{tmpdir}/weekly_papers.json",
                    stdout=StringIO(),
                )


class ResetWeeklyPushPapersCommandTests(TestCase):
    def test_reset_weekly_push_papers_creates_empty_weekly_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = f"{tmpdir}/weekly_papers.json"
            out = StringIO()

            call_command(
                "reset_weekly_push_papers",
                "--paper-file",
                file_path,
                stdout=out,
            )

            with open(file_path, "r", encoding="utf-8") as fp:
                payload = json.load(fp)

            self.assertEqual(
                payload,
                {
                    "thursday": [],
                    "friday": [],
                    "saturday": [],
                    "sunday": [],
                    "monday": [],
                    "tuesday": [],
                    "wednesday": [],
                },
            )
            self.assertIn("Reset weekly push paper records", out.getvalue())

    def test_reset_weekly_push_papers_overwrites_existing_weekly_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = f"{tmpdir}/weekly_papers.json"
            with open(file_path, "w", encoding="utf-8") as fp:
                json.dump(
                    {
                        "thursday": [1, 2],
                        "friday": [3],
                        "saturday": [],
                        "sunday": [],
                        "monday": [4],
                        "tuesday": [],
                        "wednesday": [5],
                    },
                    fp,
                )

            call_command(
                "reset_weekly_push_papers",
                "--paper-file",
                file_path,
                stdout=StringIO(),
            )

            with open(file_path, "r", encoding="utf-8") as fp:
                payload = json.load(fp)

            self.assertTrue(all(paper_ids == [] for paper_ids in payload.values()))
