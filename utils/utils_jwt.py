import base64
import json
import os
import time
from typing import Optional

from django.core import signing

EXPIRE_IN_SECONDS = 60 * 60 * 24 * 1  # 1 day
ALT_CHARS = "-_".encode("utf-8")
JWT_SIGNING_KEY_ENV = "JWT_SIGNING_KEY"
JWT_SIGNING_KEY_MIN_LENGTH = 32


def _validate_signing_key(signing_key: str) -> str:
    signing_key = signing_key.strip()
    if not signing_key:
        raise RuntimeError("JWT_SIGNING_KEY must be configured")
    if len(signing_key) < JWT_SIGNING_KEY_MIN_LENGTH:
        raise RuntimeError("JWT_SIGNING_KEY must be at least 32 characters long")
    if signing_key == "KawaiiNana":
        raise RuntimeError("JWT_SIGNING_KEY must not use a known development value")
    return signing_key


def _get_signing_key() -> bytes:
    signing_key = os.environ.get(JWT_SIGNING_KEY_ENV, "").strip()
    signing_key = _validate_signing_key(signing_key)
    return signing_key.encode("utf-8")


def validate_jwt_signing_key() -> None:
    signing_key = os.environ.get(JWT_SIGNING_KEY_ENV, "").strip()
    _validate_signing_key(signing_key)


def b64url_encode(s):
    if isinstance(s, str):
        return base64.b64encode(s.encode("utf-8"), altchars=ALT_CHARS).decode("utf-8")
    else:
        return base64.b64encode(s, altchars=ALT_CHARS).decode("utf-8")

def b64url_decode(s: str, decode_to_str=True):
    if decode_to_str:
        return base64.b64decode(s, altchars=ALT_CHARS).decode("utf-8")
    else:
        return base64.b64decode(s, altchars=ALT_CHARS)


def generate_jwt_token(username: str):
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + EXPIRE_IN_SECONDS,
        "data": {
            "username": username
        }
    }
    payload_str = json.dumps(payload, separators=(",", ":"))
    signer = signing.Signer(key=_get_signing_key().decode("utf-8"), salt="utils.utils_jwt")
    return signer.sign(payload_str)


def check_jwt_token(token: str) -> Optional[dict]:
    try:
        signer = signing.Signer(key=_get_signing_key().decode("utf-8"), salt="utils.utils_jwt")
        payload_str = signer.unsign(token)
        payload = json.loads(payload_str)
    except (signing.BadSignature, TypeError, ValueError, json.JSONDecodeError):
        return None

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    if exp < time.time():
        return None
    
    return payload["data"]
