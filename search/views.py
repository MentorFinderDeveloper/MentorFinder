from django.http import HttpRequest

from search.services.engine import search_mentors, search_papers
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


@CheckRequire
def mentors(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    keyword = _get_keyword(req)
    return request_success({
        "keyword": keyword,
        "mentors": search_mentors(keyword),
    })


@CheckRequire
def papers(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    keyword = _get_keyword(req)
    return request_success({
        "keyword": keyword,
        "papers": search_papers(keyword),
    })
