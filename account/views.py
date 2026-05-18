import json
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpRequest
from django.db.models import Q
from django.utils.timezone import localtime

from account.models import MentorVerificationRequest, SubjectFollow, User, UserFollow, UserProfile
from utils.utils_jwt import generate_jwt_token
from utils.utils_request import BAD_METHOD, request_failed, request_success
from utils.utils_require import CheckRequire, MAX_CHAR_LENGTH, require

from utils.utils_jwt import check_jwt_token
from dataset.models import Mentor, Paper
from account.models import MentorFollow
from account.services.email_verification import (
    email_matches_bypass,
    get_remaining_cooldown,
    issue_verification_code,
    send_password_reset_email,
    send_verification_email,
    verify_code,
)
from search.serializers import MentorSerializer

USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_-]+$")
MANAGEABLE_ROLES = {
    User.ROLE_STUDENT,
    User.ROLE_MENTOR,
    User.ROLE_ADMIN,
    User.ROLE_BANNED,
}


def _validate_password(password: str):
    if password.strip() == "":
        return request_failed(-2, "Invalid parameters. [password] cannot be empty", 400)
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return request_failed(
            -2,
            "Invalid parameters. [password] must be at least 8 characters and contain both letters and digits",
            400,
        )
    return None


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
        return request_success({
            "token": generate_jwt_token(user.username),
            "username": user.username,
            "role": user.role,
            "userId": user.id,
        })

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
    password_error = _validate_password(password)
    if password_error is not None:
        return password_error
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

    # 邮箱验证码校验（"bypass" 前缀邮箱可跳过，方便测试，后续可删除该后门）
    verification_code_raw = body.get("verificationCode", "")
    if not isinstance(verification_code_raw, str):
        return request_failed(-2, "Invalid parameters. [verificationCode] must be a string", 400)
    verification_code = verification_code_raw.strip()
    if not email_matches_bypass(email):
        if verification_code == "":
            return request_failed(5, "Verification code is required", 400)
        if not verify_code(email, verification_code):
            return request_failed(5, "Verification code is invalid or expired", 400)

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        role="student",
    )
    return request_success({
        "token": generate_jwt_token(user.username),
        "role": user.role,
        "userId": user.id,
    })


@CheckRequire
def send_password_reset_verification_code(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))
    email_raw = require(body, "email", "string", err_msg="Missing or error type of [email]")
    email = email_raw.strip()
    if email == "":
        return request_failed(-2, "Invalid parameters. [email] format is invalid", 400)
    try:
        validate_email(email)
    except ValidationError:
        return request_failed(-2, "Invalid parameters. [email] format is invalid", 400)

    user = User.objects.filter(email=email).first()
    if user is None:
        return request_failed(2, "User not found", 404)
    if user.role == User.ROLE_BANNED:
        return request_failed(3, "User is banned", 403)

    if email_matches_bypass(email):
        return request_success({"bypass": True, "info": "Bypass email: no verification code required"})

    from django.conf import settings as _settings
    cooldown_remaining = get_remaining_cooldown(email)
    if cooldown_remaining > 0:
        return request_failed(
            6,
            f"Verification code was just sent, please wait {cooldown_remaining}s before retrying",
            429,
        )

    code, _record = issue_verification_code(email)
    try:
        send_password_reset_email(email, code)
    except Exception as exc:
        return request_failed(7, f"Failed to send verification email: {exc}", 502)

    return request_success({
        "bypass": False,
        "cooldownSeconds": int(getattr(_settings, "EMAIL_VERIFICATION_CODE_RESEND_COOLDOWN", 60)),
    })


