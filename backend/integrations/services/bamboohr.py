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
        "webhooks",
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

        Allows ZepEx to obtain a new access token
        without requiring the Company Admin to
        authorize BambooHR again.
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
        """
        Send a token request to BambooHR.

        Used for both:

        1. Authorization code exchange
        2. Refresh token exchange

        IMPORTANT:
        OAuth response bodies are intentionally
        not logged because they contain sensitive
        access and refresh tokens.
        """

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

        # ==================================================
        # AUTHENTICATION ERROR
        # ==================================================

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

        # ==================================================
        # PERMISSION ERROR
        # ==================================================

        if response.status_code == 403:

            raise BambooHRPermissionError(
                "BambooHR OAuth access was denied."
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
                        "BambooHR OAuth rate limit "
                        f"reached. Retry after "
                        f"{retry_after} seconds."
                    )
                )

            raise BambooHRConnectionError(
                "BambooHR OAuth rate limit reached."
            )

        # ==================================================
        # BAMBOOHR SERVER ERROR
        # ==================================================

        if response.status_code >= 500:

            raise BambooHRConnectionError(
                (
                    "BambooHR OAuth service is "
                    "temporarily unavailable."
                )
            )

        # ==================================================
        # OTHER HTTP ERROR
        # ==================================================

        if not response.ok:

            raise BambooHRIntegrationError(
                (
                    "BambooHR OAuth request failed "
                    f"with status "
                    f"{response.status_code}."
                )
            )

        # ==================================================
        # PARSE TOKEN RESPONSE
        # ==================================================

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

        # ==================================================
        # VALIDATE ACCESS TOKEN
        # ==================================================

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

    Employee synchronization strategy:

        1. Fetch BambooHR employee roster using /v1/employees
        2. Collect employee IDs
        3. Fetch each employee's detailed record
        4. Return enriched employee records containing:

            - employeeId
            - firstName
            - lastName
            - workEmail
            - department
            - supervisor
            - supervisorEId
            - status

    BambooHR's bulk employee endpoint may not return
    department/supervisor fields even when explicitly
    requested, so individual employee records are fetched.
    """

    BASE_DOMAIN = "bamboohr.com"

    # ==========================================================
    # INITIALIZATION
    # ==========================================================

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

        self.access_token = access_token
        self.timeout = timeout

        self.base_url = (
            f"https://{self.company_domain}."
            f"{self.BASE_DOMAIN}/api"
        )

        # ======================================================
        # HTTP SESSION
        # ======================================================

        self.session = requests.Session()

        self.session.headers.update(
            {
                "Authorization": (
                    f"Bearer {self.access_token}"
                ),
                "Accept": "application/json",
                "User-Agent": (
                    "ZepEx-BambooHR-Integration/2.0"
                ),
            }
        )

    # ==========================================================
    # INTERNAL REQUEST
    # ==========================================================

    def _request(
        self,
        method,
        endpoint,
        *,
        params=None,
        json=None,
    ):
        """
        Make an authenticated BambooHR API request.

        OAuth credentials are never written to logs.
        """

        url = (
            f"{self.base_url}/"
            f"{endpoint.lstrip('/')}"
        )

        try:

            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json,
                timeout=self.timeout,
            )

            # ==================================================
            # SAFE ERROR LOGGING
            # ==================================================

            if not response.ok:

                logger.error(
                    (
                        "BambooHR API response. "
                        "method=%s "
                        "url=%s "
                        "status=%s "
                        "error_header=%s "
                        "retry_after=%s "
                        "body=%s"
                    ),
                    method,
                    url,
                    response.status_code,
                    response.headers.get(
                        "x-bamboohr-error-message"
                    ),
                    response.headers.get(
                        "Retry-After"
                    ),
                    response.text[:1000],
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
                    "Unable to connect to BambooHR. "
                    "url=%s"
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

        # ======================================================
        # AUTHENTICATION ERROR
        # ======================================================

        if response.status_code == 401:

            raise BambooHRAuthenticationError(
                (
                    "BambooHR access token "
                    "is invalid or expired."
                )
            )

        # ======================================================
        # PERMISSION ERROR
        # ======================================================

        if response.status_code == 403:

            error_message = (
                response.headers.get(
                    "x-bamboohr-error-message"
                )
            )

            raise BambooHRPermissionError(
                error_message
                or (
                    "BambooHR authentication succeeded "
                    "but ZepEx does not have permission "
                    "to access this resource."
                )
            )

        # ======================================================
        # RATE LIMIT
        # ======================================================

        if response.status_code == 429:

            retry_after = (
                response.headers.get(
                    "Retry-After"
                )
            )

            if retry_after:

                raise BambooHRConnectionError(
                    (
                        "BambooHR rate limit reached. "
                        f"Retry after "
                        f"{retry_after} seconds."
                    )
                )

            raise BambooHRConnectionError(
                (
                    "BambooHR rate limit reached. "
                    "Please try again later."
                )
            )

        # ======================================================
        # BAMBOOHR SERVER ERROR
        # ======================================================

        if response.status_code >= 500:

            error_message = (
                response.headers.get(
                    "x-bamboohr-error-message"
                )
            )

            if error_message:

                raise BambooHRConnectionError(
                    (
                        "BambooHR server error: "
                        f"{error_message}"
                    )
                )

            raise BambooHRConnectionError(
                (
                    "BambooHR is temporarily "
                    "unavailable "
                    f"(HTTP {response.status_code})."
                )
            )

        # ======================================================
        # OTHER API ERROR
        # ======================================================

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

        # ======================================================
        # EMPTY RESPONSE
        # ======================================================

        if response.status_code == 204:
            return {}

        if not response.content:
            return {}

        # ======================================================
        # JSON RESPONSE
        # ======================================================

        try:

            return response.json()

        except ValueError as exc:

            logger.error(
                (
                    "BambooHR returned invalid JSON. "
                    "method=%s "
                    "url=%s "
                    "status=%s"
                ),
                method,
                url,
                response.status_code,
            )

            raise BambooHRIntegrationError(
                (
                    "BambooHR returned an "
                    "invalid JSON response."
                )
            ) from exc

    # ==========================================================
    # LIST WEBHOOK MONITOR FIELDS
    # ==========================================================

    def list_webhook_monitor_fields(self):
        """
        Return employee fields that the authenticated
        BambooHR user can monitor through webhooks.
        """

        result = self._request(
            "GET",
            "v1/webhooks/monitor_fields",
        )

        if isinstance(
            result,
            dict,
        ):

            fields = (
                result.get("fields")
                or []
            )

            if isinstance(
                fields,
                list,
            ):

                return fields

        return []

    # ==========================================================
    # LIST WEBHOOKS
    # ==========================================================

    def list_webhooks(self):
        """
        Return all webhooks owned by the authenticated
        BambooHR user.
        """

        result = self._request(
            "GET",
            "v1/webhooks",
        )

        if isinstance(
            result,
            list,
        ):

            return result

        if isinstance(
            result,
            dict,
        ):

            webhooks = (
                result.get("webhooks")
                or []
            )

            if isinstance(
                webhooks,
                list,
            ):

                return webhooks

        return []

    # ==========================================================
    # CREATE WEBHOOK
    # ==========================================================

    def create_webhook(
        self,
        *,
        name,
        url,
        monitor_fields,
    ):
        """
        Register an event-based BambooHR employee webhook.

        BambooHR returns the privateKey only when the webhook
        is created. The caller must store it securely.
        """

        name = str(
            name
            or ""
        ).strip()

        url = str(
            url
            or ""
        ).strip()

        if not name:
            raise ValueError(
                "BambooHR webhook name is required."
            )

        if not url:
            raise ValueError(
                "BambooHR webhook URL is required."
            )

        if not url.startswith(
            "https://"
        ):
            raise ValueError(
                "BambooHR webhook URL must use HTTPS."
            )

        if not isinstance(
            monitor_fields,
            list,
        ):
            raise ValueError(
                "BambooHR monitor fields must be a list."
            )

        monitor_fields = [
            str(field).strip()
            for field in monitor_fields
            if str(field).strip()
        ]

        if not monitor_fields:
            raise ValueError(
                (
                    "At least one BambooHR monitor "
                    "field is required."
                )
            )

        payload = {
            "name": name,
            "url": url,
            "format": "json",
            "monitorFields": (
                monitor_fields
            ),
            "events": [
                "employee.created",
                "employee.updated",
                "employee.deleted",
            ],
        }

        result = self._request(
            "POST",
            "v1/webhooks",
            json=payload,
        )

        if not isinstance(
            result,
            dict,
        ):
            raise BambooHRIntegrationError(
                (
                    "BambooHR returned an invalid "
                    "webhook response."
                )
            )

        webhook_id = (
            result.get("id")
        )

        private_key = (
            result.get("privateKey")
        )

        if not webhook_id:
            raise BambooHRIntegrationError(
                (
                    "BambooHR did not return "
                    "a webhook ID."
                )
            )

        if not private_key:
            raise BambooHRIntegrationError(
                (
                    "BambooHR did not return a "
                    "webhook private key."
                )
            )

        return result

    # ==========================================================
    # GET WEBHOOK
    # ==========================================================

    def get_webhook(
        self,
        webhook_id,
    ):
        """
        Return one BambooHR webhook configuration.
        """

        if not webhook_id:
            raise ValueError(
                "BambooHR webhook ID is required."
            )

        return self._request(
            "GET",
            (
                f"v1/webhooks/"
                f"{webhook_id}"
            ),
        )

    # ==========================================================
    # DELETE WEBHOOK
    # ==========================================================

    def delete_webhook(
        self,
        webhook_id,
    ):
        """
        Delete a BambooHR webhook.
        """

        if not webhook_id:
            raise ValueError(
                "BambooHR webhook ID is required."
            )

        return self._request(
            "DELETE",
            (
                f"v1/webhooks/"
                f"{webhook_id}"
            ),
        )

    # ==========================================================
    # TEST CONNECTION
    # ==========================================================

    def test_connection(self):
        """
        Verify that the BambooHR OAuth access token works.

        Metadata fields are used so verification does not
        depend on any specific employee.
        """

        result = self._request(
            "GET",
            "v1/meta/fields",
        )

        field_count = 0

        if isinstance(
            result,
            list,
        ):

            field_count = len(
                result
            )

        elif isinstance(
            result,
            dict,
        ):

            fields = (
                result.get("fields")
                or result.get("data")
                or []
            )

            if isinstance(
                fields,
                list,
            ):

                field_count = len(
                    fields
                )

        return {
            "success": True,
            "company_domain": (
                self.company_domain
            ),
            "field_count": (
                field_count
            ),
        }

    # ==========================================================
    # LIST BAMBOOHR FIELDS
    # ==========================================================

    def list_fields(self):
        """
        Fetch BambooHR employee field metadata.
        """

        result = self._request(
            "GET",
            "v1/meta/fields",
        )

        if isinstance(
            result,
            list,
        ):

            return result

        if isinstance(
            result,
            dict,
        ):

            fields = (
                result.get("fields")
                or result.get("data")
                or []
            )

            if isinstance(
                fields,
                list,
            ):

                return fields

        return []

    # ==========================================================
    # GET SINGLE EMPLOYEE
    # ==========================================================

    def get_employee(
        self,
        employee_id,
        *,
        fields=None,
    ):
        """
        Fetch detailed information for one BambooHR employee.

        The single employee endpoint provides organization
        fields that may be absent from the bulk employee API.
        """

        if not employee_id:

            raise ValueError(
                "BambooHR employee ID is required."
            )

        if fields is None:

           fields = [
        "firstName",
        "lastName",
        "workEmail",
        "department",
        "jobTitle",
        "supervisor",
        "supervisorEId",
        "status",
    ]

        params = {
            "fields": ",".join(
                fields
            ),
        }

        result = self._request(
            "GET",
            (
                f"v1/employees/"
                f"{employee_id}"
            ),
            params=params,
        )

        if not isinstance(
            result,
            dict,
        ):

            return {}

        # ======================================================
        # NORMALIZE BAMBOOHR EMPLOYEE ID
        # ======================================================

        bamboohr_id = (
            result.get(
                "employeeId"
            )
            or result.get(
                "id"
            )
            or str(
                employee_id
            )
        )

        result[
            "employeeId"
        ] = str(
            bamboohr_id
        )

        return result

    # ==========================================================
    # LIST EMPLOYEES
    # ==========================================================

    def list_employees(
        self,
        *,
        fields=None,
        limit=250,
        after=None,
    ):
        """
        Fetch one page of BambooHR employees.

        The bulk endpoint is mainly used to obtain
        employee IDs. Detailed organization information
        is fetched afterward.
        """

        if fields is None:

            fields = [
                "workEmail",
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

    # ==========================================================
    # GET EMPLOYEE ROSTER
    # ==========================================================

    def get_employee_roster(self):
        """
        Fetch every BambooHR employee using cursor pagination.

        This returns the lightweight employee roster.
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

            if not isinstance(
                response,
                dict,
            ):

                raise BambooHRIntegrationError(
                    (
                        "BambooHR employee list "
                        "returned an unexpected "
                        "response."
                    )
                )

            page_employees = (
                response.get(
                    "data"
                )
                or []
            )

            if not isinstance(
                page_employees,
                list,
            ):

                raise BambooHRIntegrationError(
                    (
                        "BambooHR employee list "
                        "did not contain a valid "
                        "data array."
                    )
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

            # Protect against an accidental BambooHR
            # pagination loop.

            if (
                next_cursor
                in seen_cursors
            ):

                logger.warning(
                    (
                        "BambooHR returned duplicate "
                        "pagination cursor. "
                        "company_domain=%s"
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
                "Fetched %s BambooHR employee "
                "roster record(s). "
                "company_domain=%s"
            ),
            len(
                employees
            ),
            self.company_domain,
        )

        return employees

    # ==========================================================
    # ENRICH SINGLE EMPLOYEE
    # ==========================================================

    def enrich_employee(
        self,
        employee,
    ):
        """
        Fetch detailed BambooHR information for one employee
        and merge it into the bulk employee record.
        """

        if not isinstance(
            employee,
            dict,
        ):

            return None

        employee_id = (
            employee.get(
                "employeeId"
            )
            or employee.get(
                "id"
            )
        )

        if not employee_id:

            logger.warning(
                (
                    "Skipping BambooHR employee "
                    "without employee ID."
                )
            )

            return None

        detail = (
            self.get_employee(
                employee_id
            )
        )

        # Start with bulk employee data.

        enriched = dict(
            employee
        )

        # Detailed employee data wins where the
        # same field exists in both responses.

        if isinstance(
            detail,
            dict,
        ):

            enriched.update(
                detail
            )

        # ZepEx uses employeeId consistently for
        # BambooHR mapping.

        enriched[
            "employeeId"
        ] = str(
            employee_id
        )

        return enriched

    # ==========================================================
    # GET ALL EMPLOYEES
    # ==========================================================

    def get_all_employees(self):
        """
        Fetch and enrich all BambooHR employees.

        Flow:

            employee roster
                ↓
            employee IDs
                ↓
            individual employee detail
                ↓
            department + supervisor
                ↓
            enriched employee list

        Authentication errors are intentionally propagated
        so the outer integration synchronization service
        can refresh the OAuth token and retry.
        """

        roster = (
            self.get_employee_roster()
        )

        enriched_employees = []

        total = len(
            roster
        )

        logger.info(
            (
                "Starting BambooHR employee "
                "detail enrichment. "
                "company_domain=%s "
                "total=%s"
            ),
            self.company_domain,
            total,
        )

        for index, employee in enumerate(
            roster,
            start=1,
        ):

            employee_id = (
                employee.get(
                    "employeeId"
                )
                or employee.get(
                    "id"
                )
            )

            try:

                enriched_employee = (
                    self.enrich_employee(
                        employee
                    )
                )

                if enriched_employee:

                    enriched_employees.append(
                        enriched_employee
                    )

            # ==================================================
            # IMPORTANT:
            #
            # These errors MUST reach run_bamboohr_sync().
            #
            # Especially 401 -> BambooHRAuthenticationError,
            # because the sync layer can then refresh the
            # OAuth token automatically.
            # ==================================================

            except BambooHRAuthenticationError:
                raise

            except BambooHRPermissionError:
                raise

            except BambooHRConnectionError:
                raise

            except BambooHRIntegrationError:
                raise

            except Exception as exc:

                logger.exception(
                    (
                        "Unexpected error while "
                        "enriching BambooHR employee. "
                        "employee_id=%s "
                        "company_domain=%s"
                    ),
                    employee_id,
                    self.company_domain,
                )

                # Do not expose unnecessary employee
                # information through the public API.

                raise BambooHRIntegrationError(
                    (
                        "Unable to complete BambooHR "
                        "employee synchronization."
                    )
                ) from exc

            # ==================================================
            # SAFE PROGRESS LOGGING
            # ==================================================

            if (
                index % 25 == 0
                or index == total
            ):

                logger.info(
                    (
                        "BambooHR employee enrichment "
                        "progress: %s/%s "
                        "company_domain=%s"
                    ),
                    index,
                    total,
                    self.company_domain,
                )

        logger.info(
            (
                "Fetched and enriched %s "
                "BambooHR employee(s). "
                "company_domain=%s"
            ),
            len(
                enriched_employees
            ),
            self.company_domain,
        )

        return enriched_employees
