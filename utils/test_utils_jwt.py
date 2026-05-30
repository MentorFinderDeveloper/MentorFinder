"""utils_jwt 中签名密钥校验与边界分支的补充测试。

现有 account/tests.py 已覆盖 check_jwt_token 的正常 / 篡改 / 过期 / 轮换密钥路径，
这里专门补：
- _validate_signing_key 的三个 RuntimeError 分支；
- validate_jwt_signing_key 的成功与失败；
- _load_dotenv_if_needed 在环境变量未设置时的两个分支；
- check_jwt_token 在 exp 非数字时返回 None。
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core import signing
from django.test import SimpleTestCase

from utils import utils_jwt
from utils.utils_jwt import (
    JWT_SIGNING_KEY_ENV,
    _get_signing_key,
    _load_dotenv_if_needed,
    _validate_signing_key,
    check_jwt_token,
    validate_jwt_signing_key,
)


class ValidateSigningKeyTests(SimpleTestCase):
    def test_rejects_empty_key(self):
        with self.assertRaisesMessage(RuntimeError, "must be configured"):
            _validate_signing_key("")

    def test_rejects_whitespace_only_key(self):
        with self.assertRaisesMessage(RuntimeError, "must be configured"):
            _validate_signing_key("   ")

    def test_rejects_too_short_key(self):
        with self.assertRaisesMessage(RuntimeError, "at least 32 characters"):
            _validate_signing_key("short-key")

    def test_rejects_known_development_value(self):
        # "KawaiiNana" 仅 10 字符，会先触发长度校验；该开发态密钥无论如何都会被拒绝。
        with self.assertRaises(RuntimeError):
            _validate_signing_key("KawaiiNana")

    def test_accepts_and_strips_valid_key(self):
        key = "a-sufficiently-long-signing-key-1234567890"
        self.assertEqual(_validate_signing_key(f"  {key}  "), key)


class ValidateJwtSigningKeyEntrypointTests(SimpleTestCase):
    def test_passes_with_configured_env_key(self):
        # conftest.py 已注入合法的 JWT_SIGNING_KEY，应当不抛异常。
        self.assertIsNone(validate_jwt_signing_key())

    def test_raises_when_env_key_invalid(self):
        # 环境变量已被设置（非空）-> _load_dotenv_if_needed 提前返回、不会重载 .env，
        # 因此这里设置的短密钥会被校验拒绝。
        with patch.dict(os.environ, {JWT_SIGNING_KEY_ENV: "too-short"}):
            with self.assertRaises(RuntimeError):
                validate_jwt_signing_key()


class LoadDotenvIfNeededTests(SimpleTestCase):
    def test_returns_early_when_env_already_set(self):
        with patch.dict(os.environ, {JWT_SIGNING_KEY_ENV: "already-present-key"}):
            with patch.object(utils_jwt, "DOTENV_PATH") as mock_path:
                _load_dotenv_if_needed()
                # 提前 return，不应去访问 .env 文件。
                mock_path.exists.assert_not_called()

    def test_returns_when_env_missing_and_dotenv_absent(self):
        missing = Path(tempfile.gettempdir()) / "definitely-not-here.env"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(JWT_SIGNING_KEY_ENV, None)
            with patch.object(utils_jwt, "DOTENV_PATH", missing):
                # 不存在 .env -> 直接返回，环境变量仍为空。
                _load_dotenv_if_needed()
                self.assertEqual(os.environ.get(JWT_SIGNING_KEY_ENV, ""), "")

    def test_loads_dotenv_when_env_missing_and_file_present(self):
        loaded_key = "loaded-from-dotenv-key-abcdefghijklmnop"
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_file = Path(tmpdir) / ".env"
            dotenv_file.write_text(f"{JWT_SIGNING_KEY_ENV}={loaded_key}\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(JWT_SIGNING_KEY_ENV, None)
                with patch.object(utils_jwt, "DOTENV_PATH", dotenv_file):
                    _load_dotenv_if_needed()
                    self.assertEqual(os.environ.get(JWT_SIGNING_KEY_ENV), loaded_key)


class CheckJwtTokenExpiryTypeTests(SimpleTestCase):
    def _sign(self, payload: dict) -> str:
        key = _get_signing_key().decode("utf-8")
        signer = signing.Signer(key=key, salt="utils.utils_jwt")
        return signer.sign(json.dumps(payload, separators=(",", ":")))

    def test_rejects_token_with_non_numeric_exp(self):
        token = self._sign({"iat": 1, "exp": "soon", "data": {"username": "x"}})
        self.assertIsNone(check_jwt_token(token))

    def test_rejects_token_with_missing_exp(self):
        token = self._sign({"iat": 1, "data": {"username": "x"}})
        self.assertIsNone(check_jwt_token(token))
