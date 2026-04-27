#!/bin/sh
mkdir -p data
python3 manage.py makemigrations account
python3 manage.py makemigrations dataset
python3 manage.py migrate
python3 manage.py createsuperuser --noinput || true

RUN_INITIAL_SYNC=$(python3 -c "from utils.startup_config import load_startup_config; print('1' if load_startup_config()['startup']['run_initial_sync'] else '0')")
RUN_DAILY_SYNC_SCHEDULER=$(python3 -c "from utils.startup_config import load_startup_config; print('1' if load_startup_config()['startup']['run_daily_sync_scheduler'] else '0')")
RUN_WEEKLY_PUSH_SCHEDULER=$(python3 -c "from utils.startup_config import load_startup_config; print('1' if load_startup_config()['startup']['run_weekly_push_scheduler'] else '0')")

if [ "$RUN_INITIAL_SYNC" = "1" ]; then
    python3 manage.py sync_dataset || true
fi

if [ "$RUN_DAILY_SYNC_SCHEDULER" = "1" ]; then
    python3 manage.py run_daily_sync &
fi

if [ "$RUN_WEEKLY_PUSH_SCHEDULER" = "1" ]; then
    python3 manage.py run_weekly_push_scheduler &
fi

uwsgi --module=MFBackend.wsgi:application \
    --env DJANGO_SETTINGS_MODULE=MFBackend.settings \
    --master \
    --http=0.0.0.0:80 \
    --processes=5 \
    --harakiri=20 \
    --max-requests=5000 \
    --vacuum
