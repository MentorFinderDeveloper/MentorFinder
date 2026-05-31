#!/bin/sh
set -e

mkdir -p data

python3 -c "from utils.utils_jwt import validate_jwt_signing_key; validate_jwt_signing_key()"

# 生产环境不在启动时生成迁移文件，只应用仓库中已提交的迁移。
# 历史分叉修复：若 account.0002_mentorfollow 未应用但后续已应用，启动时自动 fake 对齐。
if python3 manage.py showmigrations account | grep -q "\[ \] 0002_mentorfollow"; then
    python3 manage.py migrate account 0002_mentorfollow --fake --noinput
fi

python3 manage.py migrate --noinput
python3 manage.py createsuperuser --noinput || true

# 部署/启动时一律不抓取数据，只由进程内调度器在每天 18:00 (Asia/Shanghai) 触发。
# 历史上的两条“启动即爬”路径（config 的 run_initial_sync、环境变量 SYNC_DATA_ON_STARTUP）
# 已移除，避免每次重新部署都重新全量爬一遍、并与定时任务重复。
# 如需手动补一次同步，进容器执行： python3 manage.py sync_dataset

exec uwsgi --module=MFBackend.wsgi:application \
    --env DJANGO_SETTINGS_MODULE=MFBackend.settings \
    --master \
    --http=0.0.0.0:80 \
    --processes=1 \
    --enable-threads \
    --harakiri=20 \
    --max-requests=5000 \
    --vacuum
