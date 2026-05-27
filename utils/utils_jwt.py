import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

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
    # * header
    header = {
        "alg": "HS256",
        "typ": "JWT"
    }
    # dump to str. remove `\n` and space after `:`
    header_str = json.dumps(header, separators=(",", ":"))
    # use base64url to encode, instead of base64
    header_b64 = b64url_encode(header_str)
    
    # * payload
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + EXPIRE_IN_SECONDS,
        "data": {
            "username": username
            # And more data for your own usage
        }
    }
    payload_str = json.dumps(payload, separators=(",", ":"))
    payload_b64 = b64url_encode(payload_str)
    
    # * signature
    signature_raw = header_b64 + "." + payload_b64
    signature = hmac.new(_get_signing_key(), signature_raw.encode("utf-8"), digestmod=hashlib.sha256).digest()
    signature_b64 = b64url_encode(signature)
    
    return header_b64 + "." + payload_b64 + "." + signature_b64


def check_jwt_token(token: str) -> Optional[dict]:
    # * Split token
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except:
        return None

    try:
        header = json.loads(b64url_decode(header_b64))
        payload_str = b64url_decode(payload_b64)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None

    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        return None
    
    # * Check signature
    signature_str_check = header_b64 + "." + payload_b64
    signature_check = hmac.new(_get_signing_key(), signature_str_check.encode("utf-8"), digestmod=hashlib.sha256).digest()
    signature_b64_check = b64url_encode(signature_check)
    
    if not hmac.compare_digest(signature_b64_check, signature_b64):
        return None
    
    # Check expire
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        return None
    if payload["exp"] < time.time():
        return None
    
    return payload["data"]
