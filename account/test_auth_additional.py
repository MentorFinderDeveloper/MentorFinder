import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from account.models import EmailVerificationCode, User
from account.services.email_verification import (
    CODE_LENGTH,
    email_matches_bypass,
    generate_verification_code,
    get_remaining_cooldown,
    issue_verification_code,
    verify_code,
)


class AccountAuthAdditionalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="auth_user",
            email="auth_user@example.com",
            password="abc12345",
        )

    def post_json(self, path: str, payload: dict):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def issue_code(
        self,
        email: str,
        code: str = "123456",
        expires_in: timedelta = timedelta(minutes=10),
    ) -> str:
        EmailVerificationCode.objects.update_or_create(
            email=email,
            defaults={
                "code": code,
                "expires_at": timezone.now() + expires_in,
            },
        )
        return code

    def test_login_rejects_missing_username(self):
        res = self.post_json(
            "/login",
            {
                "password": "abc12345",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertIn("username", res.json()["info"])

    def test_login_rejects_missing_password(self):
        res = self.post_json(
            "/login",
            {
                "username": "auth_user",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertIn("password", res.json()["info"])

    def test_login_username_is_case_sensitive(self):
        res = self.post_json(
            "/login",
            {
                "username": "AUTH_USER",
                "password": "abc12345",
            },
        )

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)
        self.assertEqual(res.json()["info"], "User not found")

    def test_login_email_is_case_sensitive_in_current_lookup(self):
        res = self.post_json(
            "/login",
            {
                "username": "AUTH_USER@EXAMPLE.COM",
                "password": "abc12345",
            },
        )

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)
        self.assertEqual(res.json()["info"], "User not found")

    def test_login_does_not_trim_identifier(self):
        res = self.post_json(
            "/login",
            {
                "username": " auth_user ",
                "password": "abc12345",
            },
        )

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)
        self.assertEqual(res.json()["info"], "User not found")

    def test_login_wrong_password_for_email_does_not_reveal_user(self):
        res = self.post_json(
            "/login",
            {
                "username": "auth_user@example.com",
                "password": "wrongpass",
            },
        )

        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["code"], 2)
        self.assertEqual(res.json()["info"], "Wrong password")

    def test_register_rejects_missing_username(self):
        res = self.post_json(
            "/register",
            {
                "password": "abc12345",
                "email": "missing_username@example.com",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertIn("username", res.json()["info"])

    def test_register_rejects_missing_password(self):
        res = self.post_json(
            "/register",
            {
                "username": "missing_password",
                "email": "missing_password@example.com",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertIn("password", res.json()["info"])

    def test_register_rejects_non_string_email(self):
        res = self.post_json(
            "/register",
            {
                "username": "bad_email_type",
                "password": "abc12345",
                "email": 123,
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertIn("email", res.json()["info"])

    def test_register_rejects_empty_username_after_trim(self):
        res = self.post_json(
            "/register",
            {
                "username": "   ",
                "password": "abc12345",
                "email": "blank_username@example.com",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertEqual(res.json()["info"], "Invalid parameters. [username] cannot be empty")

    def test_register_rejects_blank_password(self):
        res = self.post_json(
            "/register",
            {
                "username": "blank_password",
                "password": "   ",
                "email": "blank_password@example.com",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertEqual(res.json()["info"], "Invalid parameters. [password] cannot be empty")

    def test_register_rejects_non_string_verification_code(self):
        res = self.post_json(
            "/register",
            {
                "username": "bad_code_type",
                "password": "abc12345",
                "email": "bad_code_type@example.com",
                "verificationCode": 123456,
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertEqual(res.json()["info"], "Invalid parameters. [verificationCode] must be a string")

    def test_register_accepts_verification_code_with_surrounding_spaces(self):
        self.issue_code("trim_code@example.com", code="112233")

        res = self.post_json(
            "/register",
            {
                "username": "trim_code_user",
                "password": "abc12345",
                "email": "trim_code@example.com",
                "verificationCode": " 112233 ",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(User.objects.filter(username="trim_code_user").exists())
        self.assertFalse(EmailVerificationCode.objects.filter(email="trim_code@example.com").exists())

    def test_register_keeps_verification_code_when_duplicate_username_fails(self):
        self.issue_code("duplicate_username_code@example.com")

        res = self.post_json(
            "/register",
            {
                "username": "auth_user",
                "password": "abc12345",
                "email": "duplicate_username_code@example.com",
                "verificationCode": "123456",
            },
        )

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], 3)
        self.assertTrue(EmailVerificationCode.objects.filter(email="duplicate_username_code@example.com").exists())

    def test_register_keeps_verification_code_when_duplicate_email_fails(self):
        self.issue_code("auth_user@example.com")

        res = self.post_json(
            "/register",
            {
                "username": "duplicate_email_user",
                "password": "abc12345",
                "email": "auth_user@example.com",
                "verificationCode": "123456",
            },
        )

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], 4)
        self.assertTrue(EmailVerificationCode.objects.filter(email="auth_user@example.com").exists())

    def test_register_bypass_email_does_not_consume_existing_code(self):
        self.issue_code("bypass-existing@example.com", code="999999")

        res = self.post_json(
            "/register",
            {
                "username": "bypass_existing",
                "password": "abc12345",
                "email": "bypass-existing@example.com",
                "verificationCode": "wrong",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(EmailVerificationCode.objects.filter(email="bypass-existing@example.com").exists())

    def test_register_bypass_email_allows_missing_verification_code(self):
        res = self.post_json(
            "/register",
            {
                "username": "bypass_missing_code",
                "password": "abc12345",
                "email": "bypass-missing-code@example.com",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(User.objects.filter(username="bypass_missing_code").exists())

    def test_send_verification_code_rejects_missing_email(self):
        res = self.post_json(
            "/register/verification-code",
            {},
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertIn("email", res.json()["info"])

    def test_send_verification_code_rejects_blank_email(self):
        res = self.post_json(
            "/register/verification-code",
            {
                "email": "   ",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)
        self.assertEqual(res.json()["info"], "Invalid parameters. [email] format is invalid")

    def test_send_verification_code_trims_email_before_storing(self):
        res = self.post_json(
            "/register/verification-code",
            {
                "email": "  fresh-trim@example.com  ",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(EmailVerificationCode.objects.filter(email="fresh-trim@example.com").exists())
        self.assertFalse(EmailVerificationCode.objects.filter(email="  fresh-trim@example.com  ").exists())

    @patch("account.views.send_verification_email")
    def test_send_verification_code_returns_gateway_error_when_email_fails(self, mock_send):
        mock_send.side_effect = RuntimeError("smtp down")

        res = self.post_json(
            "/register/verification-code",
            {
                "email": "smtp-error@example.com",
            },
        )

        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["code"], 7)
        self.assertIn("smtp down", res.json()["info"])
        self.assertTrue(EmailVerificationCode.objects.filter(email="smtp-error@example.com").exists())

    @override_settings(EMAIL_VERIFICATION_CODE_RESEND_COOLDOWN=120)
    def test_send_verification_code_uses_configured_cooldown(self):
        res = self.post_json(
            "/register/verification-code",
            {
                "email": "cooldown-config@example.com",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["cooldownSeconds"], 120)

    @override_settings(EMAIL_VERIFICATION_BYPASS_PREFIX="")
    def test_empty_bypass_prefix_disables_bypass(self):
        self.assertFalse(email_matches_bypass("bypass-disabled@example.com"))

        res = self.post_json(
            "/register",
            {
                "username": "disabled_bypass",
                "password": "abc12345",
                "email": "bypass-disabled@example.com",
            },
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], 5)
        self.assertFalse(User.objects.filter(username="disabled_bypass").exists())

    @override_settings(EMAIL_VERIFICATION_BYPASS_PREFIX="skip")
    def test_custom_bypass_prefix_is_respected(self):
        self.assertTrue(email_matches_bypass("skip-user@example.com"))
        self.assertFalse(email_matches_bypass("bypass-user@example.com"))

        res = self.post_json(
            "/register",
            {
                "username": "custom_bypass",
                "password": "abc12345",
                "email": "skip-user@example.com",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(User.objects.filter(username="custom_bypass").exists())

    def test_email_matches_bypass_is_case_insensitive(self):
        self.assertTrue(
            email_matches_bypass("ByPass-case@example.com")
        )
        self.assertTrue(email_matches_bypass("bypass-case@example.com"))
        self.assertFalse(email_matches_bypass("regular@example.com"))
        self.assertFalse(email_matches_bypass(""))

    def test_generate_verification_code_returns_six_digits(self):
        code = generate_verification_code()

        self.assertEqual(len(code), CODE_LENGTH)
        self.assertTrue(code.isdigit())

    @override_settings(EMAIL_VERIFICATION_CODE_TTL_SECONDS=60)
    def test_issue_verification_code_sets_future_expiration(self):
        code, record = issue_verification_code("issue@example.com")

        self.assertEqual(len(code), CODE_LENGTH)
        self.assertEqual(record.email, "issue@example.com")
        self.assertTrue(record.expires_at > timezone.now())

    def test_issue_verification_code_replaces_existing_record(self):
        EmailVerificationCode.objects.create(
            email="replace@example.com",
            code="000000",
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        code, record = issue_verification_code("replace@example.com")

        self.assertEqual(EmailVerificationCode.objects.filter(email="replace@example.com").count(), 1)
        self.assertEqual(record.code, code)
        self.assertNotEqual(record.code, "000000")

    def test_verify_code_rejects_missing_record(self):
        self.assertFalse(verify_code("missing@example.com", "123456"))

    def test_verify_code_rejects_wrong_code_without_consuming(self):
        self.issue_code("wrong-code@example.com", code="111111")

        self.assertFalse(verify_code("wrong-code@example.com", "222222"))
        self.assertTrue(EmailVerificationCode.objects.filter(email="wrong-code@example.com").exists())

    def test_verify_code_strips_submitted_code(self):
        self.issue_code("strip-code@example.com", code="333333")

        self.assertTrue(verify_code("strip-code@example.com", " 333333 "))
        self.assertFalse(EmailVerificationCode.objects.filter(email="strip-code@example.com").exists())

    def test_get_remaining_cooldown_returns_zero_without_record(self):
        self.assertEqual(get_remaining_cooldown("no-record@example.com"), 0)

    @override_settings(EMAIL_VERIFICATION_CODE_RESEND_COOLDOWN=90)
    def test_get_remaining_cooldown_returns_positive_value_for_recent_record(self):
        self.issue_code("recent@example.com")

        remaining = get_remaining_cooldown("recent@example.com")

        self.assertGreater(remaining, 0)
        self.assertLessEqual(remaining, 90)
