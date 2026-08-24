import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)


def _as_bytes(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.strip() or None
    text = str(value).strip()
    return text.encode("utf-8") if text else None


def valid_fernet_key(raw):
    key = _as_bytes(raw)
    if not key:
        return None
    try:
        Fernet(key)
    except (ValueError, TypeError):
        return None
    return key


def derive_fernet_key(setting_name, secret):
    material = f"{setting_name}:{secret or 'zepex-dev-secret'}".encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(material).digest())


def get_fernet(setting_name):
    configured = valid_fernet_key(getattr(settings, setting_name, None))
    if configured:
        return Fernet(configured)

    secret = getattr(settings, "SECRET_KEY", "") or ""
    logger.warning(
        "%s is missing or not a valid 32-byte url-safe base64 Fernet key. "
        "Using a key derived from DJANGO_SECRET_KEY. Generate one with: "
        'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"',
        setting_name,
    )
    return Fernet(derive_fernet_key(setting_name, secret))


def looks_like_fernet_token(value):
    return bool(value) and str(value).startswith("gAAAA")


def decrypt_fernet_text(setting_name, encrypted_value, *, invalid_message):
    if not encrypted_value:
        return None

    text = str(encrypted_value)
    try:
        return get_fernet(setting_name).decrypt(text.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        if looks_like_fernet_token(text):
            raise RuntimeError(invalid_message) from exc
        return text
