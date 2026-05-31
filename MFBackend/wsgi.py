"""WSGI 配置（中文注释）

本模块为 MFBackend 提供 WSGI 入口，适用于同步 WSGI 服务器（例如 Gunicorn）。
模块级变量 `application` 为 WSGI 可调用对象，供外部服务器导入并调用。

启动时同样会验证 JWT 签名密钥（`validate_jwt_signing_key()`），以便在部署阶段
尽早发现配置问题并避免运行时错误。

参考文档：https://docs.djangoproject.com/en/4.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
from utils.utils_jwt import validate_jwt_signing_key

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MFBackend.settings')
validate_jwt_signing_key()

application = get_wsgi_application()
