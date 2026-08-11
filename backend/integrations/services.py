import secrets

from django.core import signing

from .providers.registry import get_provider


OAUTH_STATE_SALT = "zep-ex-integration-oauth"


class IntegrationService:

    @staticmethod
    def get_provider(integration):
        return get_provider(
            integration.provider,
            integration,
        )

    @staticmethod
    def create_oauth_state(integration):
        """
        Create a signed OAuth state containing the integration ID.
        """

        payload = {
            "integration_id": str(integration.id),
            "company_id": str(integration.company_id),
            "provider": integration.provider,
        }

        return signing.dumps(
            payload,
            salt=OAUTH_STATE_SALT,
        )

    @staticmethod
    def verify_oauth_state(state):
        """
        Verify and decode OAuth state.
        """

        if not state:
            raise ValueError(
                "OAuth state is missing."
            )

        try:
            return signing.loads(
                state,
                salt=OAUTH_STATE_SALT,
                max_age=600,
            )
        except signing.BadSignature:
            raise ValueError(
                "Invalid or expired OAuth state."
            )

    @staticmethod
    def get_authorization_url(
        integration,
        request,
    ):
        provider = IntegrationService.get_provider(
            integration
        )

        return provider.get_authorization_url(
            request,
        )

    @staticmethod
    def exchange_code_for_token(
        integration,
        code,
        request,
    ):
        provider = IntegrationService.get_provider(
            integration
        )

        return provider.exchange_code_for_token(
            code,
            request,
        )

    @staticmethod
    def refresh_access_token(
        integration,
    ):
        provider = IntegrationService.get_provider(
            integration
        )

        return provider.refresh_access_token()

    @staticmethod
    def test_connection(
        integration,
    ):
        provider = IntegrationService.get_provider(
            integration
        )

        return provider.test_connection()

    @staticmethod
    def sync(
        integration,
    ):
        provider = IntegrationService.get_provider(
            integration
        )

        return provider.sync()