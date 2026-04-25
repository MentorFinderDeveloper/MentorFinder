import json
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpRequest

from account.models import User, UserProfile
from utils.utils_jwt import generate_jwt_token
from utils.utils_request import BAD_METHOD, request_failed, request_success
from utils.utils_require import CheckRequire, MAX_CHAR_LENGTH, require

from utils.utils_jwt import check_jwt_token
from dataset.models import Mentor
from account.models import MentorFollow
from search.serializers import MentorSerializer

USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_-]+$")
MANAGEABLE_ROLES = {
    User.ROLE_STUDENT,
    User.ROLE_MENTOR,
    User.ROLE_ADMIN,
    User.ROLE_BANNED,
}


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

    if user.role == User.ROLE_BANNED:
        return request_failed(3, "User is banned", 403)

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
    if user.role == User.ROLE_BANNED:
        return None, request_failed(3, "User is banned", 403)

    return user, None


def _require_admin(req: HttpRequest):
    user, auth_error = _require_user(req)
    if auth_error is not None:
        return None, auth_error
    if user.role != User.ROLE_ADMIN:
        return None, request_failed(3, "Permission denied", 403)
    return user, None


def _serialize_admin_user(user: User):
    serialized = user.serialize()
    serialized["isBoundToMentor"] = user.mentor_profile_id is not None
    return serialized


def _validate_user_role_payload(body: dict):
    role = require(body, "role", "string", err_msg="Missing or error type of [role]").strip().lower()
    if role not in MANAGEABLE_ROLES:
        raise KeyError("Invalid parameters. [role] is invalid", -2)

    mentor_id_raw = body.get("mentorId")
    mentor = None
    if mentor_id_raw not in (None, ""):
        try:
            mentor_id = int(mentor_id_raw)
        except (TypeError, ValueError) as exc:
            raise KeyError("Invalid parameters. [mentorId] must be an integer", -2) from exc

        mentor = Mentor.objects.filter(id=mentor_id, owner__isnull=True).first()
        if mentor is None:
            raise KeyError("Mentor not found", 2)

    return role, mentor


def _apply_user_role(target_user: User, role: str, mentor: Mentor | None):
    if role == User.ROLE_MENTOR:
        if mentor is None:
            return request_failed(3, "Mentor binding is required for mentor role", 400)

        occupied_user = User.objects.filter(mentor_profile=mentor).exclude(id=target_user.id).first()
        if occupied_user is not None:
            return request_failed(3, "Mentor is already bound to another user", 409)

        target_user.role = User.ROLE_MENTOR
        target_user.mentor_profile = mentor
        target_user.save(update_fields=["role", "mentor_profile"])
        return None

    if mentor is not None:
        return request_failed(3, "Only mentor role can bind a mentor profile", 400)

    target_user.role = role
    target_user.mentor_profile = None
    target_user.save(update_fields=["role", "mentor_profile"])
    return None


@CheckRequire
def admin_users(req: HttpRequest):
    admin_user, auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

    if req.method != "GET":
        return BAD_METHOD

    keyword = str(req.GET.get("keyword", "")).strip()
    users = User.objects.select_related("mentor_profile").order_by("id")
    if keyword != "":
        if len(keyword) > MAX_CHAR_LENGTH:
            return request_failed(-2, "Invalid parameters. [keyword] is too long", 400)
        users = users.filter(username__icontains=keyword)

    return request_success({
        "users": [_serialize_admin_user(user) for user in users],
        "currentUserId": admin_user.id,
    })


@CheckRequire
def admin_user_detail(req: HttpRequest, user_id: int):
    admin_user, auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

    if req.method != "PUT":
        return BAD_METHOD

    target_user = User.objects.select_related("mentor_profile").filter(id=user_id).first()
    if target_user is None:
        return request_failed(2, "User not found", 404)

    body = json.loads(req.body.decode("utf-8"))
    if not isinstance(body, dict):
        return request_failed(-2, "Invalid parameters. [body] must be an object", 400)

    role, mentor = _validate_user_role_payload(body)

    if target_user.id == admin_user.id and role == User.ROLE_BANNED:
        return request_failed(3, "Admin cannot ban self", 400)

    transition_error = _apply_user_role(target_user, role, mentor)
    if transition_error is not None:
        return transition_error

    return request_success({
        "user": _serialize_admin_user(target_user),
    })

@CheckRequire
def followed_mentors(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    follows = MentorFollow.objects.filter(student=user).select_related("mentor")
    mentors = [follow.mentor for follow in follows if follow.mentor.is_visible_to(user)]

    return request_success({
        "mentors": MentorSerializer(mentors, many=True).data,
    })


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
    if not mentor.is_visible_to(user):
        return request_failed(2, "Mentor not found", 404)

    if req.method == "POST":
        MentorFollow.objects.get_or_create(student=user, mentor=mentor)
        return request_success({"followed": True})

    MentorFollow.objects.filter(student=user, mentor=mentor).delete()
    return request_success({"followed": False})


@CheckRequire
def my_profile(req: HttpRequest):
    if req.method == "GET":
        user, auth_error = _require_user(req)
        if auth_error is not None:
            return auth_error

        profile, _ = UserProfile.objects.get_or_create(user=user)
        return request_success({"profile": profile.serialize()})

    if req.method == "PUT":
        user, auth_error = _require_user(req)
        if auth_error is not None:
            return auth_error

        body = json.loads(req.body.decode("utf-8"))
        if not isinstance(body, dict):
            return request_failed(-2, "Invalid parameters. [body] must be an object", 400)

        research_experience = body.get("researchExperience", "")
        honors = body.get("honors", "")
        project_experience = body.get("projectExperience", "")

        if not isinstance(research_experience, str):
            return request_failed(-2, "Invalid parameters. [researchExperience] must be a string", 400)
        if not isinstance(honors, str):
            return request_failed(-2, "Invalid parameters. [honors] must be a string", 400)
        if not isinstance(project_experience, str):
            return request_failed(-2, "Invalid parameters. [projectExperience] must be a string", 400)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.research_experience = research_experience.strip()
        profile.honors = honors.strip()
        profile.project_experience = project_experience.strip()
        profile.save()

        return request_success({"profile": profile.serialize()})

    return BAD_METHOD
