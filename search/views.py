from django.http import HttpRequest

from utils.utils_request import BAD_METHOD, request_success


def health(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    return request_success({
        "module": "search",
        "status": "ready",
    })

