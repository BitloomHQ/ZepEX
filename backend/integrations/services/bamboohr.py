import logging
from urllib.parse import urlencode

import requests

from django.conf import settings


logger = logging.getLogger(__name__)


# ==========================================================
# EXCEPTIONS
# ==========================================================


class BambooHRIntegrationError(Exception):
    """
    Base exception for BambooHR integration errors.
    """


class BambooHRAuthenticationError(
    BambooHRIntegrationError
):
    """
    BambooHR rejected the OAuth token or credentials.
    """


class BambooHRPermissionError(
    BambooHRIntegrationError
):
    """
    BambooHR authentication succeeded but the
    caller does not have access to the resource.
    """


class BambooHRConnectionError(
    BambooHRIntegrationError
):
    """
    Unable to communicate with BambooHR.
    """


# ==========================================================
# DOMAIN NORMALIZATION
# ==========================================================


def normalize_bamboohr_company_domain(
    company_domain,
):
    """
    Normalize BambooHR company domain.

    Accepted:

        bitloom
        https://bitloom.bamboohr.com
        bitloom.bamboohr.com

    Returns:

        bitloom
    """

    company_domain = (
        company_domain
        or ""
    ).strip().lower()

    if not company_domain:
        raise ValueError(
            "BambooHR company domain is required."
        )

    company_domain = (
        company_domain
        .replace(
            "https://",
            "",
        )
        .replace(
            "http://",
            "",
        )
    )

    company_domain = (
        company_domain.split(
            "/"
        )[0]
    )

    if company_domain.endswith(
        ".bamboohr.com"
    ):
        company_domain = (
            company_domain[
                :-len(
                    ".bamboohr.com"
                )
            ]
        )

    company_domain = (
        company_domain.strip(
            "."
        )
    )

    if not company_domain:
        raise ValueError(
            "Invalid BambooHR company domain."
        )

    return company_domain


# ==========================================================
# OAUTH SERVICE
# ==========================================================


