#!/usr/bin/env bash
set -o errexit

echo "=== Building RonoSystems for Render ==="

# Install system dependencies for Pillow
apt-get update -y
apt-get install -y --no-install-recommends \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    zlib1g-dev

# Install Python packages
pip install --upgrade pip
pip install setuptools wheel
pip install -r requirements.txt

# Navigate to src
cd src

# Run migrations
python manage.py makemigrations --noinput || true
python manage.py migrate --noinput

# Collect static files
python manage.py collectstatic --noinput

echo "=== Build complete! ==="