@CheckRequire
def reset_password_with_email_code(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))
    email_raw = require(body, "email", "string", err_msg="Missing or error type of [email]")
    password = require(body, "password", "string", err_msg="Missing or error type of [password]")

    email = email_raw.strip()
    if email == "":
        return request_failed(-2, "Invalid parameters. [email] format is invalid", 400)
    try:
        validate_email(email)
    except ValidationError:
        return request_failed(-2, "Invalid parameters. [email] format is invalid", 400)

    password_error = _validate_password(password)
    if password_error is not None:
        return password_error

    user = User.objects.filter(email=email).first()
    if user is None:
        return request_failed(2, "User not found", 404)
    if user.role == User.ROLE_BANNED:
        return request_failed(3, "User is banned", 403)

    verification_code_raw = body.get("verificationCode", "")
    if not isinstance(verification_code_raw, str):
        return request_failed(-2, "Invalid parameters. [verificationCode] must be a string", 400)
    verification_code = verification_code_raw.strip()
    if not email_matches_bypass(email):
        if verification_code == "":
            return request_failed(5, "Verification code is required", 400)
        if not verify_code(email, verification_code):
            return request_failed(5, "Verification code is invalid or expired", 400)

    user.set_password(password)
    user.save(update_fields=["password"])
    return request_success({"username": user.username})


@CheckRequire
def send_email_verification_code(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))
    email_raw = require(body, "email", "string", err_msg="Missing or error type of [email]")
    email = email_raw.strip()
    if email == "":
        return request_failed(-2, "Invalid parameters. [email] format is invalid", 400)
    try:
        validate_email(email)
    except ValidationError:
        return request_failed(-2, "Invalid parameters. [email] format is invalid", 400)

    if User.objects.filter(email=email).exists():
        return request_failed(4, "Email already exists", 409)

    if email_matches_bypass(email):
        return request_success({"bypass": True, "info": "Bypass email: no verification code required"})

    from django.conf import settings as _settings
    cooldown_remaining = get_remaining_cooldown(email)
    if cooldown_remaining > 0:
        return request_failed(
            6,
            f"Verification code was just sent, please wait {cooldown_remaining}s before retrying",
            429,
        )

    code, _record = issue_verification_code(email)
    try:
        send_verification_email(email, code)
    except Exception as exc:
        return request_failed(7, f"Failed to send verification email: {exc}", 502)

    return request_success({
        "bypass": False,
        "cooldownSeconds": int(getattr(_settings, "EMAIL_VERIFICATION_CODE_RESEND_COOLDOWN", 60)),
    })

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


def _serialize_verification_request(request_obj: MentorVerificationRequest):
    return request_obj.serialize()


def _serialize_follow_user(user: User, current_user: User | None = None):
    profile = getattr(user, "profile", None)
    followed = False
    if current_user is not None:
        followed = UserFollow.objects.filter(follower=current_user, following=user).exists()

    return {
        "id": user.id,
        "username": user.username,
        "realName": user.real_name,
        "role": user.role,
        "avatarUrl": profile.avatar_url if profile is not None else "",
        "signature": profile.signature if profile is not None else "",
        "followed": followed,
    }


def _split_subjects(subjects: str | None) -> list[str]:
    if not subjects:
        return []
    return [subject.strip() for subject in subjects.split(",") if subject.strip()]


def _collect_subject_counts() -> dict[str, int]:
    subject_counts: dict[str, int] = {}
    subjects_query = Paper.objects.values_list("subjects", flat=True).iterator(chunk_size=500)
    for subjects in subjects_query:
        for subject in _split_subjects(subjects):
            subject_counts[subject] = subject_counts.get(subject, 0) + 1
    return subject_counts


def _papers_for_subject(subject: str):
    return [
        paper
        for paper in Paper.objects.filter(subjects__icontains=subject).order_by("-publish_date", "-id")
        if subject in _split_subjects(paper.subjects)
    ]


def _serialize_subject_paper(paper: Paper):
    return {
        "id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract,
        "tldr": paper.tldr,
        "publish_date": str(paper.publish_date) if paper.publish_date else "",
        "author_names": paper.author_names,
        "subjects": paper.subjects,
        "arxiv_id": paper.arxiv_id,
        "arxiv_url": paper.arxiv_url,
        "mentor_ids": paper.get_author_mentor_ids(),
    }