class BambooHROAuthService:
    """
    Handles BambooHR OAuth 2.0 authorization.

    This class is used before BambooHRClient exists.

    Flow:

        company_domain
            ↓
        build_authorization_url()
            ↓
        BambooHR login/consent
            ↓
        callback code
            ↓
        exchange_authorization_code()
            ↓
        access_token + refresh_token
    """

    SCOPES = [
        "openid",
        "email",
        "employee",
        "employee:job",
        "employee:management",
        "employee:name",
        "field",
        "offline_access",
    ]

    def __init__(
        self,
        *,
        company_domain,
        timeout=30,
    ):

        self.company_domain = (
            normalize_bamboohr_company_domain(
                company_domain
            )
        )

        self.timeout = timeout

        self.client_id = (
            getattr(
                settings,
                "BAMBOOHR_CLIENT_ID",
                None,
            )
            or ""
        ).strip()

        self.client_secret = (
            getattr(
                settings,
                "BAMBOOHR_CLIENT_SECRET",
                None,
            )
            or ""
        ).strip()

        self.redirect_uri = (
            getattr(
                settings,
                "BAMBOOHR_REDIRECT_URI",
                None,
            )
            or ""
        ).strip()

        if not self.client_id:
            raise BambooHRIntegrationError(
                "BambooHR client ID is not configured."
            )

        if not self.client_secret:
            raise BambooHRIntegrationError(
                "BambooHR client secret is not configured."
            )

        if not self.redirect_uri:
            raise BambooHRIntegrationError(
                "BambooHR redirect URI is not configured."
            )

    # ======================================================
    # AUTHORIZATION URL
    # ======================================================

    def build_authorization_url(
        self,
        *,
        state,
    ):
        """
        Generate BambooHR OAuth authorization URL.
        """

        if not state:
            raise ValueError(
                "OAuth state is required."
            )

        authorization_url = (
            f"https://{self.company_domain}."
            "bamboohr.com/authorize.php"
        )

        params = {
            "request": "authorize",
            "state": state,
            "response_type": "code",
            "scope": " ".join(
                self.SCOPES
            ),
            "client_id": (
                self.client_id
            ),
            "redirect_uri": (
                self.redirect_uri
            ),
        }

        return (
            f"{authorization_url}?"
            f"{urlencode(params)}"
        )

    # ======================================================
    # TOKEN ENDPOINT
    # ======================================================

    @property
    def token_url(self):
        return (
            f"https://{self.company_domain}."
            "bamboohr.com/"
            "token.php?request=token"
        )

    # ======================================================
    # EXCHANGE AUTHORIZATION CODE
    # ======================================================

    def exchange_authorization_code(
        self,
        *,
        code,
    ):
        """
        Exchange BambooHR authorization code for tokens.
        """

        if not code:
            raise BambooHRAuthenticationError(
                "BambooHR authorization code is missing."
            )

        payload = {
            "client_secret": (
                self.client_secret
            ),
            "client_id": (
                self.client_id
            ),
            "code": code,
            "grant_type": (
                "authorization_code"
            ),
            "redirect_uri": (
                self.redirect_uri
            ),
        }

        return self._token_request(
            payload
        )

    # ======================================================
    # REFRESH TOKEN
    # ======================================================

    def refresh_access_token(
        self,
        *,
        refresh_token,
    ):
        """
        Refresh BambooHR access token.
        """

        if not refresh_token:
            raise BambooHRAuthenticationError(
                "BambooHR refresh token is missing."
            )

        payload = {
            "client_secret": (
                self.client_secret
            ),
            "client_id": (
                self.client_id
            ),
            "refresh_token": (
                refresh_token
            ),
            "grant_type": (
                "refresh_token"
            ),
            "redirect_uri": (
                self.redirect_uri
            ),
        }

        return self._token_request(
            payload
        )

    # ======================================================
    # INTERNAL TOKEN REQUEST
    # ======================================================

    def _token_request(
        self,
        payload,
    ):

        try:

            response = requests.post(
                self.token_url,
                data=payload,
                headers={
                    "Accept": (
                        "application/json"
                    ),
                    "Content-Type": (
                        "application/"
                        "x-www-form-urlencoded"
                    ),
                },
                timeout=self.timeout,
            )

        except requests.Timeout as exc:

            raise BambooHRConnectionError(
                "BambooHR OAuth request timed out."
            ) from exc

        except requests.ConnectionError as exc:

            raise BambooHRConnectionError(
                "Unable to connect to BambooHR OAuth service."
            ) from exc

        except requests.RequestException as exc:

            raise BambooHRConnectionError(
                "BambooHR OAuth request failed."
            ) from exc

        if response.status_code in (
            400,
            401,
        ):

            try:
                error_data = (
                    response.json()
                )
            except ValueError:
                error_data = {}

            error_description = (
                error_data.get(
                    "error_description"
                )
                or error_data.get(
                    "error"
                )
                or (
                    "BambooHR OAuth "
                    "authentication failed."
                )
            )

            raise BambooHRAuthenticationError(
                error_description
            )

        if response.status_code == 403:

            raise BambooHRPermissionError(
                "BambooHR OAuth access was denied."
            )

        if response.status_code == 429:

            raise BambooHRConnectionError(
                "BambooHR OAuth rate limit reached."
            )

        if response.status_code >= 500:

            raise BambooHRConnectionError(
                "BambooHR OAuth service is "
                "temporarily unavailable."
            )

        if not response.ok:

            raise BambooHRIntegrationError(
                (
                    "BambooHR OAuth request failed "
                    f"with status "
                    f"{response.status_code}."
                )
            )

        try:

            token_data = (
                response.json()
            )

        except ValueError as exc:

            raise BambooHRIntegrationError(
                (
                    "BambooHR OAuth returned "
                    "invalid JSON."
                )
            ) from exc

        access_token = (
            token_data.get(
                "access_token"
            )
        )

        if not access_token:

            raise BambooHRAuthenticationError(
                (
                    "BambooHR did not return "
                    "an access token."
                )
            )

        return token_data


# ==========================================================
# BAMBOOHR API CLIENT
# ==========================================================


