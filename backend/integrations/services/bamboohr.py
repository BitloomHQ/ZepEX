import logging

import requests


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
    BambooHR rejected the supplied credentials.
    """


class BambooHRPermissionError(
    BambooHRIntegrationError
):
    """
    BambooHR credentials are valid, but the user
    does not have permission to access the resource.
    """


class BambooHRConnectionError(
    BambooHRIntegrationError
):
    """
    Unable to communicate with BambooHR.
    """


# ==========================================================
# BAMBOOHR CLIENT
# ==========================================================


class BambooHRClient:
    """
    BambooHR API client used by ZepEx.

    Current authentication:
        username = BambooHR API key
        password = arbitrary value

    Example BambooHR URL:

        https://bitloom.bamboohr.com

    company_domain:

        bitloom
    """

    BASE_DOMAIN = "bamboohr.com"

    # ======================================================
    # INITIALIZATION
    # ======================================================

    def __init__(
        self,
        *,
        company_domain,
        api_key,
        timeout=30,
    ):

        company_domain = (
            company_domain or ""
        ).strip().lower()

        api_key = (
            api_key or ""
        ).strip()

        # --------------------------------------------------
        # Validate required configuration
        # --------------------------------------------------

        if not company_domain:
            raise ValueError(
                "BambooHR company domain is required."
            )

        if not api_key:
            raise ValueError(
                "BambooHR API key is required."
            )

        # --------------------------------------------------
        # Normalize company domain
        # --------------------------------------------------

        company_domain = company_domain.replace(
            "https://",
            "",
        ).replace(
            "http://",
            "",
        )

        company_domain = company_domain.split(
            "/"
        )[0]

        if company_domain.endswith(
            ".bamboohr.com"
        ):
            company_domain = company_domain[
                :-len(".bamboohr.com")
            ]

        company_domain = company_domain.strip(
            "."
        )

        if not company_domain:
            raise ValueError(
                "Invalid BambooHR company domain."
            )

        self.company_domain = company_domain
        self.api_key = api_key
        self.timeout = timeout

        # --------------------------------------------------
        # BambooHR API base URL
        # --------------------------------------------------

        self.base_url = (
            f"https://{self.company_domain}."
            f"{self.BASE_DOMAIN}/api"
        )

        # --------------------------------------------------
        # Reusable HTTP session
        # --------------------------------------------------

        self.session = requests.Session()

        self.session.auth = (
            self.api_key,
            "x",
        )

        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": (
                    "ZepEx-BambooHR-Integration/1.0"
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
        Make a request to BambooHR and normalize
        common API errors into ZepEx exceptions.
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

        except requests.Timeout as exc:

            logger.exception(
                "BambooHR request timed out. url=%s",
                url,
            )

            raise BambooHRConnectionError(
                "BambooHR request timed out."
            ) from exc

        except requests.ConnectionError as exc:

            logger.exception(
                "Unable to connect to BambooHR. url=%s",
                url,
            )

            raise BambooHRConnectionError(
                "Unable to connect to BambooHR."
            ) from exc

        except requests.RequestException as exc:

            logger.exception(
                "BambooHR request failed. url=%s",
                url,
            )

            raise BambooHRConnectionError(
                "BambooHR request failed."
            ) from exc

        # --------------------------------------------------
        # Authentication error
        # --------------------------------------------------

        if response.status_code == 401:

            raise BambooHRAuthenticationError(
                "BambooHR authentication failed. "
                "Check the API key."
            )

        # --------------------------------------------------
        # Permission error
        # --------------------------------------------------

        if response.status_code == 403:

            error_message = response.headers.get(
                "x-bamboohr-error-message"
            )

            raise BambooHRPermissionError(
                error_message
                or (
                    "BambooHR authentication succeeded "
                    "but this user does not have permission "
                    "to access this resource."
                )
            )

        # --------------------------------------------------
        # Rate limit
        # --------------------------------------------------

        if response.status_code == 429:

            retry_after = response.headers.get(
                "Retry-After"
            )

            if retry_after:

                raise BambooHRConnectionError(
                    "BambooHR rate limit reached. "
                    f"Retry after {retry_after} seconds."
                )

            raise BambooHRConnectionError(
                "BambooHR rate limit reached. "
                "Please try again later."
            )

        # --------------------------------------------------
        # BambooHR server errors
        # --------------------------------------------------

        if response.status_code >= 500:

            raise BambooHRConnectionError(
                "BambooHR is temporarily unavailable."
            )

        # --------------------------------------------------
        # Other API errors
        # --------------------------------------------------

        if not response.ok:

            error_message = response.headers.get(
                "x-bamboohr-error-message"
            )

            raise BambooHRIntegrationError(
                error_message
                or (
                    "BambooHR API request failed "
                    f"with status "
                    f"{response.status_code}."
                )
            )

        # --------------------------------------------------
        # Parse JSON
        # --------------------------------------------------

        try:

            return response.json()

        except ValueError as exc:

            raise BambooHRIntegrationError(
                "BambooHR returned an invalid "
                "JSON response."
            ) from exc

    # ======================================================
    # TEST CONNECTION
    # ======================================================

    def test_connection(self):
        """
        Test BambooHR credentials.
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
            "company_domain": self.company_domain,
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

        Fields requested support:

        - employee identity
        - department sync
        - reporting manager sync
        - employee lifecycle sync
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
            "fields": ",".join(fields),
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
        Fetch all BambooHR employees.

        Cursor pagination is followed until there
        is no next cursor.
        """

        employees = []

        after = None

        seen_cursors = set()

        while True:

            response = self.list_employees(
                limit=250,
                after=after,
            )

            page_employees = (
                response.get("data")
                or []
            )

            employees.extend(
                page_employees
            )

            meta = (
                response.get("meta")
                or {}
            )

            page = (
                meta.get("page")
                or {}
            )

            next_cursor = page.get(
                "nextCursor"
            )

            if not next_cursor:
                break

            # --------------------------------------------------
            # Prevent infinite pagination loop
            # --------------------------------------------------

            if next_cursor in seen_cursors:

                logger.warning(
                    "BambooHR returned duplicate "
                    "pagination cursor for company=%s.",
                    self.company_domain,
                )

                break

            seen_cursors.add(
                next_cursor
            )

            after = next_cursor

        logger.info(
            "Fetched %s BambooHR employee(s) "
            "for company_domain=%s.",
            len(employees),
            self.company_domain,
        )

        return employees