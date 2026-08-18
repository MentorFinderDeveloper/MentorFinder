#!/bin/sh
set -eu

mkdir -p /app/data /app/data/media

cd /app/backend
/app/.venv/bin/python -c "from utils.utils_jwt import validate_jwt_signing_key; validate_jwt_signing_key()"

# Align the historical forked migration before applying committed migrations.
if /app/.venv/bin/python manage.py showmigrations account | grep -q "\[ \] 0002_mentorfollow"; then
    /app/.venv/bin/python manage.py migrate account 0002_mentorfollow --fake --noinput
fi

/app/.venv/bin/python manage.py migrate --noinput
/app/.venv/bin/python manage.py collectstatic --noinput --clear

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] \
    && [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ] \
    && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    /app/.venv/bin/python manage.py createsuperuser --noinput || true
fi

/app/.venv/bin/gunicorn MFBackend.wsgi:application \
    --bind 127.0.0.1:8000 \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - &

cd /app/frontend
HOSTNAME=127.0.0.1 PORT=3000 node server.js &

exec nginx -g "daemon off;"
