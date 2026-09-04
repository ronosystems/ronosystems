#!/usr/bin/env bash
set -o errexit

echo "=== Building RonoSystems for Render ==="

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Navigate to src directory
cd src

# Run migrations
python manage.py makemigrations --noinput || true
python manage.py migrate --noinput

# Collect static files
python manage.py collectstatic --noinput

echo "=== Build complete! ==="
