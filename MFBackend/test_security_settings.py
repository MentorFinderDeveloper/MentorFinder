import json

from django.conf import settings
from django.test import Client, SimpleTestCase


class SecuritySettingsTests(SimpleTestCase):
    def test_csrf_middleware_is_enabled(self):
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)

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
