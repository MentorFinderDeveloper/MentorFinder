import json
import re

from django.contrib.auth.hashers import check_password, make_password
from django.http import HttpRequest

from account.models import User
from utils.utils_jwt import generate_jwt_token
from utils.utils_request import BAD_METHOD, request_failed, request_success
from utils.utils_require import CheckRequire, require


@CheckRequire
def login(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))

    username = require(body, "username", "string", err_msg="Missing or error type of [username]")
    password = require(body, "password", "string", err_msg="Missing or error type of [password]")

    user = User.objects.filter(name=username).first()
    if user is None:
        user = User.objects.filter(email=username).first()

    if user is None:
        return request_failed(2, "User not found", 401)

    if check_password(password, user.password):
        return request_success({"token": generate_jwt_token(user.name)})

    # Backward compatibility for legacy plain-text records.
    if user.password == password:
        user.password = make_password(password)
        user.save(update_fields=["password"])
        return request_success({"token": generate_jwt_token(user.name)})

    return request_failed(2, "Wrong password", 401)


@CheckRequire
def register(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))

    username = require(body, "username", "string", err_msg="Missing or error type of [username]")
    password = require(body, "password", "string", err_msg="Missing or error type of [password]")
    email = require(body, "email", "string", err_msg="Missing or error type of [email]")

    if username.strip() == "":
        return request_failed(-2, "Invalid parameters. [username] cannot be empty", 400)
    if password.strip() == "":
        return request_failed(-2, "Invalid parameters. [password] cannot be empty", 400)
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return request_failed(
            -2,
            "Invalid parameters. [password] must be at least 8 characters and contain both letters and digits",
            400,
        )
    if email.strip() == "" or "@" not in email:
        return request_failed(-2, "Invalid parameters. [email] format is invalid", 400)

    if User.objects.filter(name=username).exists():
        return request_failed(3, "User already exists", 409)

    if User.objects.filter(email=email).exists():
        return request_failed(4, "Email already exists", 409)

    User.objects.create(name=username, password=make_password(password), email=email)
    return request_success({"token": generate_jwt_token(username)})
