from django.utils import timezone

from .base import BaseIntegrationProvider
from .registry import register_provider


@register_provider("MOCK")
class MockProvider(BaseIntegrationProvider):

    def get_authorization_url(self, request):
        return (
            "http://127.0.0.1:8000/"
            "integrations/providers/MOCK/callback/"
            "?code=MOCK_AUTHORIZATION_CODE"
        )

    def exchange_code_for_token(self, code, request):

        if code != "MOCK_AUTHORIZATION_CODE":
            raise ValueError(
                "Invalid mock authorization code."
            )

        self.integration.access_token = (
            "mock_access_token"
        )

        self.integration.refresh_token = (
            "mock_refresh_token"
        )

        self.integration.scope = (
            "employees.read"
        )

        self.integration.external_account_id = (
            "MOCK_COMPANY_001"
        )

        self.integration.status = (
            self.integration.STATUS_CONNECTED
        )

        self.integration.connected_at = (
            timezone.now()
        )

        self.integration.last_error = None

        self.integration.save(
            update_fields=[
                "access_token",
                "refresh_token",
                "scope",
                "external_account_id",
                "status",
                "connected_at",
                "last_error",
                "updated_at",
            ]
        )

        return {
            "access_token": "mock_access_token",
            "refresh_token": "mock_refresh_token",
            "scope": "employees.read",
        }

    def refresh_access_token(self):

        self.integration.access_token = (
            "mock_refreshed_access_token"
        )

        self.integration.status = (
            self.integration.STATUS_CONNECTED
        )

        self.integration.last_error = None

        self.integration.save(
            update_fields=[
                "access_token",
                "status",
                "last_error",
                "updated_at",
            ]
        )

        return {
            "access_token": "mock_refreshed_access_token"
        }

    def test_connection(self):

        return bool(
            self.integration.access_token
        )

    def sync(self):

        return {
            "success": True,
            "provider": "MOCK",
            "employees": [
                {
                    "external_id": "EMP001",
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john@example.com",
                },
                {
                    "external_id": "EMP002",
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "email": "jane@example.com",
                },
            ],
        }