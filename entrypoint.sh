#!/bin/bash

echo "Waiting for database to be ready..."
until python3 - <<'EOF'
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "horilla.settings")
import django
django.setup()
from django.db import connections
try:
    connections["default"].ensure_connection()
    sys.exit(0)
except Exception:
    sys.exit(1)
EOF
do
    echo "Database not ready, retrying in 2 seconds..."
    sleep 2
done

echo "Database is ready."
python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py collectstatic --noinput
python3 manage.py createhorillauser --first_name admin --last_name admin --username admin --password admin --email admin@example.com --phone 1234567890
gunicorn --bind 0.0.0.0:${DOCKER_PORT:-8000} --workers 4 --threads 2 --timeout 120 horilla.wsgi:application
