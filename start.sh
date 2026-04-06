#!/bin/sh
python3 manage.py makemigrations account
python3 manage.py makemigrations dataset
python3 manage.py migrate
python3 manage.py createsuperuser --noinput || true
-master \
    --http=0.0.0.0:80 \
    --processes=5 \
    --harakiri=20 \
    --max-requests=5000 \
    --vacuum
