#!/bin/sh

echo "Migrations..."
python manage.py migrate --noinput

echo "Collect static..."
python manage.py collectstatic --no-input

echo "Loading data..."
python manage.py loaddata auth
python manage.py loaddata groups

exec "$@"