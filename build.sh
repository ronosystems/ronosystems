#!/usr/bin/env bash
set -o errexit

echo "=== Building RonoSystems for Render ==="

# Install system dependencies for Pillow
apt-get update -y
apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    libtiff-dev \
    libwebp-dev \
    zlib1g-dev \
    libffi-dev \
    libssl-dev

# Navigate to src directory
cd src

# Install dependencies
pip install --upgrade pip
pip install -r ../requirements.txt

# Run migrations
python manage.py makemigrations --noinput
python manage.py migrate --noinput

# Collect static files
python manage.py collectstatic --noinput

echo "=== Build complete! ==="
