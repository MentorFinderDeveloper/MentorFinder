#!/bin/bash
set -euo pipefail

mkdir -p /app/data /app/data/media

cd /app/backend
/app/.venv/bin/python -c "from utils.utils_jwt import validate_jwt_signing_key; validate_jwt_signing_key()"

# Align the historical fork only when a database has already applied later
# account migrations. A fresh database must run this migration normally.
account_migrations=$(/app/.venv/bin/python manage.py showmigrations account)
if printf '%s\n' "$account_migrations" | grep -q "\[ \] 0002_mentorfollow" \
    && printf '%s\n' "$account_migrations" | grep -Eq "\[X\] (0002_alter_user_managers|00(0[3-9]|1[0-9])_)"; then
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
backend_pid=$!

cd /app/frontend
HOSTNAME=127.0.0.1 PORT=3000 node server.js &
frontend_pid=$!

nginx -g "daemon off;" &
nginx_pid=$!

shutdown() {
    trap - TERM INT EXIT
    kill -TERM "$backend_pid" "$frontend_pid" "$nginx_pid" 2>/dev/null || true
    wait "$backend_pid" "$frontend_pid" "$nginx_pid" 2>/dev/null || true
}

trap shutdown TERM INT EXIT

set +e
wait -n "$backend_pid" "$frontend_pid" "$nginx_pid"
exit_status=$?
set -e

if ! kill -0 "$backend_pid" 2>/dev/null; then
    echo "Gunicorn exited; stopping container" >&2
elif ! kill -0 "$frontend_pid" 2>/dev/null; then
    echo "Next.js exited; stopping container" >&2
else
    echo "Nginx exited; stopping container" >&2
fi

shutdown
exit "$exit_status"
