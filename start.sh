#!/bin/sh
set -e

mkdir -p data

# 生产环境不在启动时生成迁移文件，只应用仓库中已提交的迁移。
# 历史分叉修复：若 account.0002_mentorfollow 未应用但后续已应用，启动时自动 fake 对齐。
if python3 manage.py showmigrations account | grep -q "\[ \] 0002_mentorfollow"; then
    python3 manage.py migrate account 0002_mentorfollow --fake --noinput
fi

python3 manage.py migrate --noinput
python3 manage.py createsuperuser --noinput || true

# Avoid startup 502 caused by long-running crawler tasks blocking uwsgi boot.
# Set SYNC_DATA_ON_STARTUP=1 if you need a one-time sync after container starts.
if [ "${SYNC_DATA_ON_STARTUP:-0}" = "1" ]; then
    (python3 manage.py sync_dataset || true) &
fi

# Daily scheduler can be disabled by setting RUN_DAILY_SYNC_SCHEDULER=0.
if [ "${RUN_DAILY_SYNC_SCHEDULER:-1}" = "1" ]; then
    python3 manage.py run_daily_sync &
fi

exec uwsgi --module=MFBackend.wsgi:application \
    --env DJANGO_SETTINGS_MODULE=MFBackend.settings \
    --master \
    --http=0.0.0.0:80 \
    --processes=1 \
    --harakiri=20 \
    --max-requests=5000 \
    --vacuum
