import json

from cryptography.fernet import (
    Fernet,
    InvalidToken,
)

from django.conf import settings


def _get_fernet():

    key = getattr(
        settings,
        "INTEGRATION_ENCRYPTION_KEY",
        None,
    )

    if not key:
        raise RuntimeError(
            "INTEGRATION_ENCRYPTION_KEY "
            "is not configured."
        )

    if isinstance(key, str):
        key = key.encode()

    return Fernet(key)


def encrypt_integration_config(config):

    if not config:
        return None

    raw = json.dumps(
        config
    ).encode("utf-8")

    encrypted = _get_fernet().encrypt(
        raw
    )

    return encrypted.decode(
        "utf-8"
    )


def decrypt_integration_config(
    encrypted_config,
):

    if not encrypted_config:
        return {}

    try:

        decrypted = _get_fernet().decrypt(
            encrypted_config.encode(
                "utf-8"
            )
        )

        return json.loads(
            decrypted.decode("utf-8")
        )

    except InvalidToken as exc:

        raise RuntimeError(
            "Integration credentials "
            "could not be decrypted."
        ) from exc