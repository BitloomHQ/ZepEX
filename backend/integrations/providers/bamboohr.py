import requests
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .base import BaseIntegrationProvider
from .registry import register_provider


@register_provider("BAMBOOHR")
class BambooHRProvider(BaseIntegrationProvider):

    AUTHORIZATION_URL_TEMPLATE = (
        "https://{domain}.bamboohr.com/authorize.php"
    )

    TOKEN_URL_TEMPLATE = (
        "https://{domain}.bamboohr.com/token.php"
    )

    def _get_domain(self):
        domain = (
            self.integration.bamboohr_domain or ""
        ).strip()

        if not domain:
            raise ValueError(
                "BambooHR company domain is required."
            )

        domain = (
            domain
            .replace("https://", "")
            .replace("http://", "")
            .strip("/")
        )

        if domain.endswith(".bamboohr.com"):
            domain = domain[:-len(".bamboohr.com")]

        return domain

    def get_authorization_url(self, request):

        domain = self._get_domain()

        redirect_uri = request.build_absolute_uri(
            reverse(
                "integration-oauth-callback",
                kwargs={
                    "provider": "BAMBOOHR",
                },
            )
        )

        from ..services import IntegrationService

        state = IntegrationService.create_oauth_state(
            self.integration
        )

        # Keep the first test scope simple.
        # offline_access is required if we want BambooHR
        # to return a refresh_token.
        scopes = [
            "user",
            "offline_access",
        ]

        params = {
            "request": "authorize",
            "state": state,
            "response_type": "code",
            "scope": " ".join(scopes),
            "client_id": settings.BAMBOOHR_CLIENT_ID,
            "redirect_uri": redirect_uri,
        }

        authorization_url = (
            self.AUTHORIZATION_URL_TEMPLATE.format(
                domain=domain
            )
        )

        return (
            f"{authorization_url}?"
            f"{urlencode(params)}"
        )

    def exchange_code_for_token(
        self,
        code,
        request,
    ):

        domain = self._get_domain()

        token_url = (
            self.TOKEN_URL_TEMPLATE.format(
                domain=domain
            )
        )

        redirect_uri = request.build_absolute_uri(
            reverse(
                "integration-oauth-callback",
                kwargs={
                    "provider": "BAMBOOHR",
                },
            )
        )

        response = requests.post(
            token_url,
            params={
                "request": "token",
            },
            data={
                "client_secret": (
                    settings.BAMBOOHR_CLIENT_SECRET
                ),
                "client_id": (
                    settings.BAMBOOHR_CLIENT_ID
                ),
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            headers={
                "Accept": "application/json",
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                ),
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        access_token = data.get(
            "access_token"
        )

        if not access_token:
            raise ValueError(
                "BambooHR did not return an access token."
            )

        refresh_token = data.get(
            "refresh_token"
        )

        expires_in = data.get(
            "expires_in"
        )

        self.integration.access_token = (
            access_token
        )

        self.integration.refresh_token = (
            refresh_token or ""
        )

        self.integration.scope = (
            data.get("scope") or ""
        )

        self.integration.external_account_id = (
            data.get("companyDomain")
            or domain
        )

        if expires_in:
            self.integration.token_expires_at = (
                timezone.now()
                + timezone.timedelta(
                    seconds=int(expires_in)
                )
            )
        else:
            self.integration.token_expires_at = None

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
                "token_expires_at",
                "status",
                "connected_at",
                "last_error",
                "updated_at",
            ]
        )

        return data

    def refresh_access_token(self):

        if not self.integration.refresh_token:
            raise ValueError(
                "No BambooHR refresh token is available."
            )

        domain = self._get_domain()

        token_url = (
            self.TOKEN_URL_TEMPLATE.format(
                domain=domain
            )
        )

        response = requests.post(
            token_url,
            params={
                "request": "token",
            },
            data={
                "client_secret": (
                    settings.BAMBOOHR_CLIENT_SECRET
                ),
                "client_id": (
                    settings.BAMBOOHR_CLIENT_ID
                ),
                "refresh_token": (
                    self.integration.refresh_token
                ),
                "grant_type": "refresh_token",
            },
            headers={
                "Accept": "application/json",
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                ),
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        access_token = data.get(
            "access_token"
        )

        if not access_token:
            raise ValueError(
                "BambooHR did not return a refreshed access token."
            )

        self.integration.access_token = (
            access_token
        )

        if data.get("refresh_token"):
            self.integration.refresh_token = (
                data["refresh_token"]
            )

        if data.get("scope"):
            self.integration.scope = (
                data["scope"]
            )

        if data.get("expires_in"):
            self.integration.token_expires_at = (
                timezone.now()
                + timezone.timedelta(
                    seconds=int(
                        data["expires_in"]
                    )
                )
            )

        self.integration.status = (
            self.integration.STATUS_CONNECTED
        )

        self.integration.last_error = None

        self.integration.save(
            update_fields=[
                "access_token",
                "refresh_token",
                "scope",
                "token_expires_at",
                "status",
                "last_error",
                "updated_at",
            ]
        )

        return data

    def test_connection(self):

        if not self.integration.access_token:
            return False

        domain = self._get_domain()

        url = (
            f"https://{domain}.bamboohr.com"
            "/api/v1/employees/directory"
        )

        response = requests.get(
            url,
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{self.integration.access_token}"
                ),
                "Accept": "application/json",
            },
            timeout=15,
        )

        if response.status_code == 401:
            return False

        response.raise_for_status()

        return True

    def sync(self):

        raise NotImplementedError(
            "BambooHR synchronization will be implemented "
            "after the OAuth connection is verified."
        )