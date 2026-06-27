#!/bin/sh
set -e

python manage.py migrate --noinput

exec gunicorn auto_sell.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 60
