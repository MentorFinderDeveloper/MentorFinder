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
python3 manage.py sync_dataset || true
python3 manage.py run_daily_sync &

uwsgi --module=MFBackend.wsgi:application \
    --env DJANGO_SETTINGS_MODULE=MFBackend.settings \
    --master \
    --http=0.0.0.0:80 \
    --processes=5 \
    --harakiri=20 \
    --max-requests=5000 \
    --vacuum
