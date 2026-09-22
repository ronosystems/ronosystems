# apps/company/cloudinary_utils.py
"""
Cloudinary helpers for the expenses module.

RULE (matches apps/epa_shop/models.py):
    - Upload manually via cloudinary.uploader.upload()
    - Store the returned public_id in the model field (NOT a URL)
    - Templates use the model's `attachment_url` property to build the URL
"""
import logging
import cloudinary
import cloudinary.uploader
from django.conf import settings

logger = logging.getLogger(__name__)


def _ensure_configured():
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
    _ensure_configured()
    try:
        result = cloudinary.uploader.upload(
            file_obj,
            folder=folder,
            resource_type='auto',   # images → image, PDFs → image (Cloudinary converts)
            tags=tags or [],
            overwrite=False,
            unique_filename=True,
            use_filename=False,
        )
        logger.info("Cloudinary attachment upload OK: %s", result.get('public_id'))
        return {
            'public_id': result.get('public_id'),
            'secure_url': result.get('secure_url'),
            'format': result.get('format'),
            'bytes': result.get('bytes'),
        }
    except Exception as exc:
        logger.exception("Cloudinary attachment upload failed: %s", exc)
        return None


def delete_attachment(public_id):
    """Delete an asset from Cloudinary by public_id. Safe with None/empty."""
    if not public_id:
        return False
    pid = str(public_id).strip()
    if pid.startswith('http://') or pid.startswith('https://'):
        logger.warning("Refusing to delete non-public_id value: %s", pid)
        return False
    _ensure_configured()
    try:
        result = cloudinary.uploader.destroy(pid, resource_type='image', invalidate=True)
        logger.info("Cloudinary delete %s -> %s", pid, result.get('result'))
        return result.get('result') in ('ok', 'not found')
    except Exception as exc:
        logger.exception("Cloudinary delete failed for %s: %s", pid, exc)
        return False