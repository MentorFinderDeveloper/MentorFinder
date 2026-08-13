import json

from django.test import TestCase

from account.models import MentorVerificationRequest, User, UserFollow, UserProfile
from utils.utils_jwt import generate_jwt_token


class AccountProfileAdditionalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profile_extra",
            email="profile_extra@example.com",
            password="abc12345",
            role=User.ROLE_STUDENT,
            real_name="Profile Extra",
        )
        self.other = User.objects.create_user(
            username="profile_other",
            email="profile_other@example.com",
            password="abc12345",
            role=User.ROLE_STUDENT,
            real_name="Profile Other",
        )
        self.banned = User.objects.create_user(
            username="profile_banned",
            email="profile_banned@example.com",
            password="abc12345",
            role=User.ROLE_BANNED,
        )
        self.token = generate_jwt_token(self.user.username)
        self.other_token = generate_jwt_token(self.other.username)

    def headers(self, token=None):
        return {"HTTP_AUTHORIZATION": f"Bearer {token or self.token}"}

    def put_profile(self, payload, token=None):
        return self.client.put(
            "/profile/me",
            data=json.dumps(payload),
            content_type="application/json",
            **self.headers(token),
        )

    def post_verification(self, payload, token=None):
        return self.client.post(
            "/profile/mentor-verification-request",
            data=json.dumps(payload),
            content_type="application/json",
            **self.headers(token),
        )

    def test_get_my_profile_creates_empty_profile(self):
        res = self.client.get("/profile/me", **self.headers())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())
        self.assertEqual(res.json()["profile"]["avatarUrl"], "")

    def test_get_my_profile_returns_latest_verification_request(self):
        MentorVerificationRequest.objects.create(
            user=self.user,
            submitted_name="旧申请",
            status=MentorVerificationRequest.STATUS_REJECTED,
        )
        latest = MentorVerificationRequest.objects.create(
            user=self.user,
            submitted_name="新申请",
            status=MentorVerificationRequest.STATUS_PENDING,
        )

        res = self.client.get("/profile/me", **self.headers())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["mentorVerificationRequest"]["id"], latest.id)
        self.assertEqual(res.json()["mentorVerificationRequest"]["submittedName"], "新申请")

    def test_update_profile_creates_profile_when_missing(self):
        res = self.put_profile({"signature": "  hello  "})

        self.assertEqual(res.status_code, 200)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.signature, "hello")
        self.assertEqual(res.json()["profile"]["signature"], "hello")

    def test_update_profile_preserves_omitted_fields(self):
        UserProfile.objects.create(
            user=self.user,
            avatar_url="/media/old.png",
            personal_intro="old intro",
            show_honors=False,
        )

        res = self.put_profile({"signature": "new signature"})

        self.assertEqual(res.status_code, 200)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.avatar_url, "/media/old.png")
        self.assertEqual(profile.personal_intro, "old intro")
        self.assertFalse(profile.show_honors)

    def test_update_profile_trims_all_string_fields(self):
        res = self.put_profile(
            {
                "avatarUrl": "  /media/avatar.png  ",
                "signature": "  sig  ",
                "personalIntro": "  intro  ",
                "researchExperience": "  research  ",
                "honors": "  honors  ",
                "projectExperience": "  project  ",
            },
        )

        self.assertEqual(res.status_code, 200)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.avatar_url, "/media/avatar.png")
        self.assertEqual(profile.signature, "sig")
        self.assertEqual(profile.personal_intro, "intro")
        self.assertEqual(profile.research_experience, "research")
        self.assertEqual(profile.honors, "honors")
        self.assertEqual(profile.project_experience, "project")

    def test_update_profile_updates_all_visibility_flags(self):
        res = self.put_profile(
            {
                "showPersonalIntro": False,
                "showResearchExperience": False,
                "showHonors": False,
                "showProjectExperience": False,
            },
        )

        self.assertEqual(res.status_code, 200)
        profile = UserProfile.objects.get(user=self.user)
        self.assertFalse(profile.show_personal_intro)
        self.assertFalse(profile.show_research_experience)
        self.assertFalse(profile.show_honors)
        self.assertFalse(profile.show_project_experience)

    def test_update_profile_rejects_non_object_body(self):
        res = self.put_profile([])

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["info"], "Invalid parameters. [body] must be an object")

    def test_update_profile_rejects_non_string_avatar(self):
        res = self.put_profile({"avatarUrl": 123})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["info"], "Invalid parameters. [avatarUrl] must be a string")

    def test_update_profile_rejects_non_boolean_visibility(self):
        res = self.put_profile({"showHonors": "yes"})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["info"], "Invalid parameters. [showHonors] must be a boolean")

    def test_public_profile_marks_self(self):
        res = self.client.get(f"/users/{self.user.id}/profile", **self.headers())

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["user"]["isSelf"])

    def test_public_profile_marks_followed_state(self):
        UserFollow.objects.create(follower=self.user, following=self.other)

        res = self.client.get(f"/users/{self.other.id}/profile", **self.headers())

        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["user"]["isSelf"])
        self.assertTrue(res.json()["user"]["followed"])

    def test_public_profile_hides_private_sections(self):
        UserProfile.objects.create(
            user=self.other,
            personal_intro="intro",
            research_experience="research",
            honors="honors",
            project_experience="project",
            show_personal_intro=False,
            show_research_experience=False,
            show_honors=False,
            show_project_experience=False,
        )

        res = self.client.get(f"/users/{self.other.id}/profile", **self.headers())

        self.assertEqual(res.status_code, 200)
        profile = res.json()["user"]["profile"]
        self.assertEqual(profile["personalIntro"], "")
        self.assertEqual(profile["researchExperience"], "")
        self.assertEqual(profile["honors"], "")
        self.assertEqual(profile["projectExperience"], "")

    def test_public_profile_rejects_banned_user(self):
        res = self.client.get(f"/users/{self.banned.id}/profile", **self.headers())

        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["info"], "User not found")

    def test_submit_verification_request_trims_name(self):
        res = self.post_verification({"submittedName": "  导师申请  "})

        self.assertEqual(res.status_code, 200)
        request_obj = MentorVerificationRequest.objects.get(user=self.user)
        self.assertEqual(request_obj.submitted_name, "导师申请")

    def test_submit_verification_request_rejects_blank_name(self):
        res = self.post_verification({"submittedName": "   "})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["info"], "Invalid parameters. [submittedName] cannot be empty")

    def put_username(self, payload, token=None):
        return self.client.put(
            "/profile/username",
            data=json.dumps(payload),
            content_type="application/json",
            **self.headers(token),
        )

    def test_update_username_succeeds_when_available(self):
        res = self.put_username({"username": "  brand_new  "})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["username"], "brand_new")
        self.assertTrue(res.json()["token"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "brand_new")

    def test_update_username_rejects_duplicate(self):
        res = self.put_username({"username": self.other.username})

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], 3)
        self.assertEqual(res.json()["info"], "Username already exists")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "profile_extra")

    def test_update_username_allows_keeping_same_name(self):
        res = self.put_username({"username": "profile_extra"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["username"], "profile_extra")

    def test_update_username_rejects_blank(self):
        res = self.put_username({"username": "   "})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["info"], "Invalid parameters. [username] cannot be empty")

    def test_update_username_rejects_invalid_characters(self):
        res = self.put_username({"username": "bad name!"})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            res.json()["info"],
            "Invalid parameters. [username] can only contain letters, digits, underscores, and hyphens",
        )

    def test_update_username_requires_auth(self):
        res = self.client.put(
            "/profile/username",
            data=json.dumps({"username": "whatever"}),
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 401)
