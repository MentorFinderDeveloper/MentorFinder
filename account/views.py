import json
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpRequest

from account.models import User
from utils.utils_jwt import generate_jwt_token
from utils.utils_request import BAD_METHOD, request_failed, request_success
from utils.utils_require import CheckRequire, require

from utils.utils_jwt import check_jwt_token
from dataset.models import Mentor
from account.models import User, MentorFollow
from search.serializers import MentorSerializer

USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_-]+$")


@CheckRequire
def login(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))

    username = require(body, "username", "string", err_msg="Missing or error type of [username]")
    password = require(body, "password", "string", err_msg="Missing or error type of [password]")

    user = User.objects.filter(username=username).first()
    if user is None:
        user = User.objects.filter(email=username).first()

    if user is None:
        return request_failed(2, "User not found", 401)

    if user.check_password(password):
        return request_success({"token": generate_jwt_token(user.username), "role": user.role})

    return request_failed(2, "Wrong password", 401)


@CheckRequire
def register(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))

    username = require(body, "username", "string", err_msg="Missing or error type of [username]")
    password = require(body, "password", "string", err_msg="Missing or error type of [password]")
    email = require(body, "email", "string", err_msg="Missing or error type of [email]")

    username = username.strip()
    if username.strip() == "":
        return request_failed(-2, "Invalid parameters. [username] cannot be empty", 400)
    if not USERNAME_REGEX.fullmatch(username):
        return request_failed(
            -2,
            "Invalid parameters. [username] can only contain letters, digits, underscores, and hyphens",
            400,
        )
    if password.strip() == "":
        return request_failed(-2, "Invalid parameters. [password] cannot be empty", 400)
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return request_failed(
            -2,
            "Invalid parameters. [password] must be at least 8 characters and contain both letters and digits",
            400,
        )
    email = email.strip()
    if email == "":
        return request_failed(-2, "Invalid parameters. [email] format is invalid", 400)

    try:
        validate_email(email)
    except ValidationError:
        return request_failed(-2, "Invalid parameters. [email] format is invalid", 400)

    if User.objects.filter(username=username).exists():
        return request_failed(3, "User already exists", 409)

    if User.objects.filter(email=email).exists():
        return request_failed(4, "Email already exists", 409)

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        role="student",
    )
    return request_success({"token": generate_jwt_token(user.username), "role": user.role})

def _extract_token(req: HttpRequest) -> str:
    auth_header = req.headers.get("Authorization", "").strip()
    if auth_header == "":
        return ""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return auth_header

def _require_user(req: HttpRequest):
    token = _extract_token(req)
    if token == "":
        return None, request_failed(2, "Unauthorized", 401)

    token_data = check_jwt_token(token)
    if token_data is None:
        return None, request_failed(2, "Unauthorized", 401)

    username = str(token_data.get("username", "")).strip()
    user = User.objects.filter(username=username).first()
    if user is None:
        return None, request_failed(2, "User not found", 401)

    return user, None

@CheckRequire
def follow_mentor(req: HttpRequest, mentor_id: int):
    if req.method not in ["POST", "DELETE"]:
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    if user.role != "student":
        return request_failed(3, "Only students can follow mentors", 403)

    mentor = Mentor.objects.filter(id=mentor_id).first()
    if mentor is None:
        return request_failed(2, "Mentor not found", 404)

    if req.method == "POST":
        MentorFollow.objects.get_or_create(student=user, mentor=mentor)
        return request_success({"followed": True})

    MentorFollow.objects.filter(student=user, mentor=mentor).delete()
    return request_success({"followed": False})