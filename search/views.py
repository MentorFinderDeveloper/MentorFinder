from django.http import HttpRequest

from account.models import User
from search.services.engine import (
    search_mentors,
    search_mentors_fuzzy,
    search_papers,
    search_papers_fuzzy,
)
from utils.utils_jwt import check_jwt_token
from utils.utils_require import CheckRequire, MAX_CHAR_LENGTH, require
from utils.utils_request import BAD_METHOD, request_success


def health(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    return request_success({
        "module": "search",
        "status": "ready",
    })


def _get_keyword(req: HttpRequest) -> str:
    keyword = require(
        req.GET,
        "keyword",
        "string",
        err_msg="Missing or error type of [keyword]",
    ).strip()
    assert keyword != "", "Invalid parameters. [keyword] cannot be empty"
    assert len(keyword) <= MAX_CHAR_LENGTH, "Invalid parameters. [keyword] is too long"
    return keyword


def _get_search_mode(req: HttpRequest) -> str:
    search_mode = str(req.GET.get("search_mode", "exact")).strip().lower()
    assert search_mode in {"exact", "fuzzy"}, "Invalid parameters. [search_mode] must be exact or fuzzy"
    return search_mode


def _resolve_user(req: HttpRequest):
    auth_header = req.headers.get("Authorization", "").strip()
    if auth_header == "":
        return None

    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else auth_header
    if token == "":
        return None

    token_data = check_jwt_token(token)
    if token_data is None:
        return None

    username = str(token_data.get("username", "")).strip()
    if username == "":
        return None

    return User.objects.filter(username=username).first()


@CheckRequire
def mentors(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    keyword = _get_keyword(req)
    search_mode = _get_search_mode(req)
    user = _resolve_user(req)
    mentors = search_mentors_fuzzy(keyword, user=user) if search_mode == "fuzzy" else search_mentors(keyword, user=user)
    return request_success({
        "keyword": keyword,
        "search_mode": search_mode,
        "mentors": mentors,
    })


@CheckRequire
def papers(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    keyword = _get_keyword(req)
    search_mode = _get_search_mode(req)
    user = _resolve_user(req)
    papers = search_papers_fuzzy(keyword, user=user) if search_mode == "fuzzy" else search_papers(keyword, user=user)
    return request_success({
        "keyword": keyword,
        "search_mode": search_mode,
        "papers": papers,
    })
