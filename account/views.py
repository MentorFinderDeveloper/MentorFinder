import json

from django.http import HttpRequest

from board.models import User
from utils.utils_jwt import generate_jwt_token
from utils.utils_request import BAD_METHOD, request_failed, request_success
from utils.utils_require import CheckRequire, require


@CheckRequire
def login(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))

    username = require(body, "userName", "string", err_msg="Missing or error type of [userName]")
    password = require(body, "password", "string", err_msg="Missing or error type of [password]")

    user = User.objects.filter(name=username).first()

    if user is None:
        User.objects.create(name=username, password=password)
        return request_success({"token": generate_jwt_token(username)})

    if user.password == password:
        return request_success({"token": generate_jwt_token(username)})

    return request_failed(2, "Wrong password", 401)


@CheckRequire
def register(req: HttpRequest):
    # Keep backward-compatible behavior with the existing combined login/register logic.
    return login(req)
