import json

from django.test import TestCase

from account.models import MentorVerificationRequest, User
from dataset.models import Mentor
from utils.utils_jwt import generate_jwt_token


class AccountManagementAdditionalTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="extra_admin",
            email="extra_admin@example.com",
            password="abc12345",
            role=User.ROLE_ADMIN,
            real_name="Extra Admin",
        )
        self.student = User.objects.create_user(
            username="extra_student",
            email="extra_student@example.com",
            password="abc12345",
            role=User.ROLE_STUDENT,
            real_name="Extra Student",
        )
        self.other = User.objects.create_user(
            username="other_managed",
            email="other_managed@example.com",
            password="abc12345",
            role=User.ROLE_STUDENT,
            real_name="Other Managed",
        )
        self.banned = User.objects.create_user(
            username="managed_banned",
            email="managed_banned@example.com",
            password="abc12345",
            role=User.ROLE_BANNED,
        )
        self.public_mentor = Mentor.objects.create(
            Chinese_name="管理导师",
            English_name="Managed Mentor",
            research_direction="软件工程",
            email="managed.mentor@example.com",
            profile="管理导师档案",
        )
        self.second_mentor = Mentor.objects.create(
            Chinese_name="第二导师",
            English_name="Second Managed Mentor",
            research_direction="数据库",
            email="second.mentor@example.com",
            profile="第二导师档案",
        )
        self.private_mentor = Mentor.objects.create(
            Chinese_name="私有管理导师",
            English_name="Private Managed Mentor",
            research_direction="系统安全",
            email="private.mentor@example.com",
            profile="私有导师档案",
            owner=self.student,
        )
        self.admin_token = generate_jwt_token(self.admin.username)
        self.student_token = generate_jwt_token(self.student.username)

    def headers(self, token=None, prefix="Bearer "):
        return {"HTTP_AUTHORIZATION": f"{prefix}{token or self.admin_token}"}

    def put_json(self, path, payload, token=None):
        return self.client.put(
            path,
            data=json.dumps(payload),
            content_type="application/json",
            **self.headers(token),
        )

    def request_review(self, request_obj, payload, token=None):
        return self.put_json(
            f"/management/verification-requests/{request_obj.id}",
            payload,
            token=token,
        )

    def create_request(self, user=None, status=MentorVerificationRequest.STATUS_PENDING):
        return MentorVerificationRequest.objects.create(
            user=user or self.student,
            submitted_name="申请导师姓名",
            status=status,
        )

    def listed_usernames(self, response):
        return [user["username"] for user in response.json()["users"]]

    def test_admin_list_accepts_token_without_bearer_prefix(self):
        res = self.client.get(
            "/management/users",
            **self.headers(prefix=""),
        )

        self.assertEqual(res.status_code, 200)
        self.assertIn("extra_admin", self.listed_usernames(res))

    def test_admin_list_accepts_lowercase_bearer_prefix(self):
        res = self.client.get(
            "/management/users",
            **self.headers(prefix="bearer "),
        )

        self.assertEqual(res.status_code, 200)
        self.assertIn("extra_student", self.listed_usernames(res))

    def test_admin_list_rejects_missing_token_before_method_check(self):
        res = self.client.post("/management/users")

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)

    def test_admin_list_rejects_deleted_token_user(self):
        token = generate_jwt_token("deleted_admin")

        res = self.client.get("/management/users", **self.headers(token))

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["info"], "User not found")

    def test_admin_list_rejects_banned_admin_token(self):
        self.admin.role = User.ROLE_BANNED
        self.admin.save(update_fields=["role"])

        res = self.client.get("/management/users", **self.headers())

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["info"], "User is banned")

    def test_admin_list_trims_role_filter(self):
        res = self.client.get(
            "/management/users",
            {"role": f"  {User.ROLE_STUDENT}  "},
            **self.headers(),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["roleFilter"], User.ROLE_STUDENT)
        self.assertEqual(set(self.listed_usernames(res)), {"extra_student", "other_managed"})

    def test_admin_list_normalizes_role_filter_case(self):
        res = self.client.get(
            "/management/users",
            {"role": "ADMIN"},
            **self.headers(),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["roleFilter"], User.ROLE_ADMIN)
        self.assertEqual(self.listed_usernames(res), ["extra_admin"])

    def test_admin_list_keyword_filter_is_case_insensitive(self):
        res = self.client.get(
            "/management/users",
            {"keyword": "extra student"},
            **self.headers(),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.listed_usernames(res), ["extra_student"])

    def test_admin_list_keyword_filter_trims_spaces(self):
        res = self.client.get(
            "/management/users",
            {"keyword": "  other_managed@example.com  "},
            **self.headers(),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.listed_usernames(res), ["other_managed"])

    def test_admin_list_combines_role_and_keyword_filters(self):
        self.other.role = User.ROLE_ADMIN
        self.other.save(update_fields=["role"])

        res = self.client.get(
            "/management/users",
            {"role": User.ROLE_ADMIN, "keyword": "other"},
            **self.headers(),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.listed_usernames(res), ["other_managed"])

    def test_admin_list_serializes_current_user_id(self):
        res = self.client.get("/management/users", **self.headers())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["currentUserId"], self.admin.id)

    def test_admin_list_serializes_mentor_binding_flag(self):
        self.student.role = User.ROLE_MENTOR
        self.student.mentor_profile = self.public_mentor
        self.student.save(update_fields=["role", "mentor_profile"])

        res = self.client.get(
            "/management/users",
            {"keyword": self.student.username},
            **self.headers(),
        )

        self.assertEqual(res.status_code, 200)
        user = res.json()["users"][0]
        self.assertTrue(user["isBoundToMentor"])
        self.assertEqual(user["mentorProfile"]["id"], self.public_mentor.id)

    def test_admin_list_includes_reviewed_verification_requests(self):
        approved = self.create_request(status=MentorVerificationRequest.STATUS_APPROVED)
        rejected = self.create_request(user=self.other, status=MentorVerificationRequest.STATUS_REJECTED)

        res = self.client.get("/management/users", **self.headers())

        self.assertEqual(res.status_code, 200)
        request_ids = {item["id"] for item in res.json()["verificationRequests"]}
        self.assertEqual(request_ids, {approved.id, rejected.id})

    def test_admin_update_accepts_uppercase_role(self):
        res = self.put_json(
            f"/management/users/{self.student.id}",
            {"role": "ADMIN"},
        )

        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.ROLE_ADMIN)

    def test_admin_update_accepts_role_with_spaces(self):
        res = self.put_json(
            f"/management/users/{self.student.id}",
            {"role": f"  {User.ROLE_BANNED}  "},
        )

        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.ROLE_BANNED)

    def test_admin_update_rejects_array_body(self):
        res = self.put_json(f"/management/users/{self.student.id}", [])

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["info"], "Invalid parameters. [body] must be an object")

    def test_admin_update_rejects_missing_role(self):
        res = self.put_json(f"/management/users/{self.student.id}", {})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_admin_update_rejects_non_string_role(self):
        res = self.put_json(
            f"/management/users/{self.student.id}",
            {"role": 123},
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_admin_update_allows_rebinding_same_mentor_to_same_user(self):
        self.student.role = User.ROLE_MENTOR
        self.student.mentor_profile = self.public_mentor
        self.student.save(update_fields=["role", "mentor_profile"])

        res = self.put_json(
            f"/management/users/{self.student.id}",
            {"role": User.ROLE_MENTOR, "mentorId": self.public_mentor.id},
        )

        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.mentor_profile_id, self.public_mentor.id)

    def test_admin_update_rebinds_mentor_to_different_public_mentor(self):
        self.student.role = User.ROLE_MENTOR
        self.student.mentor_profile = self.public_mentor
        self.student.save(update_fields=["role", "mentor_profile"])

        res = self.put_json(
            f"/management/users/{self.student.id}",
            {"role": User.ROLE_MENTOR, "mentorId": self.second_mentor.id},
        )

        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.mentor_profile_id, self.second_mentor.id)

    def test_admin_update_unbinds_mentor_when_role_changes_to_student(self):
        self.student.role = User.ROLE_MENTOR
        self.student.mentor_profile = self.public_mentor
        self.student.save(update_fields=["role", "mentor_profile"])

        res = self.put_json(
            f"/management/users/{self.student.id}",
            {"role": User.ROLE_STUDENT},
        )

        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.ROLE_STUDENT)
        self.assertIsNone(self.student.mentor_profile)

    def test_admin_update_unbinds_mentor_when_role_changes_to_admin(self):
        self.student.role = User.ROLE_MENTOR
        self.student.mentor_profile = self.public_mentor
        self.student.save(update_fields=["role", "mentor_profile"])

        res = self.put_json(
            f"/management/users/{self.student.id}",
            {"role": User.ROLE_ADMIN},
        )

        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.ROLE_ADMIN)
        self.assertIsNone(self.student.mentor_profile)

    def test_admin_update_rejects_non_admin_token(self):
        res = self.put_json(
            f"/management/users/{self.student.id}",
            {"role": User.ROLE_ADMIN},
            token=self.student_token,
        )

        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["info"], "Permission denied")

    def test_admin_update_rejects_banned_target_self_via_case_normalization(self):
        res = self.put_json(
            f"/management/users/{self.admin.id}",
            {"role": "BANNED"},
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["info"], "Admin cannot ban self")

    def test_review_accepts_uppercase_status(self):
        request_obj = self.create_request()

        res = self.request_review(
            request_obj,
            {"status": "REJECTED"},
        )

        self.assertEqual(res.status_code, 200)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, MentorVerificationRequest.STATUS_REJECTED)

    def test_review_accepts_status_with_spaces(self):
        request_obj = self.create_request()

        res = self.request_review(
            request_obj,
            {"status": f"  {MentorVerificationRequest.STATUS_REJECTED}  "},
        )

        self.assertEqual(res.status_code, 200)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, MentorVerificationRequest.STATUS_REJECTED)

    def test_review_rejects_array_body(self):
        request_obj = self.create_request()

        res = self.request_review(request_obj, [])

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["info"], "Invalid parameters. [body] must be an object")

    def test_review_rejects_missing_status(self):
        request_obj = self.create_request()

        res = self.request_review(request_obj, {})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_review_rejects_non_string_status(self):
        request_obj = self.create_request()

        res = self.request_review(request_obj, {"status": 1})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_review_approval_accepts_string_mentor_id(self):
        request_obj = self.create_request()

        res = self.request_review(
            request_obj,
            {
                "status": MentorVerificationRequest.STATUS_APPROVED,
                "mentorId": str(self.public_mentor.id),
            },
        )

        self.assertEqual(res.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.ROLE_MENTOR)
        self.assertEqual(self.student.mentor_profile_id, self.public_mentor.id)

    def test_review_approval_rejects_empty_mentor_id(self):
        request_obj = self.create_request()

        res = self.request_review(
            request_obj,
            {
                "status": MentorVerificationRequest.STATUS_APPROVED,
                "mentorId": "",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["info"], "Mentor binding is required for approval")

    def test_review_approval_rejects_mentor_id_with_spaces(self):
        request_obj = self.create_request()

        res = self.request_review(
            request_obj,
            {
                "status": MentorVerificationRequest.STATUS_APPROVED,
                "mentorId": "   ",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["info"], "Invalid parameters. [mentorId] must be an integer")

    def test_review_approval_rejects_bound_public_mentor(self):
        User.objects.create_user(
            username="already_bound",
            email="already_bound@example.com",
            password="abc12345",
            role=User.ROLE_MENTOR,
            mentor_profile=self.public_mentor,
        )
        request_obj = self.create_request()

        res = self.request_review(
            request_obj,
            {
                "status": MentorVerificationRequest.STATUS_APPROVED,
                "mentorId": self.public_mentor.id,
            },
        )

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["info"], "Mentor is already bound to another user")
