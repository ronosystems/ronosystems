#!/usr/bin/env bash
set -o errexit

echo "=== Building RonoSystems for Render ==="

# Install system dependencies
apt-get update -y
apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    libffi-dev

# Navigate to src
cd src

# Upgrade pip and install with pre-built wheels
pip install --upgrade pip
pip install --only-binary :all: -r ../requirements.txt

# Run migrations
python manage.py makemigrations --noinput
python manage.py migrate --noinput

# Collect static files
python manage.py collectstatic --noinput

echo "=== Build complete! ==="
