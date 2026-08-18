from datetime import datetime, timezone as dt_timezone

from django.utils import timezone

from integrations.encryption_services import (
    decrypt_integration_config,
    encrypt_integration_config,
)

from integrations.models import (
    IntegrationCredential,
)

from integrations.services.quickbooks import (
    QuickBooksClient,
    QuickBooksAuthenticationError,
)


def _parse_iso_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except Exception:
        return None


def get_valid_quickbooks_access_token(
    *,
    integration,
):
    """
    Return a valid QuickBooks access token.

    If the current token is near expiry,
    automatically refresh it and persist
    the newest access/refresh token pair.
    """

    try:
        credential = integration.credential

    except Exception as exc:
        raise QuickBooksAuthenticationError(
            "QuickBooks credentials are not configured."
        ) from exc

    config = decrypt_integration_config(
        credential.encrypted_config
    )

    access_token = config.get(
        "access_token"
    )

    refresh_token = config.get(
        "refresh_token"
    )

    expires_at = _parse_iso_datetime(
        config.get(
            "access_token_expires_at"
        )
    )

    if not access_token:
        raise QuickBooksAuthenticationError(
            "QuickBooks access token is missing."
        )

    if not refresh_token:
        raise QuickBooksAuthenticationError(
            "QuickBooks refresh token is missing."
        )

    # Refresh if expiry is missing or token expires
    # within the next 5 minutes.
    should_refresh = True

    if expires_at:
        remaining_seconds = (
            expires_at
            - timezone.now()
        ).total_seconds()

        should_refresh = (
            remaining_seconds <= 300
        )

    if not should_refresh:
        return {
            "access_token": access_token,
            "config": config,
        }

    client = QuickBooksClient()

    token_data = (
        client.refresh_access_token(
            refresh_token=refresh_token,
        )
    )

    new_access_token = token_data.get(
        "access_token"
    )

    new_refresh_token = (
        token_data.get(
            "refresh_token"
        )
        or refresh_token
    )

    expires_in = token_data.get(
        "expires_in"
    )

    refresh_expires_in = (
        token_data.get(
            "x_refresh_token_expires_in"
        )
    )

    if not new_access_token:
        raise QuickBooksAuthenticationError(
            "QuickBooks did not return a new access token."
        )

    now = timezone.now()

    config["access_token"] = (
        new_access_token
    )

    config["refresh_token"] = (
        new_refresh_token
    )

    if expires_in:
        config[
            "access_token_expires_at"
        ] = (
            now
            + timezone.timedelta(
                seconds=int(
                    expires_in
                )
            )
        ).isoformat()

    if refresh_expires_in:
        config[
            "refresh_token_expires_at"
        ] = (
            now
            + timezone.timedelta(
                seconds=int(
                    refresh_expires_in
                )
            )
        ).isoformat()

    encrypted_config = (
        encrypt_integration_config(
            config
        )
    )

    credential.encrypted_config = (
        encrypted_config
    )

    credential.save(
        update_fields=[
            "encrypted_config",
            "updated_at",
        ]
    )

    return {
        "access_token": (
            new_access_token
        ),
        "config": config,
    }