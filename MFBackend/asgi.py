"""ASGI 配置（中文注释）

本模块为 MFBackend 提供 ASGI 入口，用于异步服务器（例如 Uvicorn/Daphne）
对 Django 应用的调用。模块级变量 `application` 暴露了 ASGI 可调用对象。

在此模块中会在应用启动阶段验证 JWT 签名密钥（`validate_jwt_signing_key()`），
以便尽早检测密钥配置问题并降低运行时错误风险。

参考文档：https://docs.djangoproject.com/en/4.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from utils.utils_jwt import validate_jwt_signing_key

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MFBackend.settings')
validate_jwt_signing_key()

application = get_asgi_application()
