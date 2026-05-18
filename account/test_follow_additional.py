from datetime import date

from django.test import TestCase

from account.models import MentorFollow, SubjectFollow, User, UserFollow, UserProfile
from dataset.models import Mentor, Paper
from utils.utils_jwt import generate_jwt_token


class AccountFollowAdditionalTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="follow_student",
            email="follow_student@example.com",
            password="abc12345",
            role=User.ROLE_STUDENT,
            real_name="Follow Student",
        )
        self.other = User.objects.create_user(
            username="other_student",
            email="other_student@example.com",
            password="abc12345",
            role=User.ROLE_STUDENT,
            real_name="Other Student",
        )
        self.third = User.objects.create_user(
            username="third_student",
            email="third_student@example.com",
            password="abc12345",
            role=User.ROLE_STUDENT,
            real_name="Third Student",
        )
        self.admin = User.objects.create_user(
            username="follow_admin",
            email="follow_admin@example.com",
            password="abc12345",
            role=User.ROLE_ADMIN,
            real_name="Follow Admin",
        )
        self.banned = User.objects.create_user(
            username="banned_student",
            email="banned_student@example.com",
            password="abc12345",
            role=User.ROLE_BANNED,
        )
        self.mentor_user = User.objects.create_user(
            username="mentor_user",
            email="mentor_user@example.com",
            password="abc12345",
            role=User.ROLE_MENTOR,
            real_name="Mentor User",
        )
        self.mentor = Mentor.objects.create(
            Chinese_name="公开导师",
            English_name="Open Mentor",
            research_direction="机器学习",
            email="open@example.com",
            profile="公开导师简介",
        )
        self.other_mentor = Mentor.objects.create(
            Chinese_name="另一位导师",
            English_name="Second Mentor",
            research_direction="自然语言处理",
            email="second@example.com",
            profile="另一位导师简介",
        )
        self.private_mentor = Mentor.objects.create(
            Chinese_name="私有导师",
            English_name="Private Mentor",
            research_direction="数据库",
            email="private@example.com",
            profile="私有导师简介",
            owner=self.other,
        )
        self.mentor_user.mentor_profile = self.mentor
        self.mentor_user.save(update_fields=["mentor_profile"])
        self.token = generate_jwt_token(self.student.username)
        self.other_token = generate_jwt_token(self.other.username)
        self.admin_token = generate_jwt_token(self.admin.username)
        self.mentor_token = generate_jwt_token(self.mentor_user.username)

    def auth(self, token=None):
        return {"HTTP_AUTHORIZATION": f"Bearer {token or self.token}"}

    def create_subject_paper(self, title="Subject paper", subjects="cs.AI"):
        return Paper.objects.create(
            title=title,
            subjects=subjects,
            publish_date=date(2026, 5, 1),
            author_names="A, B",
        )

    def usernames(self, users):
        return [user["username"] for user in users]

    def test_follow_user_creates_relationship(self):
        res = self.client.post(f"/follow/users/{self.other.id}", **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(res.json()["followed"])
        self.assertTrue(UserFollow.objects.filter(follower=self.student, following=self.other).exists())

    def test_follow_user_is_idempotent(self):
        first = self.client.post(f"/follow/users/{self.other.id}", **self.auth())
        second = self.client.post(f"/follow/users/{self.other.id}", **self.auth())

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(UserFollow.objects.filter(follower=self.student, following=self.other).count(), 1)

    def test_unfollow_user_removes_relationship(self):
        UserFollow.objects.create(follower=self.student, following=self.other)

        res = self.client.delete(f"/follow/users/{self.other.id}", **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["followed"])
        self.assertFalse(UserFollow.objects.filter(follower=self.student, following=self.other).exists())

    def test_unfollow_user_that_is_not_followed_is_ok(self):
        res = self.client.delete(f"/follow/users/{self.other.id}", **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertFalse(res.json()["followed"])

    def test_follow_user_requires_login(self):
        res = self.client.post(f"/follow/users/{self.other.id}")

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)

    def test_follow_user_rejects_self_follow(self):
        res = self.client.post(f"/follow/users/{self.student.id}", **self.auth())

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], 3)
        self.assertFalse(UserFollow.objects.filter(follower=self.student, following=self.student).exists())

    def test_follow_user_hides_banned_target(self):
        res = self.client.post(f"/follow/users/{self.banned.id}", **self.auth())

        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["code"], 2)
        self.assertFalse(UserFollow.objects.filter(follower=self.student, following=self.banned).exists())

    def test_follow_user_missing_target_returns_404(self):
        res = self.client.post("/follow/users/999999", **self.auth())

        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["info"], "User not found")

    def test_follow_user_bad_method(self):
        res = self.client.get(f"/follow/users/{self.other.id}", **self.auth())

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    def test_followed_users_lists_current_users_targets(self):
        UserProfile.objects.create(user=self.other, avatar_url="/media/a.png", signature="hello")
        UserFollow.objects.create(follower=self.student, following=self.other)
        UserFollow.objects.create(follower=self.student, following=self.admin)
        UserFollow.objects.create(follower=self.other, following=self.third)

        res = self.client.get("/follow/users", **self.auth())

        self.assertEqual(res.status_code, 200)
        users = res.json()["users"]
        self.assertEqual(set(self.usernames(users)), {"other_student", "follow_admin"})
        other = next(user for user in users if user["username"] == "other_student")
        self.assertEqual(other["avatarUrl"], "/media/a.png")
        self.assertEqual(other["signature"], "hello")
        self.assertTrue(other["followed"])

    def test_followed_users_filters_banned_targets(self):
        UserFollow.objects.create(follower=self.student, following=self.banned)
        UserFollow.objects.create(follower=self.student, following=self.other)

        res = self.client.get("/follow/users", **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.usernames(res.json()["users"]), ["other_student"])

    def test_followed_users_requires_login(self):
        res = self.client.get("/follow/users")

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)

    def test_followed_users_bad_method(self):
        res = self.client.post("/follow/users", **self.auth())

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    def test_search_users_returns_non_banned_users_except_self(self):
        res = self.client.get("/search/users", **self.auth())

        self.assertEqual(res.status_code, 200)
        names = self.usernames(res.json()["users"])
        self.assertNotIn("follow_student", names)
        self.assertNotIn("banned_student", names)
        self.assertIn("other_student", names)
        self.assertIn("follow_admin", names)

    def test_search_users_matches_username(self):
        res = self.client.get("/search/users", {"keyword": "other"}, **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.usernames(res.json()["users"]), ["other_student"])
        self.assertEqual(res.json()["keyword"], "other")

    def test_search_users_matches_email(self):
        res = self.client.get("/search/users", {"keyword": "admin@example"}, **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.usernames(res.json()["users"]), ["follow_admin"])

    def test_search_users_matches_real_name_case_insensitively(self):
        res = self.client.get("/search/users", {"keyword": "mentor user"}, **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.usernames(res.json()["users"]), ["mentor_user"])

    def test_search_users_marks_existing_follow(self):
        UserFollow.objects.create(follower=self.student, following=self.other)

        res = self.client.get("/search/users", {"keyword": "other"}, **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["users"][0]["followed"])

    def test_search_users_trims_keyword(self):
        res = self.client.get("/search/users", {"keyword": "  admin@example.com  "}, **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["keyword"], "admin@example.com")
        self.assertEqual(self.usernames(res.json()["users"]), ["follow_admin"])

    def test_search_users_limits_to_twenty_results(self):
        for index in range(25):
            User.objects.create_user(
                username=f"bulk_user_{index:02d}",
                email=f"bulk{index}@example.com",
                password="abc12345",
                role=User.ROLE_STUDENT,
            )

        res = self.client.get("/search/users", {"keyword": "bulk_user"}, **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["users"]), 20)
        self.assertEqual(res.json()["users"][0]["username"], "bulk_user_00")

    def test_search_users_rejects_overlong_keyword(self):
        res = self.client.get("/search/users", {"keyword": "x" * 300}, **self.auth())

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_search_users_requires_login(self):
        res = self.client.get("/search/users")

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)

    def test_search_users_bad_method(self):
        res = self.client.post("/search/users", **self.auth())

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    def test_mentor_can_follow_public_mentor(self):
        res = self.client.post(f"/follow/mentors/{self.other_mentor.id}", **self.auth(self.mentor_token))

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["followed"])
        self.assertTrue(MentorFollow.objects.filter(student=self.mentor_user, mentor=self.other_mentor).exists())

    def test_owner_can_follow_own_private_mentor(self):
        res = self.client.post(f"/follow/mentors/{self.private_mentor.id}", **self.auth(self.other_token))

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["followed"])
        self.assertTrue(MentorFollow.objects.filter(student=self.other, mentor=self.private_mentor).exists())

    def test_admin_can_follow_private_mentor(self):
        res = self.client.post(f"/follow/mentors/{self.private_mentor.id}", **self.auth(self.admin_token))

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["followed"])
        self.assertTrue(MentorFollow.objects.filter(student=self.admin, mentor=self.private_mentor).exists())

    def test_unfollow_private_mentor_requires_visibility(self):
        MentorFollow.objects.create(student=self.student, mentor=self.private_mentor)

        res = self.client.delete(f"/follow/mentors/{self.private_mentor.id}", **self.auth())

        self.assertEqual(res.status_code, 404)
        self.assertTrue(MentorFollow.objects.filter(student=self.student, mentor=self.private_mentor).exists())

    def test_followed_mentors_filters_now_hidden_private_mentor(self):
        MentorFollow.objects.create(student=self.student, mentor=self.mentor)
        MentorFollow.objects.create(student=self.student, mentor=self.private_mentor)

        res = self.client.get("/follow/mentors", **self.auth())

        self.assertEqual(res.status_code, 200)
        names = [mentor["Chinese_name"] for mentor in res.json()["mentors"]]
        self.assertEqual(names, ["公开导师"])

    def test_followed_mentors_owner_can_see_private_mentor(self):
        MentorFollow.objects.create(student=self.other, mentor=self.private_mentor)

        res = self.client.get("/follow/mentors", **self.auth(self.other_token))

        self.assertEqual(res.status_code, 200)
        self.assertEqual([mentor["Chinese_name"] for mentor in res.json()["mentors"]], ["私有导师"])

    def test_follow_subject_trims_subject_from_url(self):
        self.create_subject_paper(subjects="cs.AI")

        res = self.client.post("/follow/subjects/%20cs.AI%20", **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertTrue(SubjectFollow.objects.filter(user=self.student, subject="cs.AI").exists())

    def test_follow_subject_rejects_empty_subject(self):
        res = self.client.post("/follow/subjects/%20%20", **self.auth())

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_follow_subject_rejects_too_long_subject(self):
        subject = "x" * 101
        res = self.client.post(f"/follow/subjects/{subject}", **self.auth())

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    def test_follow_subject_requires_login(self):
        self.create_subject_paper(subjects="cs.AI")

        res = self.client.post("/follow/subjects/cs.AI")

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)

    def test_follow_subject_is_idempotent(self):
        self.create_subject_paper(subjects="cs.AI")

        first = self.client.post("/follow/subjects/cs.AI", **self.auth())
        second = self.client.post("/follow/subjects/cs.AI", **self.auth())

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(SubjectFollow.objects.filter(user=self.student, subject="cs.AI").count(), 1)

    def test_unfollow_subject_that_is_not_followed_is_ok(self):
        self.create_subject_paper(subjects="cs.AI")

        res = self.client.delete("/follow/subjects/cs.AI", **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["followed"])

    def test_followed_subjects_orders_available_by_count_then_name(self):
        self.create_subject_paper("AI 1", "cs.AI, cs.LG")
        self.create_subject_paper("AI 2", "cs.AI, cs.CL")
        self.create_subject_paper("DB 1", "cs.DB")
        SubjectFollow.objects.create(user=self.student, subject="cs.CL")

        res = self.client.get("/follow/subjects", **self.auth())

        self.assertEqual(res.status_code, 200)
        available = res.json()["availableSubjects"]
        self.assertEqual([item["subject"] for item in available], ["cs.AI", "cs.CL", "cs.DB", "cs.LG"])
        self.assertFalse(available[0]["followed"])
        self.assertTrue(available[1]["followed"])

    def test_followed_subjects_returns_empty_available_when_no_papers(self):
        SubjectFollow.objects.create(user=self.student, subject="cs.AI")

        res = self.client.get("/follow/subjects", **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["availableSubjects"], [])
        self.assertEqual(res.json()["subjects"][0]["paperCount"], 0)

    def test_followed_subjects_requires_login(self):
        res = self.client.get("/follow/subjects")

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)

    def test_followed_subjects_bad_method(self):
        res = self.client.post("/follow/subjects", **self.auth())

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    def test_follow_subject_bad_method(self):
        res = self.client.get("/follow/subjects/cs.AI", **self.auth())

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    def test_followers_for_student_excludes_mentor_follow_records(self):
        MentorFollow.objects.create(student=self.other, mentor=self.mentor)
        UserFollow.objects.create(follower=self.third, following=self.student)

        res = self.client.get("/follow/followers", **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.usernames(res.json()["users"]), ["third_student"])

    def test_auth_helper_uses_default_student_token(self):
        headers = self.auth()

        self.assertIn("HTTP_AUTHORIZATION", headers)
        self.assertTrue(headers["HTTP_AUTHORIZATION"].startswith("Bearer "))
        self.assertIn(self.token, headers["HTTP_AUTHORIZATION"])

    def test_usernames_helper_preserves_order(self):
        users = [{"username": "first"}, {"username": "second"}]

        self.assertEqual(self.usernames(users), ["first", "second"])

    def test_followers_for_bound_mentor_marks_user_followed_state(self):
        UserFollow.objects.create(follower=self.mentor_user, following=self.other)
        MentorFollow.objects.create(student=self.other, mentor=self.mentor)

        res = self.client.get("/follow/followers", **self.auth(self.mentor_token))

        self.assertEqual(res.status_code, 200)
        users = res.json()["users"]
        self.assertEqual(self.usernames(users), ["other_student"])
        self.assertTrue(users[0]["followed"])

    def test_followers_for_unbound_mentor_uses_only_user_follows(self):
        self.mentor_user.mentor_profile = None
        self.mentor_user.save(update_fields=["mentor_profile"])
        MentorFollow.objects.create(student=self.other, mentor=self.mentor)
        UserFollow.objects.create(follower=self.third, following=self.mentor_user)

        res = self.client.get("/follow/followers", **self.auth(self.mentor_token))

        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.usernames(res.json()["users"]), ["third_student"])