def _serialize_subject_follow(subject: str, subject_counts: dict[str, int] | None = None):
    counts = subject_counts if subject_counts is not None else _collect_subject_counts()
    papers = _papers_for_subject(subject)
    return {
        "subject": subject,
        "paperCount": counts.get(subject, len(papers)),
        "recentPapers": [_serialize_subject_paper(paper) for paper in papers[:8]],
    }


def _serialize_public_user_profile(user: User, current_user: User):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    serialized_user = _serialize_follow_user(user, current_user)
    serialized_user["isSelf"] = user.id == current_user.id
    serialized_user["profile"] = {
        "personalIntro": profile.personal_intro if profile.show_personal_intro else "",
        "researchExperience": profile.research_experience if profile.show_research_experience else "",
        "honors": profile.honors if profile.show_honors else "",
        "projectExperience": profile.project_experience if profile.show_project_experience else "",
        "showPersonalIntro": profile.show_personal_intro,
        "showResearchExperience": profile.show_research_experience,
        "showHonors": profile.show_honors,
        "showProjectExperience": profile.show_project_experience,
        "updatedAt": localtime(profile.updated_at).isoformat(sep=" ", timespec="seconds") if profile.updated_at else "",
    }
    return serialized_user


def _validate_verification_review_payload(body: dict):
    status = require(body, "status", "string", err_msg="Missing or error type of [status]").strip().lower()
    if status not in {
        MentorVerificationRequest.STATUS_APPROVED,
        MentorVerificationRequest.STATUS_REJECTED,
    }:
        raise KeyError("Invalid parameters. [status] is invalid", -2)

    mentor = None
    mentor_id_raw = body.get("mentorId")
    if status == MentorVerificationRequest.STATUS_APPROVED:
        if mentor_id_raw in (None, ""):
            raise KeyError("Mentor binding is required for approval", 3)
        try:
            mentor_id = int(mentor_id_raw)
        except (TypeError, ValueError) as exc:
            raise KeyError("Invalid parameters. [mentorId] must be an integer", -2) from exc

        mentor = Mentor.objects.filter(id=mentor_id, owner__isnull=True).first()
        if mentor is None:
            raise KeyError("Mentor not found", 2)

    return status, mentor


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
    role_filter = str(req.GET.get("role", "")).strip().lower()
    users = User.objects.select_related("mentor_profile").order_by("id")

    if role_filter != "":
        if role_filter not in MANAGEABLE_ROLES:
            return request_failed(-2, "Invalid parameters. [role] is invalid", 400)
        users = users.filter(role=role_filter)

    if keyword != "":
        if len(keyword) > MAX_CHAR_LENGTH:
            return request_failed(-2, "Invalid parameters. [keyword] is too long", 400)
        users = users.filter(
            Q(username__icontains=keyword) |
            Q(email__icontains=keyword) |
            Q(real_name__icontains=keyword)
        )

    return request_success({
        "users": [_serialize_admin_user(user) for user in users],
        "verificationRequests": [
            _serialize_verification_request(request_obj)
            for request_obj in MentorVerificationRequest.objects.select_related("user").all()
        ],
        "currentUserId": admin_user.id,
        "roleFilter": role_filter,
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
def admin_verification_request_detail(req: HttpRequest, request_id: int):
    admin_user, auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

    if req.method != "PUT":
        return BAD_METHOD

    request_obj = (
        MentorVerificationRequest.objects
        .select_related("user")
        .filter(id=request_id)
        .first()
    )
    if request_obj is None:
        return request_failed(2, "Verification request not found", 404)

    body = json.loads(req.body.decode("utf-8"))
    if not isinstance(body, dict):
        return request_failed(-2, "Invalid parameters. [body] must be an object", 400)

    status, mentor = _validate_verification_review_payload(body)
    if request_obj.status != MentorVerificationRequest.STATUS_PENDING:
        return request_failed(3, "Verification request has already been reviewed", 409)

    target_user = request_obj.user

    if status == MentorVerificationRequest.STATUS_APPROVED:
        transition_error = _apply_user_role(target_user, User.ROLE_MENTOR, mentor)
        if transition_error is not None:
            return transition_error
    else:
        if target_user.role == User.ROLE_MENTOR and target_user.mentor_profile_id is not None:
            target_user.role = User.ROLE_STUDENT
            target_user.mentor_profile = None
            target_user.save(update_fields=["role", "mentor_profile"])

    request_obj.status = status
    request_obj.save(update_fields=["status", "updated_at"])

    return request_success({
        "verificationRequest": _serialize_verification_request(request_obj),
        "user": _serialize_admin_user(target_user),
        "reviewedByUserId": admin_user.id,
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
def followed_users(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    follows = (
        UserFollow.objects
        .filter(follower=user)
        .select_related("following", "following__profile")
    )
    users = [
        _serialize_follow_user(follow.following, user)
        for follow in follows
        if follow.following.role != User.ROLE_BANNED
    ]

    return request_success({
        "users": users,
    })


@CheckRequire
def followed_subjects(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    subject_counts = _collect_subject_counts()
    followed_subjects_set = set(
        SubjectFollow.objects.filter(user=user).values_list("subject", flat=True)
    )
    available_subjects = [
        {
            "subject": subject,
            "paperCount": count,
            "followed": subject in followed_subjects_set,
        }
        for subject, count in sorted(subject_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    followed_subjects_data = [
        _serialize_subject_follow(subject, subject_counts)
        for subject in SubjectFollow.objects.filter(user=user).values_list("subject", flat=True)
    ]

    return request_success({
        "subjects": followed_subjects_data,
        "availableSubjects": available_subjects,
    })


@CheckRequire
def follow_subject(req: HttpRequest, subject: str):
    if req.method not in ["POST", "DELETE"]:
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    normalized_subject = subject.strip()
    if normalized_subject == "":
        return request_failed(-2, "Invalid parameters. [subject] cannot be empty", 400)
    if len(normalized_subject) > 100:
        return request_failed(-2, "Invalid parameters. [subject] is too long", 400)

    subject_counts = _collect_subject_counts()
    if normalized_subject not in subject_counts:
        return request_failed(2, "Subject not found", 404)

    if req.method == "POST":
        SubjectFollow.objects.get_or_create(user=user, subject=normalized_subject)
        return request_success({
            "followed": True,
            "subject": _serialize_subject_follow(normalized_subject, subject_counts),
        })

    SubjectFollow.objects.filter(user=user, subject=normalized_subject).delete()
    return request_success({
        "followed": False,
        "subject": normalized_subject,
    })


@CheckRequire
def follower_users(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    seen_user_ids = set()
    users = []

    def append_follower(follower: User):
        if follower.id == user.id or follower.role == User.ROLE_BANNED or follower.id in seen_user_ids:
            return
        seen_user_ids.add(follower.id)
        users.append(_serialize_follow_user(follower, user))

    user_follows = (
        UserFollow.objects
        .filter(following=user)
        .select_related("follower", "follower__profile")
    )
    for follow in user_follows:
        append_follower(follow.follower)

    if user.role == User.ROLE_MENTOR and user.mentor_profile_id is not None:
        mentor_follows = (
            MentorFollow.objects
            .filter(mentor_id=user.mentor_profile_id)
            .select_related("student", "student__profile")
        )
        for follow in mentor_follows:
            append_follower(follow.student)

    return request_success({
        "users": users,
    })


@CheckRequire
def search_users(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    keyword = str(req.GET.get("keyword", "")).strip()
    if len(keyword) > MAX_CHAR_LENGTH:
        return request_failed(-2, "Invalid parameters. [keyword] is too long", 400)

    users = (
        User.objects
        .exclude(id=user.id)
        .exclude(role=User.ROLE_BANNED)
        .select_related("profile")
        .order_by("id")
    )
    if keyword != "":
        users = users.filter(
            Q(username__icontains=keyword) |
            Q(real_name__icontains=keyword) |
            Q(email__icontains=keyword)
        )

    return request_success({
        "users": [_serialize_follow_user(match, user) for match in users[:20]],
        "keyword": keyword,
    })


@CheckRequire
def follow_user(req: HttpRequest, user_id: int):
    if req.method not in ["POST", "DELETE"]:
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    if user.id == user_id:
        return request_failed(3, "Cannot follow yourself", 400)

    target_user = User.objects.filter(id=user_id).first()
    if target_user is None or target_user.role == User.ROLE_BANNED:
        return request_failed(2, "User not found", 404)

    if req.method == "POST":
        UserFollow.objects.get_or_create(follower=user, following=target_user)
        return request_success({"followed": True})

    UserFollow.objects.filter(follower=user, following=target_user).delete()
    return request_success({"followed": False})


@CheckRequire
def public_user_profile(req: HttpRequest, user_id: int):
    if req.method != "GET":
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    target_user = User.objects.select_related("profile").filter(id=user_id).first()
    if target_user is None or target_user.role == User.ROLE_BANNED:
        return request_failed(2, "User not found", 404)

    return request_success({
        "user": _serialize_public_user_profile(target_user, user),
    })


@CheckRequire
def follow_mentor(req: HttpRequest, mentor_id: int):
    if req.method not in ["POST", "DELETE"]:
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

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
        verification_request = (
            MentorVerificationRequest.objects
            .filter(user=user)
            .order_by("-created_at")
            .first()
        )
        return request_success({
            "userId": user.id,
            "profile": profile.serialize(),
            "mentorVerificationRequest": (
                _serialize_verification_request(verification_request)
                if verification_request is not None else None
            ),
        })

    if req.method == "PUT":
        user, auth_error = _require_user(req)
        if auth_error is not None:
            return auth_error

        body = json.loads(req.body.decode("utf-8"))
        if not isinstance(body, dict):
            return request_failed(-2, "Invalid parameters. [body] must be an object", 400)

        profile, _ = UserProfile.objects.get_or_create(user=user)

        string_fields = {
            "avatarUrl": "avatar_url",
            "signature": "signature",
            "personalIntro": "personal_intro",
            "researchExperience": "research_experience",
            "honors": "honors",
            "projectExperience": "project_experience",
        }
        bool_fields = {
            "showPersonalIntro": "show_personal_intro",
            "showResearchExperience": "show_research_experience",
            "showHonors": "show_honors",
            "showProjectExperience": "show_project_experience",
        }

        for request_key, model_field in string_fields.items():
            if request_key not in body:
                continue
            value = body[request_key]
            if not isinstance(value, str):
                return request_failed(-2, f"Invalid parameters. [{request_key}] must be a string", 400)
            setattr(profile, model_field, value.strip())

        for request_key, model_field in bool_fields.items():
            if request_key not in body:
                continue
            value = body[request_key]
            if not isinstance(value, bool):
                return request_failed(-2, f"Invalid parameters. [{request_key}] must be a boolean", 400)
            setattr(profile, model_field, value)

        profile.save()

        return request_success({"profile": profile.serialize()})

    return BAD_METHOD


@CheckRequire
def mentor_verification_request(req: HttpRequest):
    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))
    if not isinstance(body, dict):
        return request_failed(-2, "Invalid parameters. [body] must be an object", 400)

    submitted_name = require(
        body,
        "submittedName",
        "string",
        err_msg="Missing or error type of [submittedName]",
    ).strip()
    if submitted_name == "":
        return request_failed(-2, "Invalid parameters. [submittedName] cannot be empty", 400)
    if len(submitted_name) > 100:
        return request_failed(-2, "Invalid parameters. [submittedName] is too long", 400)

    latest_request = (
        MentorVerificationRequest.objects
        .filter(user=user)
        .order_by("-created_at")
        .first()
    )
    if latest_request is not None and latest_request.status == MentorVerificationRequest.STATUS_PENDING:
        return request_failed(3, "A pending mentor verification request already exists", 409)

    request_obj = MentorVerificationRequest.objects.create(
        user=user,
        submitted_name=submitted_name,
    )
    return request_success({
        "mentorVerificationRequest": _serialize_verification_request(request_obj),
    })
