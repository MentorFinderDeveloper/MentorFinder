import json

from django.contrib.auth.hashers import check_password, make_password
from django.test import TestCase

from account.models import User


class AccountAuthTests(TestCase):
    def setUp(self):
        User.objects.create(name="Ashitemaru", password=make_password("abc12345"), email="ashitemaru@example.com")

    def post_json(self, path: str, payload: dict):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def test_login_existing_user_correct_password(self):
        res = self.post_json("/login", {"username": "Ashitemaru", "password": "abc12345"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(res.json()["token"].count(".") == 2)

    def test_login_with_email_correct_password(self):
        res = self.post_json("/login", {"username": "ashitemaru@example.com", "password": "abc12345"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertTrue(res.json()["token"].count(".") == 2)

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
        user = User.objects.filter(name="NewUser", email="newuser@example.com").first()
        self.assertIsNotNone(user)
        self.assertNotEqual(user.password, "abc12345")
        self.assertTrue(check_password("abc12345", user.password))

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
