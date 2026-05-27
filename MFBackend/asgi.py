"""
ASGI config for MFBackend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from utils.utils_jwt import validate_jwt_signing_key

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MFBackend.settings')
validate_jwt_signing_key()

application = get_asgi_application()
