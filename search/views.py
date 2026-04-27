from django.http import HttpRequest

from account.models import User
from search.services.engine import (
    search_mentors_page,
    search_papers_page,
)
from utils.utils_jwt import check_jwt_token
from utils.utils_require import CheckRequire, MAX_CHAR_LENGTH, require
from utils.utils_request import BAD_METHOD, request_success


DEFAULT_SEARCH_PAGE = 1
DEFAULT_SEARCH_PAGE_SIZE = 10
MAX_SEARCH_PAGE_SIZE = 100


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


def _get_sort_mode(req: HttpRequest) -> str:
    sort_mode = str(req.GET.get("sort_mode", "default")).strip().lower()
    assert sort_mode in {"default", "early", "late"}, "Invalid parameters. [sort_mode] must be default, early or late"
    return sort_mode


def _parse_positive_int(raw_value, default_value: int, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return default_value

    if parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _get_pagination(req: HttpRequest) -> tuple[int, int]:
    page = _parse_positive_int(req.GET.get("page"), DEFAULT_SEARCH_PAGE)
    page_size = _parse_positive_int(
        req.GET.get("page_size"),
        DEFAULT_SEARCH_PAGE_SIZE,
        maximum=MAX_SEARCH_PAGE_SIZE,
    )
    return page, page_size


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
    page, page_size = _get_pagination(req)
    user = _resolve_user(req)
    mentors, pagination = search_mentors_page(
        keyword,
        user=user,
        fuzzy=(search_mode == "fuzzy"),
        page=page,
        page_size=page_size,
    )
    return request_success({
        "keyword": keyword,
        "search_mode": search_mode,
        **pagination,
        "mentors": mentors,
    })


@CheckRequire
def papers(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    keyword = _get_keyword(req)
    search_mode = _get_search_mode(req)
    sort_mode = _get_sort_mode(req)
    page, page_size = _get_pagination(req)
    user = _resolve_user(req)
    papers, pagination = search_papers_page(
        keyword,
        user=user,
        search_mode=search_mode,
        sort_mode=sort_mode,
        page=page,
        page_size=page_size,
    )
    return request_success({
        "keyword": keyword,
        "search_mode": search_mode,
        "sort_mode": sort_mode,
        **pagination,
        "papers": papers,
    })
