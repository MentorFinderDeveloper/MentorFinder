import json

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpRequest

from account.models import User
from dataset.models import Mentor, Paper
from utils.utils_jwt import check_jwt_token
from utils.utils_request import BAD_METHOD, request_failed, request_success
from utils.utils_require import CheckRequire, MAX_CHAR_LENGTH, require


def _extract_token(req: HttpRequest) -> str:
    auth_header = req.headers.get("Authorization", "").strip()
    if auth_header == "":
        return ""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return auth_header


def _require_admin(req: HttpRequest):
    token = _extract_token(req)
    if token == "":
        return request_failed(2, "Unauthorized", 401)

    token_data = check_jwt_token(token)
    if token_data is None:
        return request_failed(2, "Unauthorized", 401)

    username = str(token_data.get("username", "")).strip()
    if username == "":
        return request_failed(2, "Unauthorized", 401)

    user = User.objects.filter(username=username).first()
    if user is None:
        return request_failed(2, "User not found", 401)

    if user.role != "admin":
        return request_failed(3, "Permission denied", 403)

    return None


def _serialize_paper(paper: Paper):
    return {
        "id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract,
        "publish_date": paper.publish_date,
        "author_names": paper.author_names,
    }


def _serialize_mentor(mentor: Mentor):
    return {
        "id": mentor.id,
        "Chinese_name": mentor.Chinese_name,
        "English_name": mentor.English_name,
        "research_direction": mentor.research_direction,
        "email": mentor.email,
        "profile": mentor.profile,
        "paper_ids": mentor.paper_ids,
    }


def _validate_paper_payload(body: dict):
    title = require(body, "title", "string", err_msg="Missing or error type of [title]").strip()
    if title == "":
        raise KeyError("Invalid parameters. [title] cannot be empty", -2)
    if len(title) > MAX_CHAR_LENGTH:
        raise KeyError("Invalid parameters. [title] is too long", -2)

    abstract = str(body.get("abstract", "")).strip()
    author_names = str(body.get("author_names", "")).strip()
    publish_date = body.get("publish_date")

    if abstract and len(abstract) > 5000:
        raise KeyError("Invalid parameters. [abstract] is too long", -2)
    if author_names and len(author_names) > 5000:
        raise KeyError("Invalid parameters. [author_names] is too long", -2)

    return {
        "title": title,
        "abstract": abstract or None,
        "publish_date": publish_date if publish_date else None,
        "author_names": author_names,
    }


def _validate_mentor_payload(body: dict):
    chinese_name = require(
        body,
        "Chinese_name",
        "string",
        err_msg="Missing or error type of [Chinese_name]",
    ).strip()
    research_direction = require(
        body,
        "research_direction",
        "string",
        err_msg="Missing or error type of [research_direction]",
    ).strip()

    if chinese_name == "":
        raise KeyError("Invalid parameters. [Chinese_name] cannot be empty", -2)
    if research_direction == "":
        raise KeyError("Invalid parameters. [research_direction] cannot be empty", -2)

    if len(chinese_name) > 100:
        raise KeyError("Invalid parameters. [Chinese_name] is too long", -2)
    if len(research_direction) > MAX_CHAR_LENGTH:
        raise KeyError("Invalid parameters. [research_direction] is too long", -2)

    english_name = str(body.get("English_name", "")).strip()
    email = str(body.get("email", "")).strip()
    profile = str(body.get("profile", "")).strip()

    if english_name and len(english_name) > 100:
        raise KeyError("Invalid parameters. [English_name] is too long", -2)
    if email:
        try:
            validate_email(email)
        except ValidationError:
            raise KeyError("Invalid parameters. [email] format is invalid", -2)

    return {
        "Chinese_name": chinese_name,
        "English_name": english_name or None,
        "research_direction": research_direction,
        "email": email or None,
        "profile": profile or None,
    }


def _refresh_mentor_papers(mentor: Mentor):
    paper_ids = []
    for paper in Paper.objects.all():
        author_list = paper.get_author_list()
        if mentor.Chinese_name in author_list or (
            mentor.English_name and mentor.English_name in author_list
        ):
            paper_ids.append(paper.id)
    mentor.set_paper_id_list(paper_ids)
    mentor.save()


def _detach_paper_from_mentors(paper_id: int):
    for mentor in Mentor.objects.all():
        id_list = mentor.get_paper_id_list()
        if paper_id in id_list:
            mentor.set_paper_id_list([pid for pid in id_list if pid != paper_id])
            mentor.save()


@CheckRequire
def create_paper(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

    body = json.loads(req.body.decode("utf-8"))
    paper_payload = _validate_paper_payload(body)

    paper = Paper.objects.create(**paper_payload)

    paper.bind_to_mentors_by_authors()

    return request_success({"paper": _serialize_paper(paper)})


@CheckRequire
def create_mentor(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

    body = json.loads(req.body.decode("utf-8"))
    mentor_payload = _validate_mentor_payload(body)

    mentor = Mentor.objects.create(**mentor_payload, paper_ids="")
    _refresh_mentor_papers(mentor)

    return request_success({"mentor": _serialize_mentor(mentor)})


@CheckRequire
def paper_detail(req: HttpRequest, paper_id: int):
    if req.method not in ["PUT", "DELETE"]:
        return BAD_METHOD

    auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

    paper = Paper.objects.filter(id=paper_id).first()
    if paper is None:
        return request_failed(2, "Paper not found", 404)

    if req.method == "DELETE":
        _detach_paper_from_mentors(paper.id)
        paper.delete()
        return request_success()

    body = json.loads(req.body.decode("utf-8"))
    paper_payload = _validate_paper_payload(body)
    for key, value in paper_payload.items():
        setattr(paper, key, value)
    paper.save()

    _detach_paper_from_mentors(paper.id)
    paper.bind_to_mentors_by_authors()

    return request_success({"paper": _serialize_paper(paper)})


@CheckRequire
def mentor_detail(req: HttpRequest, mentor_id: int):
    if req.method not in ["PUT", "DELETE"]:
        return BAD_METHOD

    auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

    mentor = Mentor.objects.filter(id=mentor_id).first()
    if mentor is None:
        return request_failed(2, "Mentor not found", 404)

    if req.method == "DELETE":
        mentor.delete()
        return request_success()

    body = json.loads(req.body.decode("utf-8"))
    mentor_payload = _validate_mentor_payload(body)
    for key, value in mentor_payload.items():
        setattr(mentor, key, value)
    mentor.save()

    _refresh_mentor_papers(mentor)

    return request_success({"mentor": _serialize_mentor(mentor)})

