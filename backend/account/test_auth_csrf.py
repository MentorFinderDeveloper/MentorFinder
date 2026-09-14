"""Exercise browser authentication requests with CSRF middleware enforced."""

from django.core import mail
from django.test import Client, TestCase, override_settings

from account.models import EmailVerificationCode, User


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PublicAuthenticationCsrfTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def post_json(self, path, data):
        bootstrap = self.client.get("/csrf")
        self.assertEqual(bootstrap.status_code, 200)
        self.assertIn("no-store", bootstrap.headers["Cache-Control"])
        self.assertIn("csrftoken", bootstrap.cookies)
        return self.client.post(
            path, data=data, content_type="application/json",
            HTTP_X_CSRFTOKEN=bootstrap.json()["csrfToken"],
        )

    def test_registration_and_login_bootstrap_csrf_cookie(self):
        email = "new@example.com"
        response = self.post_json("/register/verification-code", {"email": email})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        code = EmailVerificationCode.objects.get(email=email).code
        self.assertIn(code, mail.outbox[0].body)

        cooldown = self.post_json("/register/verification-code", {"email": email})
        self.assertEqual(cooldown.status_code, 429)
        self.assertEqual(len(mail.outbox), 1)

        response = self.post_json("/register", {
            "username": "new_user", "email": email, "password": "abc12345",
            "verificationCode": code,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token"])
        self.assertNotIn("sessionid", response.cookies)

        response = self.post_json("/login", {
            "username": "new_user", "password": "abc12345",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token"])
        self.assertNotIn("sessionid", response.cookies)

    def test_password_reset_still_requires_valid_code(self):
        email = "existing@example.com"
        user = User.objects.create_user(
            username="existing", email=email, password="abc12345",
        )
        response = self.post_json("/password-reset/verification-code", {"email": email})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        code = EmailVerificationCode.objects.get(email=email).code
        payload = {"email": email, "password": "changed123", "verificationCode": ""}
        self.assertEqual(self.post_json("/password-reset", payload).status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password("abc12345"))

        payload["verificationCode"] = code
        self.assertEqual(self.post_json("/password-reset", payload).status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("changed123"))

    def test_admin_login_remains_csrf_protected(self):
        response = self.client.post("/admin/login/", {
            "username": "admin", "password": "password",
        })
        self.assertEqual(response.status_code, 403)

    def test_authentication_posts_without_token_remain_rejected(self):
        for path in ("/login", "/register", "/register/verification-code",
                     "/password-reset", "/password-reset/verification-code"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, {}, content_type="application/json").status_code, 403)

    def test_cross_origin_post_is_rejected_even_with_token(self):
        token = self.client.get("/csrf").json()["csrfToken"]
        response = self.client.post(
            "/register/verification-code", {"email": "new@example.com"},
            content_type="application/json", HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://untrusted.example",
        )
        self.assertEqual(response.status_code, 403)
