import time
import cloudinary
import cloudinary.uploader
from django.conf import settings

def _cloudinary_configure():
    """Configure Cloudinary using Django settings."""
    cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )

def _upload_product_image_to_cloudinary(uploaded_file, folder='epa_shop/products'):
    """
    Upload to Cloudinary and return the public_id, mirroring the
    accounts.profile_picture_upload pattern. Returns None on failure.
    """
    if not uploaded_file:
        return None

    try:
        _cloudinary_configure()

        # Unique public_id per upload, same idea as profiles
        base = f"{folder}/p_{int(time.time() * 1000)}"

        result = cloudinary.uploader.upload(
            uploaded_file,
            public_id=base,
            overwrite=False,
            resource_type='image',
        )
        public_id = result.get('public_id') or base
        print(f"✅ Cloudinary upload OK: {public_id}")
        return public_id
    except Exception as e:
        import traceback
        print(f"❌ Cloudinary upload FAILED: {e}")
        traceback.print_exc()
        return None