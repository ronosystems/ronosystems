import hashlib
import ipaddress
import logging
import os

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


# ============================================
# IP HELPERS
# ============================================

def get_client_ip(request):
    """
    Return the real client IP.
    Render.com puts the client IP first in X-Forwarded-For:
        X-Forwarded-For: 197.232.x.x, 10.0.0.1, 10.0.0.2
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or None


def is_private_ip(ip):
    """True for 127.0.0.1, 10.x, 192.168.x, ::1, etc."""
    if not ip:
        return True
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return True


def maybe_hash_ip(ip):
    """Return sha256(ip + SALT) if VISIT_TRACKING_HASH_IP is on."""
    if not ip:
        return None
    if not getattr(settings, 'VISIT_TRACKING_HASH_IP', False):
        return ip
    salt = getattr(settings, 'VISIT_TRACKING_IP_SALT', '')
    return hashlib.sha256(f'{salt}{ip}'.encode()).hexdigest()


# ============================================
# USER AGENT PARSING
# ============================================

def parse_user_agent(ua_string):
    """
    Return (device, device_type, browser, browser_version, os).

    device is a smart, brand-aware label:
      - 'Lenovo ThinkCentre', 'HP PC', 'Dell PC', 'Acer PC', 'MacBook'
      - 'iPhone', 'iPad'
      - 'Android Samsung', 'Android Tecno', 'Android Xiaomi', ...
    """
    if not ua_string:
        return ('', '', '', '', '')

    try:
        from user_agents import parse as ua_parse
    except ImportError:
        logger.warning('user-agents package not installed')
        return ('', '', '', '', '')

    try:
        ua = ua_parse(ua_string)
        ua_lower = ua_string.lower()

        # ── Base device_type from user-agents ──
        if ua.is_bot:
            device_type = 'bot'
        elif ua.is_mobile:
            device_type = 'mobile'
        elif ua.is_tablet:
            device_type = 'tablet'
        elif ua.is_pc:
            device_type = 'desktop'
        else:
            device_type = 'other'

        browser         = ua.browser.family or ''
        browser_version = ua.browser.version_string or ''
        os_family       = ua.os.family or ''

        # ── Brand-aware device label ──
        device = _smart_device_label(ua_string, ua_lower, ua, device_type)

        return (device, device_type, browser, browser_version, os_family)

    except Exception:
        return ('', '', '', '', '')


# Desktop / laptop brand tokens (order matters — more specific first)
_DESKTOP_BRANDS = (
    ('thinkcentre', 'Lenovo ThinkCentre'),
    ('thinkpad',    'Lenovo ThinkPad'),
    ('ideapad',     'Lenovo IdeaPad'),
    ('legion',      'Lenovo Legion'),
    ('lenovo',      'Lenovo PC'),
    ('macbook',     'MacBook'),
    ('imac',        'iMac'),
    ('macintosh',   'Mac'),
    ('surface',     'Microsoft Surface'),
    ('pavilion',    'HP Pavilion'),
    ('probook',     'HP ProBook'),
    ('elitebook',   'HP EliteBook'),
    ('hp ',         'HP PC'),
    ('hewlett',     'HP PC'),
    ('optiplex',    'Dell OptiPlex'),
    ('latitude',    'Dell Latitude'),
    ('precision',   'Dell Precision'),
    ('inspiron',    'Dell Inspiron'),
    ('xps',         'Dell XPS'),
    ('dell',        'Dell PC'),
    ('aspire',      'Acer Aspire'),
    ('predator',    'Acer Predator'),
    ('nitro',       'Acer Nitro'),
    ('acer',        'Acer PC'),
    ('asus',        'Asus PC'),
    ('toshiba',     'Toshiba PC'),
    ('msi',         'MSI PC'),
)

# Android phone manufacturers
_ANDROID_BRANDS = (
    ('samsung',   'Android Samsung'),
    ('tecno',     'Android Tecno'),
    ('infinix',   'Android Infinix'),
    ('itel',      'Android iTel'),
    ('xiaomi',    'Android Xiaomi'),
    ('redmi',     'Android Redmi'),
    ('poco',      'Android POCO'),
    ('huawei',    'Android Huawei'),
    ('honor',     'Android Honor'),
    ('oppo',      'Android Oppo'),
    ('vivo',      'Android Vivo'),
    ('oneplus',   'Android OnePlus'),
    ('realme',    'Android Realme'),
    ('nokia',     'Android Nokia'),
    ('pixel',     'Android Pixel'),
    ('motorola',  'Android Motorola'),
    ('moto ',     'Android Motorola'),
    ('sony',      'Android Sony'),
    ('htc',       'Android HTC'),
    ('lava',      'Android Lava'),
    ('micromax',  'Android Micromax'),
    ('walton',    'Android Walton'),
    ('blackview', 'Android Blackview'),
)


def _smart_device_label(ua_string, ua_lower, ua, device_type):
    """Return a brand-aware, human-friendly device label."""

    # ── iOS ──
    if 'iphone' in ua_lower:
        return 'iPhone'
    if 'ipad' in ua_lower:
        return 'iPad'
    if 'ipod' in ua_lower:
        return 'iPod'

    # ── Desktop / laptop ──
    if device_type == 'desktop':
        for token, label in _DESKTOP_BRANDS:
            if token in ua_lower:
                return label
        family = ua.device.family or ''
        if family and family.lower() not in ('other', 'pc', 'desktop', 'unknown'):
            return family
        if ua.os.family == 'Windows':
            return 'Windows PC'
        if ua.os.family == 'Mac OS X':
            return 'Mac'
        if ua.os.family == 'Linux':
            return 'Linux PC'
        return 'Desktop'

    # ── Android mobile / tablet ──
    if device_type in ('mobile', 'tablet'):
        if 'android' in ua_lower:
            for token, label in _ANDROID_BRANDS:
                if token in ua_lower:
                    return label
            return 'Android ' + ('Tablet' if device_type == 'tablet' else 'Phone')
        family = ua.device.family or ''
        if family and family.lower() not in ('other', 'generic smartphone', 'unknown'):
            return family
        return 'Mobile'

    # ── Bots ──
    if device_type == 'bot':
        return ua.device.family or 'Bot'

    # ── Other ──
    return ua.device.family or 'Unknown'


# ============================================
# GEOIP LOOKUP (with DB + memory cache)
# ============================================


def lookup_geo(ip):
    """
    Return (country, country_code, city) for an IP.
    Returns ('', '', '') on any failure.

    Caches successful results only — never caches blanks, so a temporarily
    missing or unreadable GeoLite2 DB cannot poison the cache.
    """
    if not ip or is_private_ip(ip):
        return ('', '', '')

    cache_key = f'geoip:{ip}'

    # ── 1. Memory cache (only trust non-empty results) ──
    cached = cache.get(cache_key)
    if cached and cached[0]:
        return cached

    # ── 2. DB cache (only trust non-empty rows) ──
    try:
        from .models import IPGeoCache
        row = IPGeoCache.objects.filter(ip_address=ip).first()
        if row and row.country:
            result = (row.country, row.country_code, row.city)
            cache.set(cache_key, result, 60 * 60 * 24 * 30)
            return result
    except Exception:
        pass

    # ── 3. Actual MaxMind lookup ──
    country = country_code = city = ''
    try:
        import geoip2.database
        geoip_path = getattr(settings, 'GEOIP_PATH', None)
        if geoip_path:
            db_file = os.path.join(str(geoip_path), 'GeoLite2-City.mmdb')
            if os.path.exists(db_file):
                with geoip2.database.Reader(db_file) as reader:
                    resp = reader.city(ip)
                    country      = resp.country.name or ''
                    country_code = resp.country.iso_code or ''
                    city         = resp.city.name or ''
            else:
                logger.warning('GeoLite2-City.mmdb not found at %s', db_file)
    except Exception as e:
        logger.warning('GeoIP lookup failed for %s: %s', ip, e)

    result = (country, country_code, city)

    # ── 4. Cache ONLY if we actually resolved something ──
    if country:
        try:
            from .models import IPGeoCache
            IPGeoCache.objects.update_or_create(
                ip_address=ip,
                defaults={
                    'country': country,
                    'country_code': country_code,
                    'city': city,
                },
            )
        except Exception:
            pass
        cache.set(cache_key, result, 60 * 60 * 24 * 30)
    else:
        logger.info('No geo data resolved for %s — not caching', ip)

    return result