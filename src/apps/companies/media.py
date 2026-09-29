# apps/companies/media.py
"""
Cloudinary upload/delete helpers for per-company media (logo, favicon).

Mirrors the pattern in apps/settings/views.py:

  - Upload to Cloudinary with a UNIQUE public_id per upload:
        companies/<company_id>/<field>_<timestamp>
  - Store the returned public_id in the model field (a plain string).
  - Delete the old asset when replaced or removed.

Why a unique public_id: Cloudinary's CDN caches by public_id. With a
fixed public_id + overwrite=True, replacing a file serves the OLD
cached version. A unique public_id makes every upload a new asset →
CDN never serves stale content.
"""

import time
import cloudinary
import cloudinary.uploader
from django.conf import settings as django_settings


def _cloudinary():
    cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )


def upload_company_media(file_obj, company_id, field_name, resource_type='image'):
    """
    Upload a company media file to Cloudinary.

    Returns the public_id Cloudinary used (e.g.
        'companies/42/favicon_1789754321').

    `field_name` should be 'logo' or 'favicon' (used only in the
    public_id so assets are grouped by purpose).
    """
    _cloudinary()
    public_id = f"companies/{company_id}/{field_name}_{int(time.time())}"

    result = cloudinary.uploader.upload(
        file_obj,
        public_id=public_id,
        overwrite=False,
        resource_type=resource_type,
    )
    return result.get('public_id') or public_id


def delete_company_media(public_id, resource_type='image'):
    """Delete a Cloudinary asset by its exact public_id. Silent on failure."""
    if not public_id:
        return
    try:
        _cloudinary()
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    except Exception:
        pass