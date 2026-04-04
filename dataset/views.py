from django.shortcuts import render

import json

from django.http import HttpRequest

from dataset.models import Mentor, Paper
from utils.utils_request import BAD_METHOD, request_failed, request_success
from utils.utils_require import CheckRequire, MAX_CHAR_LENGTH, require


@CheckRequire
def create_paper(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))

    title = require(body, "title", "string", err_msg="Missing or error type of [title]").strip()
    if title == "":
        return request_failed(-2, "Invalid parameters. [title] cannot be empty", 400)
    if len(title) > MAX_CHAR_LENGTH:
        return request_failed(-2, "Invalid parameters. [title] is too long", 400)

    abstract = str(body.get("abstract", "")).strip()
    author_names = str(body.get("author_names", "")).strip()
    publish_date = body.get("publish_date")

    if abstract and len(abstract) > 5000:
        return request_failed(-2, "Invalid parameters. [abstract] is too long", 400)
    if author_names and len(author_names) > 5000:
        return request_failed(-2, "Invalid parameters. [author_names] is too long", 400)

    paper = Paper.objects.create(
        title=title,
        abstract=abstract or None,
        publish_date=publish_date if publish_date else None,
        author_names=author_names,
    )

    paper.bind_to_mentors_by_authors()

    return request_success({
        "paper": {
            "id": paper.id,
            "title": paper.title,
            "abstract": paper.abstract,
            "publish_date": paper.publish_date,
            "author_names": paper.author_names,
        }
    })


@CheckRequire
def create_mentor(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    body = json.loads(req.body.decode("utf-8"))

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
        return request_failed(-2, "Invalid parameters. [Chinese_name] cannot be empty", 400)
    if research_direction == "":
        return request_failed(-2, "Invalid parameters. [research_direction] cannot be empty", 400)

    if len(chinese_name) > 100:
        return request_failed(-2, "Invalid parameters. [Chinese_name] is too long", 400)
    if len(research_direction) > MAX_CHAR_LENGTH:
        return request_failed(-2, "Invalid parameters. [research_direction] is too long", 400)

    english_name = str(body.get("English_name", "")).strip()
    email = str(body.get("email", "")).strip()
    profile = str(body.get("profile", "")).strip()
    paper_ids = ""

    if english_name and len(english_name) > 100:
        return request_failed(-2, "Invalid parameters. [English_name] is too long", 400)
    if email and "@" not in email:
        return request_failed(-2, "Invalid parameters. [email] format is invalid", 400)

    mentor = Mentor.objects.create(
        Chinese_name=chinese_name,
        English_name=english_name or None,
        research_direction=research_direction,
        email=email or None,
        profile=profile or None,
        paper_ids=paper_ids,
    )

    return request_success({
        "mentor": {
            "id": mentor.id,
            "Chinese_name": mentor.Chinese_name,
            "English_name": mentor.English_name,
            "research_direction": mentor.research_direction,
            "email": mentor.email,
            "profile": mentor.profile,
            "paper_ids": mentor.paper_ids,
        }
    })

