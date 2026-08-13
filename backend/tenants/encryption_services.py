from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _get_fernet():

    key = getattr(
        settings,
        "IMAP_ENCRYPTION_KEY",
        None,
    )

    if not key:
        raise RuntimeError(
            "IMAP_ENCRYPTION_KEY is not configured."
        )

    if isinstance(key, str):
        key = key.encode()

    return Fernet(key)


def encrypt_imap_password(password):

    if not password:
        return None

    fernet = _get_fernet()

    return fernet.encrypt(
        password.encode("utf-8")
    ).decode("utf-8")


def decrypt_imap_password(encrypted_password):

    if not encrypted_password:
        return None

    fernet = _get_fernet()

    try:

        return fernet.decrypt(
            encrypted_password.encode("utf-8")
        ).decode("utf-8")

    except InvalidToken as exc:

        raise RuntimeError(
            "Stored IMAP password could not be decrypted."
        ) from exc