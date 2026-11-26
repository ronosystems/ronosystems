# apps/company/cloudinary_utils.py
"""
Cloudinary helpers for the expenses module.

Mirrors the pattern in apps/accounts/views.py (which works):
    - Call cloudinary.config() from settings each time
    - Explicit resource_type='image' (never 'auto')
    - Store public_id in the model field
    - Build the delivery URL from the public_id via _build_cloudinary_url()
"""
import logging
import time
import cloudinary
import cloudinary.uploader
from django.conf import settings

logger = logging.getLogger(__name__)


def _configure():
    """Same as _cloudinary_configure() in accounts/views.py — call before every SDK op."""
    cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )


def upload_attachment(file_obj, folder='expenses', tags=None):
    """
    Upload an attachment (image or PDF) to Cloudinary.

    Returns dict {public_id, secure_url, format, bytes} or None on failure.
    """
    if not file_obj:
        return None

    _configure()

    # Unique public_id per upload — same pattern as profiles/user_<id>_<ts>
    ts = int(time.time())
    base_name = getattr(file_obj, 'name', 'file')
    # Strip extension (Cloudinary adds it back based on the file)
    if '.' in base_name:
        base_name = base_name.rsplit('.', 1)[0]
    # Sanitize — Cloudinary dislikes spaces and some punctuation in public_ids
    safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in base_name)[:60] or 'file'

    public_id = f"{folder}/{safe_name}_{ts}"

    try:
        result = cloudinary.uploader.upload(
            file_obj,
            public_id=public_id,
            overwrite=False,
            resource_type='image',      # ← explicitly 'image', same as accounts/views.py
            tags=tags or [],
        )
        logger.info("Cloudinary attachment upload OK: %s", result.get('public_id'))
        return {
            'public_id': result.get('public_id') or public_id,
            'secure_url': result.get('secure_url'),
            'format': result.get('format'),
            'bytes': result.get('bytes'),
        }
    except Exception as exc:
        logger.exception("Cloudinary attachment upload failed: %s", exc)
        return None


def delete_attachment(public_id):
    """Best-effort delete. Never raises."""
    if not public_id:
        return False
    pid = str(public_id).strip().lstrip('/')
    if pid.startswith('http://') or pid.startswith('https://'):
        logger.warning("Refusing to delete non-public_id value: %s", pid)
        return False
    _configure()
    try:
        result = cloudinary.uploader.destroy(pid, resource_type='image', invalidate=True)
        logger.info("Cloudinary delete %s -> %s", pid, result.get('result'))
        return result.get('result') in ('ok', 'not found')
    except Exception as exc:
        logger.exception("Cloudinary delete failed for %s: %s", pid, exc)
        return False