from backend.fernet_utils import decrypt_fernet_text, get_fernet


def encrypt_imap_password(password):
    if not password:
        return None
    return (
        get_fernet("IMAP_ENCRYPTION_KEY")
        .encrypt(password.encode("utf-8"))
        .decode("utf-8")
    )


def decrypt_imap_password(encrypted_password):
    return decrypt_fernet_text(
        "IMAP_ENCRYPTION_KEY",
        encrypted_password,
        invalid_message=(
            "Stored IMAP password could not be decrypted. "
            "Set IMAP_ENCRYPTION_KEY to a valid Fernet key."
        ),
    )
