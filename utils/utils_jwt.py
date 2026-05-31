import base64
import json
import os
import time
from pathlib import Path
from typing import Optional

from django.core import signing


EXPIRE_IN_SECONDS = int(os.environ.get("JWT_EXPIRE_SECONDS", str(60 * 60 * 2)))
ALT_CHARS = "-_".encode("utf-8")
JWT_SIGNING_KEY_ENV = "JWT_SIGNING_KEY"
JWT_SIGNING_KEY_MIN_LENGTH = 32
DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"


# 校验 JWT 签名密钥是否满足安全要求。
def _validate_signing_key(signing_key: str) -> str:
    signing_key = signing_key.strip()
    if not signing_key:
        raise RuntimeError("JWT_SIGNING_KEY must be configured")
    if len(signing_key) < JWT_SIGNING_KEY_MIN_LENGTH:
        raise RuntimeError("JWT_SIGNING_KEY must be at least 32 characters long")
    if signing_key == "KawaiiNana":
        raise RuntimeError("JWT_SIGNING_KEY must not use a known development value")
    return signing_key


# 在环境变量缺失时尝试从 .env 文件加载 JWT 签名密钥。
def _load_dotenv_if_needed() -> None:
    if os.environ.get(JWT_SIGNING_KEY_ENV, "").strip():
        return
    if not DOTENV_PATH.exists():
        return
    try:
        from dotenv import load_dotenv as _load_dotenv

        _load_dotenv(DOTENV_PATH)
    except ModuleNotFoundError:
        pass


# 读取并返回经过校验的 JWT 签名密钥字节串。
def _get_signing_key() -> bytes:
    _load_dotenv_if_needed()
    signing_key = os.environ.get(JWT_SIGNING_KEY_ENV, "").strip()
    signing_key = _validate_signing_key(signing_key)
    return signing_key.encode("utf-8")


# 对外校验当前环境中的 JWT 签名密钥配置。
def validate_jwt_signing_key() -> None:
    _load_dotenv_if_needed()
    signing_key = os.environ.get(JWT_SIGNING_KEY_ENV, "").strip()
    _validate_signing_key(signing_key)


# 将字符串或字节内容编码为 URL 安全的 Base64 字符串。
def b64url_encode(s):
    if isinstance(s, str):
        return base64.b64encode(s.encode("utf-8"), altchars=ALT_CHARS).decode("utf-8")
    return base64.b64encode(s, altchars=ALT_CHARS).decode("utf-8")


# 将 URL 安全的 Base64 字符串解码为文本或字节内容。
def b64url_decode(s: str, decode_to_str=True):
    if decode_to_str:
        return base64.b64decode(s, altchars=ALT_CHARS).decode("utf-8")
    return base64.b64decode(s, altchars=ALT_CHARS)


def _token_version_for_username(username: str) -> int:
    from account.models import User

    user = User.objects.filter(username=username).only("jwt_token_version").first()
    if user is None:
        return 0
    return user.jwt_token_version


# 为指定用户名生成带过期时间和吊销版本的签名 JWT 令牌。
def generate_jwt_token(username: str):
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + EXPIRE_IN_SECONDS,
        "tokenVersion": _token_version_for_username(username),
        "data": {
            "username": username,
        },
    }
    payload_str = json.dumps(payload, separators=(",", ":"))
    signer = signing.Signer(key=_get_signing_key().decode("utf-8"), salt="utils.utils_jwt")
    return signer.sign(payload_str)


# 校验 JWT 令牌并在有效时返回其中的业务数据。
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

    token_version = payload.get("tokenVersion", -1)
    token_data = payload.get("data", {})
    username = str(token_data.get("username", "") if isinstance(token_data, dict) else "").strip()
    if username != "":
        from account.models import User

        user = User.objects.filter(username=username).only("jwt_token_version").first()
        if user is not None and token_version != user.jwt_token_version:
            return None

    return payload["data"]


# 根据令牌解析用户对象，并按需过滤被封禁用户。
def resolve_user_from_token(token: str, reject_banned: bool = True):
    token_data = check_jwt_token(token)
    if token_data is None:
        return None

    username = str(token_data.get("username", "")).strip()
    if username == "":
        return None

    from account.models import User

    user = User.objects.filter(username=username).first()
    if user is None:
        return None
    if reject_banned and user.role == User.ROLE_BANNED:
        return None
    return user
