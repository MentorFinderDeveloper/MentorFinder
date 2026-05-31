import json

from django.conf import settings
from django.test import Client, SimpleTestCase


class SecuritySettingsTests(SimpleTestCase):
    def test_csrf_middleware_is_enabled(self):
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)

    def test_allowed_hosts_does_not_allow_every_host(self):
        self.assertNotIn("*", settings.ALLOWED_HOSTS)

    def test_production_security_headers_and_cookies_are_enabled(self):
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertGreater(settings.SECURE_HSTS_SECONDS, 0)
        self.assertTrue(settings.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertTrue(settings.SECURE_HSTS_PRELOAD)
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.SECURE_REFERRER_POLICY, "same-origin")
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")

    def test_unknown_host_is_rejected(self):
        response = Client(HTTP_HOST="attacker.example").get("/admin/")

        self.assertEqual(response.status_code, 400)

    def test_django_admin_is_not_exposed_by_default(self):
        response = Client().get("/admin/")

        self.assertEqual(response.status_code, 404)

    def test_json_api_is_explicitly_exempt_from_cookie_csrf(self):
        response = Client(enforce_csrf_checks=True).post(
            "/login",
            data=json.dumps({"username": "missing", "password": "wrongpass"}),
            content_type="application/json",
        )

        self.assertNotEqual(response.status_code, 403)
