import json

from backend.fernet_utils import decrypt_fernet_text, get_fernet


def encrypt_integration_config(config):
    if not config:
        return None
    raw = json.dumps(config).encode("utf-8")
    return get_fernet("INTEGRATION_ENCRYPTION_KEY").encrypt(raw).decode("utf-8")


def decrypt_integration_config(encrypted_config):
    if not encrypted_config:
        return {}
    decrypted = decrypt_fernet_text(
        "INTEGRATION_ENCRYPTION_KEY",
        encrypted_config,
        invalid_message=(
            "Integration credentials could not be decrypted. "
            "Set INTEGRATION_ENCRYPTION_KEY to a valid Fernet key."
        ),
    )
    if not decrypted:
        return {}
    try:
        return json.loads(decrypted)
    except json.JSONDecodeError:
        return {}