class BambooHRClient:
    """
    BambooHR API client used by ZepEx.

    OAuth authentication:

        Authorization: Bearer <access_token>

    Example:

        BambooHRClient(
            company_domain="bitloom",
            access_token="...",
        )
    """

    BASE_DOMAIN = "bamboohr.com"

    def __init__(
        self,
        *,
        company_domain,
        access_token,
        timeout=30,
    ):

        self.company_domain = (
            normalize_bamboohr_company_domain(
                company_domain
            )
        )

        access_token = (
            access_token
            or ""
        ).strip()

        if not access_token:
            raise ValueError(
                "BambooHR access token is required."
            )

        self.access_token = (
            access_token
        )

        self.timeout = timeout

        self.base_url = (
            f"https://{self.company_domain}."
            f"{self.BASE_DOMAIN}/api"
        )

        # ======================================================
        # HTTP SESSION
        # ======================================================

        self.session = (
            requests.Session()
        )

        self.session.headers.update(
            {
                "Authorization": (
                    f"Bearer "
                    f"{self.access_token}"
                ),
                "Accept": (
                    "application/json"
                ),
                "User-Agent": (
                    "ZepEx-BambooHR-"
                    "Integration/2.0"
                ),
            }
        )

    # ======================================================
    # INTERNAL REQUEST
    # ======================================================

    def _request(
        self,
        method,
        endpoint,
        *,
        params=None,
        json=None,
    ):
        """
        Make authenticated BambooHR API request.
        """

        url = (
            f"{self.base_url}/"
            f"{endpoint.lstrip('/')}"
        )

        try:

            response = (
                self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    timeout=self.timeout,
                )
            )

        except requests.Timeout as exc:

            logger.exception(
                (
                    "BambooHR request timed out. "
                    "url=%s"
                ),
                url,
            )

            raise BambooHRConnectionError(
                "BambooHR request timed out."
            ) from exc

        except requests.ConnectionError as exc:

            logger.exception(
                (
                    "Unable to connect to "
                    "BambooHR. url=%s"
                ),
                url,
            )

            raise BambooHRConnectionError(
                "Unable to connect to BambooHR."
            ) from exc

        except requests.RequestException as exc:

            logger.exception(
                (
                    "BambooHR request failed. "
                    "url=%s"
                ),
                url,
            )

            raise BambooHRConnectionError(
                "BambooHR request failed."
            ) from exc

        # ==================================================
        # AUTHENTICATION
        # ==================================================

        if response.status_code == 401:

            raise BambooHRAuthenticationError(
                (
                    "BambooHR access token "
                    "is invalid or expired."
                )
            )

        # ==================================================
        # PERMISSION
        # ==================================================

        if response.status_code == 403:

            error_message = (
                response.headers.get(
                    "x-bamboohr-error-message"
                )
            )

            raise BambooHRPermissionError(
                error_message
                or (
                    "BambooHR authentication "
                    "succeeded but ZepEx does not "
                    "have permission to access "
                    "this resource."
                )
            )

        # ==================================================
        # RATE LIMIT
        # ==================================================

        if response.status_code == 429:

            retry_after = (
                response.headers.get(
                    "Retry-After"
                )
            )

            if retry_after:

                raise BambooHRConnectionError(
                    (
                        "BambooHR rate limit "
                        "reached. Retry after "
                        f"{retry_after} seconds."
                    )
                )

            raise BambooHRConnectionError(
                (
                    "BambooHR rate limit reached. "
                    "Please try again later."
                )
            )

        # ==================================================
        # SERVER ERROR
        # ==================================================

        if response.status_code >= 500:

            raise BambooHRConnectionError(
                (
                    "BambooHR is temporarily "
                    "unavailable."
                )
            )

        # ==================================================
        # OTHER API ERROR
        # ==================================================

        if not response.ok:

            error_message = (
                response.headers.get(
                    "x-bamboohr-error-message"
                )
            )

            raise BambooHRIntegrationError(
                error_message
                or (
                    "BambooHR API request failed "
                    f"with status "
                    f"{response.status_code}."
                )
            )

        # ==================================================
        # JSON RESPONSE
        # ==================================================

        try:

            return response.json()

        except ValueError as exc:

            raise BambooHRIntegrationError(
                (
                    "BambooHR returned an "
                    "invalid JSON response."
                )
            ) from exc

    # ======================================================
    # TEST CONNECTION
    # ======================================================

    def test_connection(self):
        """
        Test OAuth token and retrieve the
        authenticated employee record.
        """

        result = self._request(
            "GET",
            "v1/employees/0",
            params={
                "fields": (
                    "firstName,"
                    "lastName,"
                    "workEmail"
                ),
            },
        )

        return {
            "success": True,
            "company_domain": (
                self.company_domain
            ),
            "employee": result,
        }

    # ======================================================
    # LIST EMPLOYEES
    # ======================================================

    def list_employees(
        self,
        *,
        fields=None,
        limit=250,
        after=None,
    ):
        """
        Fetch one page of BambooHR employees.
        """

        if fields is None:

            fields = [
                "workEmail",
                "department",
                "supervisor",
                "supervisorEId",
                "status",
            ]

        params = {
            "fields": ",".join(
                fields
            ),
            "page[limit]": limit,
        }

        if after:

            params[
                "page[after]"
            ] = after

        return self._request(
            "GET",
            "v1/employees",
            params=params,
        )

    # ======================================================
    # GET ALL EMPLOYEES
    # ======================================================

    def get_all_employees(self):
        """
        Fetch every BambooHR employee using
        BambooHR cursor pagination.
        """

        employees = []

        after = None

        seen_cursors = set()

        while True:

            response = (
                self.list_employees(
                    limit=250,
                    after=after,
                )
            )

            page_employees = (
                response.get(
                    "data"
                )
                or []
            )

            employees.extend(
                page_employees
            )

            meta = (
                response.get(
                    "meta"
                )
                or {}
            )

            page = (
                meta.get(
                    "page"
                )
                or {}
            )

            next_cursor = (
                page.get(
                    "nextCursor"
                )
            )

            if not next_cursor:
                break

            if (
                next_cursor
                in seen_cursors
            ):

                logger.warning(
                    (
                        "BambooHR returned "
                        "duplicate pagination "
                        "cursor for company=%s."
                    ),
                    self.company_domain,
                )

                break

            seen_cursors.add(
                next_cursor
            )

            after = (
                next_cursor
            )

        logger.info(
            (
                "Fetched %s BambooHR "
                "employee(s) for "
                "company_domain=%s."
            ),
            len(
                employees
            ),
            self.company_domain,
        )

        return employees