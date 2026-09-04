import hashlib
import hmac
import json
import logging
import secrets

from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import redirect
from django.utils import timezone

from rest_framework.decorators import (
    authentication_classes,
    api_view,
    permission_classes,
)

from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
)

from rest_framework.response import Response

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
)

from rest_framework.permissions import (
    IsAuthenticated,
)
from .services.quickbooks_export import (
    QuickBooksExportError,
    reconcile_quickbooks_export,
)
from rest_framework.response import Response
from rest_framework import status

from integrations.models import (
    CompanyIntegration,
)

# ==========================================================
# AUDIT LOGS
# ==========================================================

from audit_logs.models import AuditLog

from audit_logs.utils import (
    create_integration_audit_log,
)


# ==========================================================
# TENANT PERMISSIONS
# ==========================================================

from tenants.permission_utils import (
    has_company_permission,
)


# ==========================================================
# INTEGRATION MODELS
# ==========================================================

from expenses.models import ExpenseReport

from .models import (
    CompanyIntegration,
    IntegrationCredential,
    IntegrationSyncLog,
    QuickBooksCategoryMapping,
    QuickBooksExportRecord,
    QuickBooksOAuthState,
)


# ==========================================================
# SERIALIZERS
# ==========================================================

from .serializers import (
    BambooHRStatusSerializer,
    CompanyIntegrationSerializer,
    IntegrationSyncLogSerializer,
    QuickBooksCategoryMappingSerializer,
)


# ==========================================================
# ENCRYPTION
# ==========================================================

from .encryption_services import (
    encrypt_integration_config,
    decrypt_integration_config,
)

from .schema import (
    get_company_integration,
    integration_has_credentials,
    list_company_integrations,
)


# ==========================================================
# BAMBOOHR
# ==========================================================

from .services.bamboohr import (
    BambooHRClient,
    BambooHROAuthService,
    BambooHRIntegrationError,
    BambooHRAuthenticationError,
    BambooHRPermissionError,
    BambooHRConnectionError,
)


# ==========================================================
# BAMBOOHR SYNC
# ==========================================================

from .services.integration_sync import (
    run_bamboohr_sync,
)


# ==========================================================
# QUICKBOOKS
# ==========================================================

from .services.quickbooks import (
    QuickBooksClient,
    QuickBooksIntegrationError,
)

from .services.quickbooks_auth import (
    get_valid_quickbooks_access_token,
)


# ==========================================================
# CELERY TASKS
# ==========================================================

from .tasks import (
    export_report_to_quickbooks_task,
    process_bamboohr_webhook_event,
)
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)
QUICKBOOKS_PENDING_STALE_MINUTES = 5


def redirect_quickbooks_oauth_to_frontend(view_func):
    """Send Intuit's browser callback back to the admin integrations page."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        result = view_func(request, *args, **kwargs)
        frontend = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
        if not frontend or not isinstance(result, Response):
            return result
        data = result.data if isinstance(result.data, dict) else {}
        params = {}
        if data.get("success"):
            params["quickbooks"] = "connected"
        else:
            params["quickbooks"] = "error"
            error = data.get("error")
            if error:
                params["quickbooks_error"] = str(error)[:400]
        return redirect(f"{frontend}/admin/integrations?{urlencode(params)}")

    return wrapped


def is_quickbooks_export_stale(
    export_record,
):
    """
    Consider a PENDING QuickBooks export stale when it has
    not been updated for more than 5 minutes.

    A stale export can safely be queued again.
    """

    if (
        export_record.status
        != QuickBooksExportRecord.STATUS_PENDING
    ):
        return False

    stale_before = (
        timezone.now()
        - timedelta(
            minutes=(
                QUICKBOOKS_PENDING_STALE_MINUTES
            )
        )
    )

    return (
        export_record.updated_at
        < stale_before
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integration_list(request):

    profile = request.user.profile

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    can_view = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not can_view:
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to view integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    integrations = list_company_integrations(
        profile.company,
    )

    serializer = CompanyIntegrationSerializer(
        integrations,
        many=True,
    )

    return Response(
        {
            "success": True,
            "count": len(integrations),
            "results": serializer.data,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integration_provider_catalog(request):

    profile = request.user.profile

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    providers = []

    connected_map = {
        integration.provider: integration
        for integration in list_company_integrations(
            profile.company,
        )
    }

    for value, label in (
        CompanyIntegration.PROVIDER_CHOICES
    ):

        integration = connected_map.get(
            value
        )

        providers.append(
            {
                "provider": value,
                "provider_name": label,

                "configured": integration_has_credentials(
                    integration
                ),

                "is_connected": (
                    integration.is_connected
                    if integration
                    else False
                ),

                "is_active": (
                    integration.is_active
                    if integration
                    else False
                ),

                "last_synced_at": (
                    integration.last_synced_at
                    if integration
                    else None
                ),
            }
        )

    return Response(
        {
            "success": True,
            "providers": providers,
        },
        status=status.HTTP_200_OK,
    )

from rest_framework.decorators import (
    api_view,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from tenants.permission_utils import has_company_permission

from .services.bamboohr import (
    BambooHRClient,
    BambooHRAuthenticationError,
    BambooHRPermissionError,
    BambooHRConnectionError,
    BambooHRIntegrationError,
)




from rest_framework.decorators import (
    api_view,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from tenants.permission_utils import has_company_permission

from .models import (
    CompanyIntegration,
    IntegrationCredential,
)

from .encryption_services import (
    decrypt_integration_config,
    encrypt_integration_config,
)

from .services.bamboohr import (
    BambooHRClient,
    BambooHRAuthenticationError,
    BambooHRPermissionError,
    BambooHRConnectionError,
    BambooHRIntegrationError,
)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def connect_bamboohr(request):

    profile = request.user.profile

    # ==========================================================
    # 1. PERMISSION
    # ==========================================================

    if not (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    ):
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to manage integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. COMPANY DOMAIN
    # ==========================================================

    company_domain = str(
        request.data.get(
            "company_domain",
            "",
        )
    ).strip()

    if not company_domain:
        return Response(
            {
                "success": False,
                "error": "company_domain is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 3. CREATE / GET INTEGRATION
    # ==========================================================

    integration, _ = (
        CompanyIntegration.objects
        .get_or_create(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_BAMBOOHR
            ),
            defaults={
                "is_connected": False,
                "is_active": True,
            },
        )
    )

    # ==========================================================
    # 4. CREATE OAUTH STATE
    # ==========================================================

    state = secrets.token_urlsafe(
        32
    )

    # Store temporary OAuth state information.
    # We use encrypted IntegrationCredential for now
    # so callback can identify company/domain safely.

    temporary_config = {
        "oauth_state": state,
        "company_domain": company_domain,
        "oauth_started_by_profile_id": str(
            profile.id
        ),
        "oauth_started_at": (
            timezone.now().isoformat()
        ),
    }

    try:

        encrypted_config = (
            encrypt_integration_config(
                temporary_config
            )
        )

        IntegrationCredential.objects.update_or_create(
            integration=integration,
            defaults={
                "encrypted_config": encrypted_config,
            },
        )

    except Exception as exc:

        logger.exception(
            "Unable to store BambooHR OAuth state."
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to start BambooHR authorization."
                ),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # ==========================================================
    # 5. BUILD BAMBOOHR AUTHORIZATION URL
    # ==========================================================

    try:

        oauth_service = (
            BambooHROAuthService(
                company_domain=company_domain,
            )
        )

        authorization_url = (
            oauth_service
            .build_authorization_url(
                state=state,
            )
        )

    except (
        BambooHRIntegrationError,
        ValueError,
    ) as exc:

        return Response(
            {
                "success": False,
                "error": str(
                    exc
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 6. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,
            "provider": "BAMBOOHR",
            "connected": False,
            "company_domain": (
                oauth_service.company_domain
            ),
            "authorization_url": (
                authorization_url
            ),
            "message": (
                "Redirect the user to BambooHR "
                "to authorize ZepEx."
            ),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([AllowAny])
def bamboohr_callback(request):
    """
    BambooHR OAuth callback.

    BambooHR redirects here with:

        code
        state
    """

    code = (
        request.query_params.get(
            "code"
        )
    )

    returned_state = (
        request.query_params.get(
            "state"
        )
    )

    oauth_error = (
        request.query_params.get(
            "error"
        )
    )

    # ==========================================================
    # 1. BAMBOOHR AUTHORIZATION ERROR
    # ==========================================================

    if oauth_error:

        return Response(
            {
                "success": False,
                "error": oauth_error,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not code:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR authorization code "
                    "is missing."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not returned_state:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR OAuth state is missing."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. FIND THE MATCHING INTEGRATION
    # ==========================================================

    matched_integration = None
    matched_config = None

    integrations = (
        CompanyIntegration.objects
        .filter(
            provider=(
                CompanyIntegration
                .PROVIDER_BAMBOOHR
            ),
            is_active=True,
        )
        .select_related(
            "company",
            "credential",
        )
    )

    for integration in integrations:

        try:

            config = (
                decrypt_integration_config(
                    integration
                    .credential
                    .encrypted_config
                )
            )

        except Exception:
            continue

        if (
            config.get(
                "oauth_state"
            )
            == returned_state
        ):

            matched_integration = (
                integration
            )

            matched_config = config

            break

    if not matched_integration:

        return Response(
            {
                "success": False,
                "error": (
                    "Invalid or expired "
                    "BambooHR OAuth state."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 3. VALIDATE OAUTH STATE AGE
    # ==========================================================

    started_at_raw = (
        matched_config.get(
            "oauth_started_at"
        )
    )

    if started_at_raw:

        try:

            started_at = (
                timezone.datetime.fromisoformat(
                    started_at_raw
                )
            )

            if timezone.is_naive(
                started_at
            ):
                started_at = (
                    timezone.make_aware(
                        started_at
                    )
                )

            if (
                timezone.now()
                - started_at
                > timedelta(
                    minutes=10
                )
            ):

                return Response(
                    {
                        "success": False,
                        "error": (
                            "BambooHR authorization "
                            "request has expired."
                        ),
                    },
                    status=(
                        status.HTTP_400_BAD_REQUEST
                    ),
                )

        except Exception:
            pass

    company_domain = (
        matched_config.get(
            "company_domain"
        )
    )

    # ==========================================================
    # 4. EXCHANGE CODE FOR TOKENS
    # ==========================================================

    try:

        oauth_service = (
            BambooHROAuthService(
                company_domain=company_domain,
            )
        )

        token_data = (
            oauth_service
            .exchange_authorization_code(
                code=code,
            )
        )

    except (
        BambooHRAuthenticationError,
        BambooHRPermissionError,
        BambooHRConnectionError,
        BambooHRIntegrationError,
        ValueError,
    ) as exc:

        create_integration_audit_log(
            company=(
                matched_integration
                .company
            ),
            integration=(
                matched_integration
            ),
            provider="BAMBOOHR",
            action=(
                "BAMBOOHR_CONNECTION_FAILED"
            ),
            action_by=None,
            message=(
                "BambooHR OAuth token "
                "exchange failed."
            ),
            metadata={
                "company_domain": (
                    company_domain
                ),
                "stage": (
                    "TOKEN_EXCHANGE"
                ),
                "error": str(
                    exc
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": str(
                    exc
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 5. VALIDATE TOKEN DATA
    # ==========================================================

    access_token = (
        token_data.get(
            "access_token"
        )
    )

    refresh_token = (
        token_data.get(
            "refresh_token"
        )
    )

    expires_in = (
        token_data.get(
            "expires_in"
        )
    )

    if not access_token:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR did not return "
                    "an access token."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 6. TEST ACCESS TOKEN
    # ==========================================================

    try:

        client = (
            BambooHRClient(
                company_domain=(
                    company_domain
                ),
                access_token=(
                    access_token
                ),
            )
        )

        test_result = (
            client.test_connection()
        )

    except (
        BambooHRAuthenticationError,
        BambooHRPermissionError,
        BambooHRConnectionError,
        BambooHRIntegrationError,
        ValueError,
    ) as exc:

        create_integration_audit_log(
            company=(
                matched_integration.company
            ),
            integration=(
                matched_integration
            ),
            provider="BAMBOOHR",
            action=(
                "BAMBOOHR_CONNECTION_FAILED"
            ),
            action_by=None,
            message=(
                "BambooHR connection validation failed."
            ),
            metadata={
                "company_domain": company_domain,
                "stage": (
                    "TOKEN_VALIDATION"
                ),
                "error": str(
                    exc
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": str(
                    exc
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 7. REGISTER BAMBOOHR WEBHOOK
    # ==========================================================

    webhook_base_url = (
        getattr(
            settings,
            "BAMBOOHR_WEBHOOK_URL",
            "",
        )
        or ""
    ).strip()

    if not webhook_base_url:

        create_integration_audit_log(
            company=(
                matched_integration.company
            ),
            integration=(
                matched_integration
            ),
            provider="BAMBOOHR",
            action=(
                "BAMBOOHR_CONNECTION_FAILED"
            ),
            action_by=None,
            message=(
                "BambooHR webhook URL is not configured."
            ),
            metadata={
                "company_domain": company_domain,
                "stage": (
                    "WEBHOOK_CONFIGURATION"
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": (
                    "BAMBOOHR_WEBHOOK_URL "
                    "is not configured."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    webhook_base_url = (
        webhook_base_url.rstrip("/")
    )

    if not webhook_base_url.startswith(
        "https://"
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "BAMBOOHR_WEBHOOK_URL must "
                    "use HTTPS."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # Each integration gets its own receiver URL. This lets
    # the receiver locate the correct encrypted private key
    # before verifying the BambooHR HMAC signature.

    webhook_url = (
        f"{webhook_base_url}/"
        f"{matched_integration.id}/"
    )

    webhook_name = (
        "ZepEx Employee Sync - "
        f"{matched_integration.id}"
    )

    desired_monitor_fields = {
        "firstname",
        "lastname",
        "workemail",
        "department",
        "jobtitle",
        "supervisor",
        "supervisoreid",
        "supervisorid",
        "reportingto",
        "reportingtoemployeeid",
        "status",
        "employmentstatus",
    }

    webhook_id = None
    webhook_private_key = None
    monitor_fields = []

    try:

        available_fields = (
            client.list_webhook_monitor_fields()
        )

        seen_field_identifiers = set()

        for field in available_fields:

            if not isinstance(
                field,
                dict,
            ):
                continue

            field_identifier = str(
                field.get("alias")
                or field.get("id")
                or ""
            ).strip()

            if not field_identifier:
                continue

            searchable_values = [
                field.get("alias"),
                field.get("name"),
                field.get("displayName"),
            ]

            matches_required_field = False

            for value in searchable_values:

                normalized_value = "".join(
                    character.lower()
                    for character in str(
                        value
                        or ""
                    )
                    if character.isalnum()
                )

                if (
                    normalized_value
                    in desired_monitor_fields
                ):

                    matches_required_field = True
                    break

            if (
                matches_required_field
                and field_identifier
                not in seen_field_identifiers
            ):

                monitor_fields.append(
                    field_identifier
                )

                seen_field_identifiers.add(
                    field_identifier
                )

        if not monitor_fields:
            raise BambooHRPermissionError(
                (
                    "BambooHR did not provide access "
                    "to any employee fields required "
                    "for webhook monitoring."
                )
            )

        # Remove an earlier ZepEx webhook owned by the same
        # BambooHR user. This prevents duplicate deliveries
        # when a company reconnects the integration.

        existing_webhooks = (
            client.list_webhooks()
        )

        for existing_webhook in existing_webhooks:

            if not isinstance(
                existing_webhook,
                dict,
            ):
                continue

            existing_name = str(
                existing_webhook.get("name")
                or ""
            ).strip()

            existing_url = str(
                existing_webhook.get("url")
                or ""
            ).strip()

            if (
                existing_name != webhook_name
                and existing_url != webhook_url
            ):
                continue

            existing_webhook_id = (
                existing_webhook.get("id")
            )

            if existing_webhook_id:
                client.delete_webhook(
                    existing_webhook_id
                )

        webhook_result = (
            client.create_webhook(
                name=webhook_name,
                url=webhook_url,
                monitor_fields=(
                    monitor_fields
                ),
            )
        )

        webhook_id = str(
            webhook_result.get("id")
        )

        webhook_private_key = (
            webhook_result.get(
                "privateKey"
            )
        )

    except (
        BambooHRAuthenticationError,
        BambooHRPermissionError,
        BambooHRConnectionError,
        BambooHRIntegrationError,
        ValueError,
    ) as exc:

        matched_integration.bamboohr_webhook_id = None
        matched_integration.bamboohr_webhook_enabled = False
        matched_integration.last_sync_error = str(
            exc
        )

        matched_integration.save(
            update_fields=[
                "bamboohr_webhook_id",
                "bamboohr_webhook_enabled",
                "last_sync_error",
                "updated_at",
            ]
        )

        create_integration_audit_log(
            company=(
                matched_integration.company
            ),
            integration=(
                matched_integration
            ),
            provider="BAMBOOHR",
            action=(
                "BAMBOOHR_CONNECTION_FAILED"
            ),
            action_by=None,
            message=(
                "BambooHR webhook registration failed."
            ),
            metadata={
                "company_domain": company_domain,
                "stage": (
                    "WEBHOOK_REGISTRATION"
                ),
                "error": str(
                    exc
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": str(
                    exc
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 8. STORE TOKENS AND WEBHOOK KEY SECURELY
    # ==========================================================

    now = timezone.now()

    final_config = {
        "auth_type": "OAUTH2",

        "company_domain": (
            company_domain
        ),

        "access_token": (
            access_token
        ),

        "refresh_token": (
            refresh_token
        ),

        "access_token_expires_at": (
            (
                now
                + timedelta(
                    seconds=int(
                        expires_in
                    )
                )
            ).isoformat()
            if expires_in
            else None
        ),

        "scope": (
            token_data.get(
                "scope"
            )
        ),

        "token_type": (
            token_data.get(
                "token_type"
            )
            or "Bearer"
        ),

        # BambooHR returns this key only once. It is encrypted
        # together with the OAuth tokens and is never included
        # in an API response or application log.

        "bamboohr_webhook_private_key": (
            webhook_private_key
        ),

        "bamboohr_webhook_url": (
            webhook_url
        ),

        "bamboohr_webhook_monitor_fields": (
            monitor_fields
        ),
    }

    try:

        encrypted_config = (
            encrypt_integration_config(
                final_config
            )
        )

        IntegrationCredential.objects.update_or_create(
            integration=(
                matched_integration
            ),
            defaults={
                "encrypted_config": (
                    encrypted_config
                ),
            },
        )

    except Exception as exc:

        logger.exception(
            (
                "Unable to store BambooHR OAuth tokens "
                "and webhook credentials."
            )
        )

        # Avoid leaving an unusable external webhook behind
        # when its private key could not be stored by ZepEx.

        if webhook_id:

            try:
                client.delete_webhook(
                    webhook_id
                )

            except Exception:
                logger.exception(
                    (
                        "Unable to clean up BambooHR "
                        "webhook after credential "
                        "storage failure."
                    )
                )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to securely save "
                    "BambooHR credentials."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 9. MARK CONNECTED AND WEBHOOK ENABLED
    # ==========================================================

    matched_integration.is_connected = True
    matched_integration.is_active = True
    matched_integration.last_sync_error = None
    matched_integration.bamboohr_webhook_id = (
        webhook_id
    )
    matched_integration.bamboohr_webhook_enabled = True
    matched_integration.bamboohr_webhook_created_at = now

    matched_integration.save(
        update_fields=[
            "is_connected",
            "is_active",
            "last_sync_error",
            "bamboohr_webhook_id",
            "bamboohr_webhook_enabled",
            "bamboohr_webhook_created_at",
            "updated_at",
        ]
    )

    # ==========================================================
    # 10. AUDIT LOG
    # ==========================================================

    create_integration_audit_log(
        company=(
            matched_integration.company
        ),
        integration=(
            matched_integration
        ),
        provider="BAMBOOHR",
        action="BAMBOOHR_CONNECTED",
        action_by=None,
        message=(
            "BambooHR connected successfully "
            "using OAuth."
        ),
        metadata={
            "company_domain": (
                company_domain
            ),
            "integration_id": str(
                matched_integration.id
            ),
            "auth_type": "OAUTH2",
            "webhook_id": (
                webhook_id
            ),
            "webhook_enabled": True,
            "monitor_field_count": len(
                monitor_fields
            ),
        },
    )

    # ==========================================================
    # 11. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,
            "connected": True,
            "message": (
                "BambooHR connected successfully."
            ),
            "provider": "BAMBOOHR",
            "integration_id": str(
                matched_integration.id
            ),
            "company_domain": (
                company_domain
            ),
            "webhook": {
                "enabled": True,
                "id": webhook_id,
                "monitor_field_count": len(
                    monitor_fields
                ),
            },
            "bamboohr_user": (
                test_result.get(
                    "employee"
                )
            ),
        },
        status=status.HTTP_200_OK,
    )

# ==========================================================
# BAMBOOHR WEBHOOK RECEIVER
# ==========================================================


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def bamboohr_webhook(
    request,
    integration_id,
):
    """
    Receive an event-based BambooHR employee webhook.

    Security flow:

        integration-specific URL
            ↓
        encrypted private key
            ↓
        HMAC-SHA256 verification
            ↓
        payload validation
            ↓
        duplicate-delivery protection
            ↓
        Celery task

    BambooHR signs:

        raw_request_body + X-BambooHR-Timestamp
    """

    # ======================================================
    # 1. FIND ACTIVE WEBHOOK INTEGRATION
    # ======================================================

    try:

        integration = (
            CompanyIntegration.objects
            .select_related(
                "credential",
            )
            .get(
                id=integration_id,
                provider=(
                    CompanyIntegration
                    .PROVIDER_BAMBOOHR
                ),
                is_connected=True,
                is_active=True,
                bamboohr_webhook_enabled=True,
            )
        )

    except CompanyIntegration.DoesNotExist:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook integration "
                    "was not found."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # ======================================================
    # 2. READ ENCRYPTED WEBHOOK PRIVATE KEY
    # ======================================================

    try:

        config = decrypt_integration_config(
            integration
            .credential
            .encrypted_config
        )

    except Exception:

        logger.exception(
            (
                "Unable to decrypt BambooHR webhook "
                "credentials. integration=%s"
            ),
            integration.id,
        )

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook credentials "
                    "are unavailable."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    if not isinstance(
        config,
        dict,
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook credentials "
                    "are invalid."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    private_key = str(
        config.get(
            "bamboohr_webhook_private_key"
        )
        or ""
    ).strip()

    if not private_key:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook private key "
                    "is missing."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ======================================================
    # 3. READ SIGNATURE HEADERS AND RAW BODY
    # ======================================================

    webhook_timestamp = str(
        request.headers.get(
            "X-BambooHR-Timestamp"
        )
        or ""
    ).strip()

    received_signature = str(
        request.headers.get(
            "X-BambooHR-Signature"
        )
        or ""
    ).strip()

    if (
        not webhook_timestamp
        or not received_signature
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook signature "
                    "headers are missing."
                ),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    raw_body = request.body

    # Employee event payloads are small. Reject unexpectedly
    # large bodies before parsing or queueing them.

    if len(raw_body) > 1_000_000:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook payload "
                    "is too large."
                ),
            },
            status=(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            ),
        )

    if not raw_body:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook payload "
                    "is empty."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ======================================================
    # 4. VERIFY BAMBOOHR HMAC-SHA256 SIGNATURE
    # ======================================================

    signed_content = (
        raw_body
        + webhook_timestamp.encode(
            "utf-8"
        )
    )

    expected_signature = hmac.new(
        private_key.encode("utf-8"),
        signed_content,
        hashlib.sha256,
    ).hexdigest()

    # Accept both the documented hexadecimal signature and
    # the common optional "sha256=" prefix.

    normalized_signature = (
        received_signature
    )

    if normalized_signature.lower().startswith(
        "sha256="
    ):

        normalized_signature = (
            normalized_signature.split(
                "=",
                1,
            )[1]
        )

    signature_is_valid = hmac.compare_digest(
        expected_signature.lower(),
        normalized_signature.lower(),
    )

    if not signature_is_valid:

        logger.warning(
            (
                "Rejected BambooHR webhook with "
                "invalid signature. integration=%s"
            ),
            integration.id,
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Invalid BambooHR webhook "
                    "signature."
                ),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    # ======================================================
    # 5. PARSE AND VALIDATE EVENT PAYLOAD
    # ======================================================

    try:

        payload = json.loads(
            raw_body.decode("utf-8")
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook payload "
                    "must contain valid JSON."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(
        payload,
        dict,
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook payload "
                    "must be a JSON object."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    event_type = str(
        payload.get("type")
        or ""
    ).strip().lower()

    allowed_event_types = {
        "employee.created",
        "employee.updated",
        "employee.deleted",
    }

    if event_type not in allowed_event_types:

        return Response(
            {
                "success": False,
                "error": (
                    "Unsupported BambooHR webhook event."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    event_data = (
        payload.get("data")
        or {}
    )

    if not isinstance(
        event_data,
        dict,
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook event data "
                    "is invalid."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    employee_id = str(
        event_data.get("employeeId")
        or ""
    ).strip()

    event_timestamp = str(
        payload.get("timestamp")
        or webhook_timestamp
    ).strip()

    if not employee_id:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR webhook employee ID "
                    "is missing."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ======================================================
    # 6. PREVENT DUPLICATE DELIVERY PROCESSING
    # ======================================================

    delivery_fingerprint = hashlib.sha256(
        (
            f"{integration.id}:"
            f"{webhook_timestamp}:"
            f"{normalized_signature.lower()}"
        ).encode("utf-8")
    ).hexdigest()

    delivery_cache_key = (
        "bamboohr:webhook:delivery:"
        f"{delivery_fingerprint}"
    )

    is_new_delivery = cache.add(
        delivery_cache_key,
        True,
        timeout=600,
    )

    if not is_new_delivery:

        return Response(
            {
                "success": True,
                "duplicate": True,
                "message": (
                    "BambooHR webhook was already accepted."
                ),
            },
            status=status.HTTP_200_OK,
        )

    # ======================================================
    # 7. QUEUE CELERY PROCESSING
    # ======================================================

    try:

        task = (
            process_bamboohr_webhook_event.delay(
                str(integration.id),
                event_type,
                employee_id,
                event_timestamp,
            )
        )

    except Exception:

        # Allow BambooHR's retry to queue the delivery again.
        cache.delete(
            delivery_cache_key
        )

        logger.exception(
            (
                "Unable to queue BambooHR webhook event. "
                "integration=%s event=%s employee=%s"
            ),
            integration.id,
            event_type,
            employee_id,
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to queue BambooHR "
                    "webhook processing."
                ),
            },
            status=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
        )

    logger.info(
        (
            "Accepted BambooHR webhook event. "
            "integration=%s event=%s employee=%s "
            "task=%s"
        ),
        integration.id,
        event_type,
        employee_id,
        task.id,
    )

    return Response(
        {
            "success": True,
            "accepted": True,
            "event_type": event_type,
            "employee_id": employee_id,
            "task_id": str(
                task.id
            ),
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preview_bamboohr_employees(request):

    profile = request.user.profile

    # ==========================================================
    # 1. COMPANY CHECK
    # ==========================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. PERMISSION
    # ==========================================================

    if not (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
    ):
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "view integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 3. FIND CONNECTED BAMBOOHR INTEGRATION
    # ==========================================================

    try:

        integration = (
            CompanyIntegration.objects
            .select_related(
                "credential"
            )
            .get(
                company=profile.company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_BAMBOOHR
                ),
                is_connected=True,
                is_active=True,
            )
        )

    except CompanyIntegration.DoesNotExist:

        return Response(
            {
                "success": False,
                "error": "BambooHR is not connected.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 4. DECRYPT OAUTH CONFIG
    # ==========================================================

    try:

        config = decrypt_integration_config(
            integration
            .credential
            .encrypted_config
        )

    except Exception:

        logger.exception(
            "Unable to decrypt BambooHR credentials."
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to read BambooHR "
                    "credentials."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 5. READ OAUTH VALUES
    # ==========================================================

    company_domain = (
        config.get(
            "company_domain"
        )
        or ""
    ).strip()

    access_token = (
        config.get(
            "access_token"
        )
        or ""
    ).strip()

    refresh_token = (
        config.get(
            "refresh_token"
        )
        or ""
    ).strip()

    if not company_domain:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR company domain "
                    "is missing."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not access_token:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR access token "
                    "is missing."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 6. CREATE OAUTH CLIENT
    # ==========================================================

    try:

        client = BambooHRClient(
            company_domain=(
                company_domain
            ),
            access_token=(
                access_token
            ),
        )

        employees = (
            client.get_all_employees()
        )

    # ==========================================================
    # 7. ACCESS TOKEN EXPIRED
    # ==========================================================

    except BambooHRAuthenticationError:

        if not refresh_token:

            return Response(
                {
                    "success": False,
                    "error": (
                        "BambooHR access token "
                        "expired and no refresh "
                        "token is available."
                    ),
                },
                status=(
                    status.HTTP_401_UNAUTHORIZED
                ),
            )

        try:

            oauth_service = (
                BambooHROAuthService(
                    company_domain=(
                        company_domain
                    ),
                )
            )

            token_data = (
                oauth_service
                .refresh_access_token(
                    refresh_token=(
                        refresh_token
                    ),
                )
            )

            new_access_token = (
                token_data.get(
                    "access_token"
                )
            )

            new_refresh_token = (
                token_data.get(
                    "refresh_token"
                )
                or refresh_token
            )

            expires_in = (
                token_data.get(
                    "expires_in"
                )
            )

            if not new_access_token:

                raise BambooHRAuthenticationError(
                    (
                        "BambooHR token refresh "
                        "did not return an "
                        "access token."
                    )
                )

            # ----------------------------------------------
            # Update encrypted config
            # ----------------------------------------------

            config[
                "access_token"
            ] = new_access_token

            config[
                "refresh_token"
            ] = new_refresh_token

            if expires_in:

                config[
                    "access_token_expires_at"
                ] = (
                    timezone.now()
                    + timedelta(
                        seconds=int(
                            expires_in
                        )
                    )
                ).isoformat()

            encrypted_config = (
                encrypt_integration_config(
                    config
                )
            )

            IntegrationCredential.objects.update_or_create(
                integration=integration,
                defaults={
                    "encrypted_config": (
                        encrypted_config
                    ),
                },
            )

            # ----------------------------------------------
            # Retry BambooHR call
            # ----------------------------------------------

            client = BambooHRClient(
                company_domain=(
                    company_domain
                ),
                access_token=(
                    new_access_token
                ),
            )

            employees = (
                client.get_all_employees()
            )

        except (
            BambooHRAuthenticationError,
            BambooHRPermissionError,
            BambooHRConnectionError,
            BambooHRIntegrationError,
            ValueError,
        ) as exc:

            return Response(
                {
                    "success": False,
                    "error": str(
                        exc
                    ),
                },
                status=(
                    status.HTTP_401_UNAUTHORIZED
                ),
            )

    except BambooHRPermissionError as exc:

        return Response(
            {
                "success": False,
                "error": str(
                    exc
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    except (
        BambooHRConnectionError,
        BambooHRIntegrationError,
        ValueError,
    ) as exc:

        return Response(
            {
                "success": False,
                "error": str(
                    exc
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 8. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,
            "provider": "BAMBOOHR",
            "count": len(
                employees
            ),
            "employees": employees,
        },
        status=status.HTTP_200_OK,
    )
from django.utils import timezone

from .models import (
    CompanyIntegration,
    IntegrationCredential,
    IntegrationSyncLog,
    IntegrationChangeLog,
    QuickBooksCategoryMapping,
    QuickBooksOAuthState,
)

from .encryption_services import (
    decrypt_integration_config,
)

from .services.bamboohr import (
    BambooHRClient,
    BambooHRAuthenticationError,
    BambooHRPermissionError,
    BambooHRIntegrationError,
)

from .services.bamboohr_sync import (
    sync_bamboohr_departments,
    sync_bamboohr_employees_only,
    sync_bamboohr_managers,
    sync_bamboohr_all,
)

from .services.integration_sync import (
    run_bamboohr_sync,
)


def _get_bamboohr_sync_integration(
    profile,
):
    """
    Return the connected BambooHR integration
    for the current company.

    Returns:
        (integration, error_response)
    """

    # ==========================================================
    # 1. COMPANY CHECK
    # ==========================================================

    if not profile.company:

        return (
            None,
            Response(
                {
                    "success": False,
                    "error": (
                        "Company is not assigned."
                    ),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            ),
        )

    # ==========================================================
    # 2. PERMISSION CHECK
    # ==========================================================

    if not (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    ):

        return (
            None,
            Response(
                {
                    "success": False,
                    "error": (
                        "You are not allowed to "
                        "manage integrations."
                    ),
                },
                status=(
                    status.HTTP_403_FORBIDDEN
                ),
            ),
        )

    # ==========================================================
    # 3. FIND CONNECTED BAMBOOHR
    # ==========================================================

    try:

        integration = (
            CompanyIntegration.objects
            .select_related(
                "credential"
            )
            .get(
                company=profile.company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_BAMBOOHR
                ),
                is_connected=True,
                is_active=True,
            )
        )

    except CompanyIntegration.DoesNotExist:

        return (
            None,
            Response(
                {
                    "success": False,
                    "error": (
                        "BambooHR is not connected."
                    ),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            ),
        )

    return (
        integration,
        None,
    )


def _run_bamboohr_resource_sync(
    *,
    profile,
    resource,
):
    """
    Run BambooHR synchronization for one resource.

    Supported:

        DEPARTMENTS
        EMPLOYEES
        MANAGERS
        ALL
    """

    # ==========================================================
    # 1. GET INTEGRATION
    # ==========================================================

    (
        integration,
        error_response,
    ) = _get_bamboohr_sync_integration(
        profile
    )

    if error_response:

        return error_response

    # ==========================================================
    # 2. RUN SYNC
    # ==========================================================

    result = run_bamboohr_sync(
        integration=integration,
        trigger=(
            IntegrationSyncLog
            .TRIGGER_MANUAL
        ),
        resource=resource,
    )

    # ==========================================================
    # 3. FAILED SYNC
    # ==========================================================

    if not result.get(
        "success"
    ):

        return Response(
            result,
            status=(
                status.HTTP_400_BAD_REQUEST
            ),
        )

    # ==========================================================
    # 4. SUCCESS
    # ==========================================================

    return Response(
        result,
        status=status.HTTP_200_OK,
    )


# ==============================================================
# BAMBOOHR — SYNC DEPARTMENTS
# ==============================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_bamboohr_departments_view(
    request,
):
    """
    Synchronize BambooHR departments only.
    """

    profile = request.user.profile

    return _run_bamboohr_resource_sync(
        profile=profile,
        resource="DEPARTMENTS",
    )


# ==============================================================
# BAMBOOHR — SYNC EMPLOYEES
# ==============================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_bamboohr_employees_view(
    request,
):
    """
    Synchronize BambooHR employees only.

    Departments are not created here.
    Run department sync first when needed.
    """

    profile = request.user.profile

    return _run_bamboohr_resource_sync(
        profile=profile,
        resource="EMPLOYEES",
    )


# ==============================================================
# BAMBOOHR — SYNC MANAGERS
# ==============================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_bamboohr_managers_view(
    request,
):
    """
    Synchronize:

    - employee reporting managers
    - department manager relationships

    Employees should already be synchronized.
    """

    profile = request.user.profile

    return _run_bamboohr_resource_sync(
        profile=profile,
        resource="MANAGERS",
    )


# ==============================================================
# BAMBOOHR — SYNC ALL
# ==============================================================


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_bamboohr_all_view(
    request,
):
    """
    Run complete BambooHR synchronization.

    Order:

        Departments
            ↓
        Employees
            ↓
        Managers
    """

    profile = request.user.profile

    return _run_bamboohr_resource_sync(
        profile=profile,
        resource="ALL",
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bamboohr_status(request):

    profile = request.user.profile

    # ==========================================================
    # 1. PERMISSION
    # ==========================================================

    can_view = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not can_view:

        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "view integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 2. COMPANY
    # ==========================================================

    if not profile.company:

        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 3. FIND BAMBOOHR INTEGRATION
    # ==========================================================

    integration = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_BAMBOOHR
            ),
        )
        .select_related(
            "credential"
        )
        .first()
    )

    # ==========================================================
    # 4. NOT CONFIGURED
    # ==========================================================

    if not integration:

        return Response(
            {
                "success": True,
                "provider": "BAMBOOHR",
                "connected": False,
                "configured": False,
                "integration": None,

                "sync_status": {
                    "departments": None,
                    "employees": None,
                    "managers": None,
                    "all": None,
                },
            },
            status=status.HTTP_200_OK,
        )

    # ==========================================================
    # 5. SERIALIZED INTEGRATION
    # ==========================================================

    serializer = (
        BambooHRStatusSerializer(
            integration
        )
    )

    # ==========================================================
    # 6. HELPER — LATEST SYNC BY RESOURCE
    # ==========================================================

    def get_latest_resource_sync(
        resource,
    ):

        sync_log = (
            IntegrationSyncLog.objects
            .filter(
                integration=integration,
                stats__resource=resource,
            )
            .order_by(
                "-started_at"
            )
            .first()
        )

        if not sync_log:
            return None

        return {
            "sync_log_id": str(
                sync_log.id
            ),

            "resource": resource,

            "status": (
                sync_log.status
            ),

            "trigger": (
                sync_log.trigger
            ),

            "records_received": (
                sync_log.records_received
            ),

            "records_created": (
                sync_log.records_created
            ),

            "records_updated": (
                sync_log.records_updated
            ),

            "records_skipped": (
                sync_log.records_skipped
            ),

            "error_message": (
                sync_log.error_message
            ),

            "started_at": (
                sync_log.started_at
            ),

            "completed_at": (
                sync_log.completed_at
            ),
        }

    # ==========================================================
    # 7. RESOURCE-WISE STATUS
    # ==========================================================

    resource_status = {
        "departments": (
            get_latest_resource_sync(
                "DEPARTMENTS"
            )
        ),

        "employees": (
            get_latest_resource_sync(
                "EMPLOYEES"
            )
        ),

        "managers": (
            get_latest_resource_sync(
                "MANAGERS"
            )
        ),

        "all": (
            get_latest_resource_sync(
                "ALL"
            )
        ),
    }

    # ==========================================================
    # 8. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,

            "provider": "BAMBOOHR",

            "connected": (
                integration.is_connected
            ),

            "configured": (
                serializer.data[
                    "configured"
                ]
            ),

            "integration": (
                serializer.data
            ),

            "sync_status": (
                resource_status
            ),
        },
        status=status.HTTP_200_OK,
    )
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bamboohr_sync_history(request):

    profile = request.user.profile

    # ==========================================================
    # 1. COMPANY CHECK
    # ==========================================================

    if not profile.company:

        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. PERMISSION CHECK
    # ==========================================================

    can_view = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not can_view:

        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "view integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 3. FIND BAMBOOHR INTEGRATION
    # ==========================================================

    try:

        integration = (
            CompanyIntegration.objects
            .get(
                company=profile.company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_BAMBOOHR
                ),
            )
        )

    except CompanyIntegration.DoesNotExist:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR integration "
                    "not found."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # ==========================================================
    # 4. OPTIONAL RESOURCE FILTER
    # ==========================================================

    resource = (
        request.query_params.get(
            "resource",
            "",
        )
        or ""
    ).strip().upper()

    allowed_resources = {
        "DEPARTMENTS",
        "EMPLOYEES",
        "MANAGERS",
        "ALL",
    }

    if (
        resource
        and resource
        not in allowed_resources
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "Invalid resource. "
                    "Allowed values are: "
                    "DEPARTMENTS, EMPLOYEES, "
                    "MANAGERS, ALL."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 5. OPTIONAL STATUS FILTER
    # ==========================================================

    sync_status = (
        request.query_params.get(
            "status",
            "",
        )
        or ""
    ).strip().upper()

    allowed_statuses = {
        IntegrationSyncLog.STATUS_RUNNING,
        IntegrationSyncLog.STATUS_SUCCESS,
        IntegrationSyncLog.STATUS_FAILED,
    }

    if (
        sync_status
        and sync_status
        not in allowed_statuses
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "Invalid status. "
                    "Allowed values are: "
                    "RUNNING, SUCCESS, FAILED."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 6. OPTIONAL TRIGGER FILTER
    # ==========================================================

    trigger = (
        request.query_params.get(
            "trigger",
            "",
        )
        or ""
    ).strip().upper()

    allowed_triggers = {
        IntegrationSyncLog.TRIGGER_MANUAL,
        IntegrationSyncLog.TRIGGER_SCHEDULED,
    }

    if (
        trigger
        and trigger
        not in allowed_triggers
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "Invalid trigger. "
                    "Allowed values are: "
                    "MANUAL, SCHEDULED."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 7. LIMIT
    # ==========================================================

    try:

        limit = int(
            request.query_params.get(
                "limit",
                20,
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        limit = 20

    limit = max(
        1,
        min(
            limit,
            100,
        ),
    )

    # ==========================================================
    # 8. BASE QUERY
    # ==========================================================

    logs = (
        IntegrationSyncLog.objects
        .filter(
            integration=integration,
        )
    )

    # ==========================================================
    # 9. APPLY RESOURCE FILTER
    # ==========================================================

    if resource:

        logs = logs.filter(
            stats__resource=resource,
        )

    # ==========================================================
    # 10. APPLY STATUS FILTER
    # ==========================================================

    if sync_status:

        logs = logs.filter(
            status=sync_status,
        )

    # ==========================================================
    # 11. APPLY TRIGGER FILTER
    # ==========================================================

    if trigger:

        logs = logs.filter(
            trigger=trigger,
        )

    # ==========================================================
    # 12. ORDER + LIMIT
    # ==========================================================

    logs = (
        logs
        .order_by(
            "-started_at"
        )[:limit]
    )

    # ==========================================================
    # 13. SERIALIZE
    # ==========================================================

    serializer = (
        IntegrationSyncLogSerializer(
            logs,
            many=True,
        )
    )

    # ==========================================================
    # 14. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,

            "provider": "BAMBOOHR",

            "filters": {
                "resource": (
                    resource
                    or None
                ),
                "status": (
                    sync_status
                    or None
                ),
                "trigger": (
                    trigger
                    or None
                ),
                "limit": limit,
            },

            "count": len(
                serializer.data
            ),

            "results": (
                serializer.data
            ),
        },
        status=status.HTTP_200_OK,
    )
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def connect_quickbooks(request):
    """
    Start QuickBooks OAuth connection.

    Returns an Intuit authorization URL.
    The frontend redirects the browser to that URL.
    """

    profile = request.user.profile

    # ==========================================================
    # 1. COMPANY CHECK
    # ==========================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. PERMISSION
    # ==========================================================

    if not (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    ):
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "manage integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 3. CHECK EXISTING CONNECTION
    # ==========================================================

    existing = get_company_integration(
        profile.company,
        provider=(
            CompanyIntegration
            .PROVIDER_QUICKBOOKS
        ),
        is_connected=True,
    )

    if existing:
        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks is already connected."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 4. REMOVE OLD UNUSED STATES
    # ==========================================================

    QuickBooksOAuthState.objects.filter(
        company=profile.company,
        user=request.user,
        is_used=False,
    ).delete()

    # ==========================================================
    # 5. GENERATE SECURE STATE
    # ==========================================================

    oauth_state = (
        secrets.token_urlsafe(48)
    )

    QuickBooksOAuthState.objects.create(
        company=profile.company,
        user=request.user,
        state=oauth_state,
        expires_at=(
            timezone.now()
            + timedelta(minutes=10)
        ),
    )

    # ==========================================================
    # 6. GENERATE INTUIT AUTHORIZATION URL
    # ==========================================================

    try:

        client = QuickBooksClient()

        authorization_url = (
            client.get_authorization_url(
                state=oauth_state,
            )
        )

    except Exception as exc:

        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # ==========================================================
    # 7. RETURN TO FRONTEND
    # ==========================================================

    return Response(
        {
            "success": True,
            "provider": "QUICKBOOKS",
            "authorization_url": authorization_url,
            "expires_in": 600,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([AllowAny])
@redirect_quickbooks_oauth_to_frontend
def quickbooks_callback(request):
    """
    Handle Intuit OAuth callback.

    Expected query parameters:

        code
        state
        realmId
    """

    code = request.query_params.get(
        "code"
    )

    returned_state = request.query_params.get(
        "state"
    )

    realm_id = request.query_params.get(
        "realmId"
    )

    oauth_error = request.query_params.get(
        "error"
    )

    # ==========================================================
    # 1. INTUIT AUTHORIZATION ERROR
    # ==========================================================

    if oauth_error:

        return Response(
            {
                "success": False,
                "error": oauth_error,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. VALIDATE REQUIRED PARAMETERS
    # ==========================================================

    if not code:

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks authorization "
                    "code is missing."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not returned_state:

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks OAuth state "
                    "is missing."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not realm_id:

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks realm ID "
                    "is missing."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 3. FIND OAUTH STATE
    # ==========================================================

    try:

        oauth_state = (
            QuickBooksOAuthState.objects
            .select_related(
                "company",
                "user",
                "user__profile",
            )
            .get(
                state=returned_state,
                is_used=False,
            )
        )

    except QuickBooksOAuthState.DoesNotExist:

        return Response(
            {
                "success": False,
                "error": (
                    "Invalid or already used "
                    "QuickBooks OAuth state."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 4. RESOLVE ACTION USER
    # ==========================================================

    try:

        action_by = (
            oauth_state.user.profile
        )

    except Exception:

        action_by = None

    # ==========================================================
    # 5. CHECK EXPIRATION
    # ==========================================================

    if oauth_state.is_expired():

        oauth_state.is_used = True

        oauth_state.save(
            update_fields=[
                "is_used",
            ]
        )

        create_integration_audit_log(
            company=oauth_state.company,
            provider="QUICKBOOKS",
            action=(
                "QUICKBOOKS_CONNECTION_FAILED"
            ),
            action_by=action_by,
            message=(
                "QuickBooks connection failed "
                "because the OAuth request expired."
            ),
            metadata={
                "stage": (
                    "OAUTH_STATE_VALIDATION"
                ),
                "realm_id": str(
                    realm_id
                ),
                "error": (
                    "OAuth state expired."
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks authorization "
                    "request has expired."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 6. EXCHANGE CODE FOR TOKENS
    # ==========================================================

    try:

        client = QuickBooksClient()

        token_data = (
            client.exchange_authorization_code(
                code=code,
            )
        )

    except QuickBooksIntegrationError as exc:

        create_integration_audit_log(
            company=oauth_state.company,
            provider="QUICKBOOKS",
            action=(
                "QUICKBOOKS_CONNECTION_FAILED"
            ),
            action_by=action_by,
            message=(
                "QuickBooks OAuth token "
                "exchange failed."
            ),
            metadata={
                "stage": (
                    "TOKEN_EXCHANGE"
                ),
                "realm_id": str(
                    realm_id
                ),
                "error": str(
                    exc
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": str(
                    exc
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except Exception as exc:

        logger.exception(
            "Unexpected QuickBooks OAuth "
            "token exchange error."
        )

        create_integration_audit_log(
            company=oauth_state.company,
            provider="QUICKBOOKS",
            action=(
                "QUICKBOOKS_CONNECTION_FAILED"
            ),
            action_by=action_by,
            message=(
                "Unexpected QuickBooks OAuth "
                "token exchange failure."
            ),
            metadata={
                "stage": (
                    "TOKEN_EXCHANGE"
                ),
                "realm_id": str(
                    realm_id
                ),
                "error": str(
                    exc
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": str(
                    exc
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 7. EXTRACT TOKENS
    # ==========================================================

    access_token = token_data.get(
        "access_token"
    )

    refresh_token = token_data.get(
        "refresh_token"
    )

    expires_in = token_data.get(
        "expires_in"
    )

    refresh_token_expires_in = (
        token_data.get(
            "x_refresh_token_expires_in"
        )
    )

    # ==========================================================
    # 8. VALIDATE TOKENS
    # ==========================================================

    if (
        not access_token
        or not refresh_token
    ):

        create_integration_audit_log(
            company=oauth_state.company,
            provider="QUICKBOOKS",
            action=(
                "QUICKBOOKS_CONNECTION_FAILED"
            ),
            action_by=action_by,
            message=(
                "QuickBooks did not return "
                "required OAuth tokens."
            ),
            metadata={
                "stage": (
                    "TOKEN_VALIDATION"
                ),
                "realm_id": str(
                    realm_id
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks did not return "
                    "the required OAuth tokens."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 9. VERIFY QUICKBOOKS COMPANY
    # ==========================================================

    try:

        company_info_response = (
            client.get_company_info(
                realm_id=realm_id,
                access_token=access_token,
            )
        )

    except QuickBooksIntegrationError as exc:

        create_integration_audit_log(
            company=oauth_state.company,
            provider="QUICKBOOKS",
            action=(
                "QUICKBOOKS_CONNECTION_FAILED"
            ),
            action_by=action_by,
            message=(
                "QuickBooks company "
                "verification failed."
            ),
            metadata={
                "stage": (
                    "COMPANY_VERIFICATION"
                ),
                "realm_id": str(
                    realm_id
                ),
                "error": str(
                    exc
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks authorization "
                    "succeeded but company "
                    "verification failed: "
                    f"{str(exc)}"
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except Exception as exc:

        logger.exception(
            "Unexpected QuickBooks company "
            "verification error."
        )

        create_integration_audit_log(
            company=oauth_state.company,
            provider="QUICKBOOKS",
            action=(
                "QUICKBOOKS_CONNECTION_FAILED"
            ),
            action_by=action_by,
            message=(
                "Unexpected QuickBooks company "
                "verification failure."
            ),
            metadata={
                "stage": (
                    "COMPANY_VERIFICATION"
                ),
                "realm_id": str(
                    realm_id
                ),
                "error": str(
                    exc
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to verify the "
                    "QuickBooks company."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    company_info = (
        company_info_response.get(
            "CompanyInfo"
        )
        or {}
    )

    # ==========================================================
    # 10. CREATE / UPDATE INTEGRATION
    # ==========================================================

    integration, _ = (
        CompanyIntegration.objects
        .get_or_create(
            company=(
                oauth_state.company
            ),
            provider=(
                CompanyIntegration
                .PROVIDER_QUICKBOOKS
            ),
        )
    )

    integration.is_connected = True
    integration.is_active = True
    integration.last_sync_error = None

    integration.save(
        update_fields=[
            "is_connected",
            "is_active",
            "last_sync_error",
            "updated_at",
        ]
    )

    # ==========================================================
    # 11. BUILD SECRET CONFIG
    # ==========================================================

    now = timezone.now()

    config = {

        "realm_id": str(
            realm_id
        ),

        "access_token": (
            access_token
        ),

        "refresh_token": (
            refresh_token
        ),

        "access_token_expires_at": (
            (
                now
                + timedelta(
                    seconds=int(
                        expires_in
                    )
                )
            ).isoformat()
            if expires_in
            else None
        ),

        "refresh_token_expires_at": (
            (
                now
                + timedelta(
                    seconds=int(
                        refresh_token_expires_in
                    )
                )
            ).isoformat()
            if refresh_token_expires_in
            else None
        ),

        "quickbooks_company_name": (
            company_info.get(
                "CompanyName"
            )
        ),
    }

    # ==========================================================
    # 12. ENCRYPT CONFIG
    # ==========================================================

    try:

        encrypted_config = (
            encrypt_integration_config(
                config
            )
        )

        IntegrationCredential.objects.update_or_create(
            integration=integration,
            defaults={
                "encrypted_config": (
                    encrypted_config
                ),
            },
        )

    except Exception as exc:

        logger.exception(
            "Unable to save QuickBooks "
            "OAuth credentials."
        )

        # ----------------------------------------------
        # Roll back connection state logically
        # ----------------------------------------------

        integration.is_connected = False
        integration.is_active = False

        integration.last_sync_error = str(
            exc
        )

        integration.save(
            update_fields=[
                "is_connected",
                "is_active",
                "last_sync_error",
                "updated_at",
            ]
        )

        create_integration_audit_log(
            company=oauth_state.company,
            integration=integration,
            provider="QUICKBOOKS",
            action=(
                "QUICKBOOKS_CONNECTION_FAILED"
            ),
            action_by=action_by,
            message=(
                "QuickBooks connection failed "
                "while saving OAuth credentials."
            ),
            metadata={
                "stage": (
                    "CREDENTIAL_STORAGE"
                ),
                "realm_id": str(
                    realm_id
                ),
                "error": str(
                    exc
                ),
            },
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to securely save "
                    "QuickBooks credentials."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 13. MARK OAUTH STATE USED
    # ==========================================================

    oauth_state.is_used = True

    oauth_state.save(
        update_fields=[
            "is_used",
        ]
    )

    # ==========================================================
    # 14. SUCCESS AUDIT LOG
    # ==========================================================

    create_integration_audit_log(
        company=oauth_state.company,
        integration=integration,
        provider="QUICKBOOKS",
        action=(
            "QUICKBOOKS_CONNECTED"
        ),
        action_by=action_by,
        message=(
            "QuickBooks connected successfully."
        ),
        metadata={
            "realm_id": str(
                realm_id
            ),
            "quickbooks_company_name": (
                company_info.get(
                    "CompanyName"
                )
            ),
        },
    )

    # ==========================================================
    # 15. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,

            "message": (
                "QuickBooks connected successfully."
            ),

            "provider": (
                "QUICKBOOKS"
            ),

            "integration_id": str(
                integration.id
            ),

            "company": {

                "realm_id": str(
                    realm_id
                ),

                "name": (
                    company_info.get(
                        "CompanyName"
                    )
                ),
            },
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def quickbooks_status(request):

    profile = request.user.profile

    can_view = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not can_view:
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to view integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    integration = get_company_integration(
        profile.company,
        provider=(
            CompanyIntegration
            .PROVIDER_QUICKBOOKS
        ),
    )

    if not integration:

        return Response(
            {
                "success": True,
                "provider": "QUICKBOOKS",
                "connected": False,
                "integration": None,
            },
            status=status.HTTP_200_OK,
        )

    if not integration.is_connected:

        return Response(
            {
                "success": True,
                "provider": "QUICKBOOKS",
                "connected": False,
                "integration_id": str(
                    integration.id
                ),
            },
            status=status.HTTP_200_OK,
        )

    try:

        token_result = (
            get_valid_quickbooks_access_token(
                integration=integration,
            )
        )

        config = token_result["config"]

        client = QuickBooksClient()

        company_info_response = (
            client.get_company_info(
                realm_id=config.get(
                    "realm_id"
                ),
                access_token=(
                    token_result[
                        "access_token"
                    ]
                ),
            )
        )

        company_info = (
            company_info_response.get(
                "CompanyInfo"
            )
            or {}
        )

    except Exception as exc:

        return Response(
            {
                "success": True,
                "provider": "QUICKBOOKS",
                "connected": True,
                "healthy": False,
                "error": str(exc),
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {
            "success": True,
            "provider": "QUICKBOOKS",
            "connected": True,
            "healthy": True,
            "integration_id": str(
                integration.id
            ),
            "company": {
                "realm_id": (
                    config.get(
                        "realm_id"
                    )
                ),
                "name": (
                    company_info.get(
                        "CompanyName"
                    )
                ),
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def quickbooks_accounts(request):

    profile = request.user.profile

    # ==========================================================
    # 1. PERMISSION CHECK
    # ==========================================================

    can_view = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not can_view:

        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "view integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 2. COMPANY CHECK
    # ==========================================================

    if not profile.company:

        return Response(
            {
                "success": False,
                "error": (
                    "Company is not assigned."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 3. FIND CONNECTED QUICKBOOKS INTEGRATION
    # ==========================================================

    try:

        integration = (
            CompanyIntegration.objects
            .select_related(
                "credential"
            )
            .get(
                company=profile.company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_QUICKBOOKS
                ),
                is_connected=True,
                is_active=True,
            )
        )

    except CompanyIntegration.DoesNotExist:

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks is not connected."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 4. GET VALID ACCESS TOKEN
    # ==========================================================

    try:

        token_result = (
            get_valid_quickbooks_access_token(
                integration=integration,
            )
        )

        config = token_result[
            "config"
        ]

        access_token = token_result[
            "access_token"
        ]

        realm_id = config.get(
            "realm_id"
        )

        if not realm_id:

            return Response(
                {
                    "success": False,
                    "error": (
                        "QuickBooks realm ID "
                        "is missing."
                    ),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        # ======================================================
        # 5. FETCH EXPENSE ACCOUNTS
        # ======================================================

        client = QuickBooksClient()

        accounts = (
            client.get_expense_accounts(
                realm_id=realm_id,
                access_token=access_token,
            )
        )

    except QuickBooksIntegrationError as exc:

        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except Exception as exc:

        logger.exception(
            "Unexpected QuickBooks accounts error."
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to fetch QuickBooks "
                    "expense accounts."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 6. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,
            "provider": "QUICKBOOKS",
            "count": len(
                accounts
            ),
            "accounts": accounts,
        },
        status=status.HTTP_200_OK,
    )
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def quickbooks_category_mappings(request):

    profile = request.user.profile

    # ==========================================================
    # PERMISSION
    # ==========================================================

    can_view = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not can_view:
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "view integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # INTEGRATION
    # ==========================================================

    integration = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_QUICKBOOKS
            ),
            is_connected=True,
        )
        .first()
    )

    if not integration:

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks is not connected."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # MAPPINGS
    # ==========================================================

    mappings = (
        QuickBooksCategoryMapping.objects
        .filter(
            integration=integration,
        )
        .order_by(
            "zepex_category"
        )
    )

    serializer = (
        QuickBooksCategoryMappingSerializer(
            mappings,
            many=True,
        )
    )

    return Response(
        {
            "success": True,
            "provider": "QUICKBOOKS",
            "count": mappings.count(),
            "mappings": serializer.data,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_quickbooks_category_mapping(request):

    profile = request.user.profile

    # ==========================================================
    # 1. PERMISSION
    # ==========================================================

    if not (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    ):
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "manage integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 2. COMPANY CHECK
    # ==========================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 3. FIND QUICKBOOKS INTEGRATION
    # ==========================================================

    integration = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_QUICKBOOKS
            ),
            is_connected=True,
            is_active=True,
        )
        .first()
    )

    if not integration:
        return Response(
            {
                "success": False,
                "error": "QuickBooks is not connected.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 4. REQUEST DATA
    # ==========================================================

    zepex_category = (
        request.data.get("zepex_category")
        or ""
    ).strip().lower()

    account_id = (
        request.data.get(
            "quickbooks_account_id"
        )
        or ""
    ).strip()

    if not zepex_category:
        return Response(
            {
                "success": False,
                "error": "zepex_category is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not account_id:
        return Response(
            {
                "success": False,
                "error": (
                    "quickbooks_account_id "
                    "is required."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 5. FETCH QUICKBOOKS EXPENSE ACCOUNTS
    # ==========================================================

    try:

        token_result = (
            get_valid_quickbooks_access_token(
                integration=integration,
            )
        )

        config = token_result["config"]

        realm_id = config.get("realm_id")

        if not realm_id:
            return Response(
                {
                    "success": False,
                    "error": (
                        "QuickBooks realm ID "
                        "is missing."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = QuickBooksClient()

        accounts = (
            client.get_expense_accounts(
                realm_id=realm_id,
                access_token=(
                    token_result[
                        "access_token"
                    ]
                ),
            )
        )

    except QuickBooksIntegrationError as exc:

        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except Exception:
        logger.exception(
            "Unable to fetch QuickBooks accounts "
            "while saving category mapping."
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to fetch QuickBooks "
                    "expense accounts."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 6. FIND SELECTED ACCOUNT
    #
    # get_expense_accounts() already returns:
    #
    # {
    #     "id": "...",
    #     "name": "...",
    #     "account_type": "...",
    #     ...
    # }
    # ==========================================================

    selected_account = next(
        (
            account
            for account in accounts
            if str(
                account.get("id")
            ) == account_id
        ),
        None,
    )

    if not selected_account:
        return Response(
            {
                "success": False,
                "error": (
                    "Selected QuickBooks expense "
                    "account was not found."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 7. SAVE / UPDATE MAPPING
    # ==========================================================

    mapping, created = (
        QuickBooksCategoryMapping.objects
        .update_or_create(
            integration=integration,
            zepex_category=zepex_category,
            defaults={
                "quickbooks_account_id": str(
                    selected_account.get("id")
                ),
                "quickbooks_account_name": (
                    selected_account.get("name")
                    or ""
                ),
                "quickbooks_account_type": (
                    selected_account.get(
                        "account_type"
                    )
                ),
                "quickbooks_account_sub_type": (
                    selected_account.get(
                        "account_sub_type"
                    )
                ),
                "is_active": True,
            },
        )
    )

    # ==========================================================
    # 8. RESPONSE
    # ==========================================================

    serializer = (
        QuickBooksCategoryMappingSerializer(
            mapping
        )
    )

    return Response(
        {
            "success": True,
            "message": (
                "QuickBooks category mapping "
                "saved successfully."
            ),
            "created": created,
            "mapping": serializer.data,
        },
        status=(
            status.HTTP_201_CREATED
            if created
            else status.HTTP_200_OK
        ),
    )

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_quickbooks_category_mapping(
    request,
    mapping_id,
):

    profile = request.user.profile

    if not (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "manage integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    try:

        mapping = (
            QuickBooksCategoryMapping.objects
            .select_related(
                "integration",
            )
            .get(
                id=mapping_id,
                integration__company=(
                    profile.company
                ),
                integration__provider=(
                    CompanyIntegration
                    .PROVIDER_QUICKBOOKS
                ),
            )
        )

    except QuickBooksCategoryMapping.DoesNotExist:

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks category "
                    "mapping not found."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    mapping.delete()

    return Response(
        {
            "success": True,
            "message": (
                "QuickBooks category mapping "
                "deleted successfully."
            ),
        },
        status=status.HTTP_200_OK,
    )
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def export_report_quickbooks(
    request,
    report_id,
):

    profile = request.user.profile

    # ==========================================================
    # 1. COMPANY
    # ==========================================================

    if not profile.company:

        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. PERMISSION
    # ==========================================================

    allowed = (
        profile.role
        in (
            "COMPANY_ADMIN",
            "ACCOUNTS",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not allowed:

        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "export reports to QuickBooks."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 3. REPORT VALIDATION
    # ==========================================================

    try:

        report = ExpenseReport.objects.get(
            id=report_id,
            company=profile.company,
        )

    except ExpenseReport.DoesNotExist:

        return Response(
            {
                "success": False,
                "error": "Expense report not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # ==========================================================
    # 4. REPORT MUST BE PAID
    # ==========================================================

    if (
        report.status
        != ExpenseReport.STATUS_PAID
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "Only PAID expense reports "
                    "can be exported to QuickBooks."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 5. QUICKBOOKS CONNECTION
    # ==========================================================

    integration = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_QUICKBOOKS
            ),
            is_connected=True,
            is_active=True,
        )
        .first()
    )

    if not integration:

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks is not connected."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 6. PREVENT SUCCESSFUL DUPLICATE
    # ==========================================================

    successful_export = (
        QuickBooksExportRecord.objects
        .filter(
            integration=integration,
            report=report,
            status=(
                QuickBooksExportRecord
                .STATUS_SUCCESS
            ),
        )
        .first()
    )

    if successful_export:

        return Response(
            {
                "success": False,
                "error": (
                    "This expense report has already "
                    "been exported to QuickBooks."
                ),
                "quickbooks_transaction_id": (
                    successful_export
                    .quickbooks_transaction_id
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 7. PREVENT MULTIPLE RUNNING JOBS
    # ==========================================================

    pending_export = (
        QuickBooksExportRecord.objects
        .filter(
            integration=integration,
            report=report,
            status=(
                QuickBooksExportRecord
                .STATUS_PENDING
            ),
        )
        .first()
    )

    if pending_export:

        # ======================================================
        # ACTIVE PENDING JOB
        # ======================================================

        if not is_quickbooks_export_stale(
            pending_export
        ):

            return Response(
                {
                    "success": True,
                    "message": (
                        "QuickBooks export is already "
                        "being processed."
                    ),
                    "report_id": str(
                        report.id
                    ),
                    "export_status": "PENDING",
                    "export_record_id": str(
                        pending_export.id
                    ),
                },
                status=status.HTTP_202_ACCEPTED,
            )

        # ======================================================
        # STALE PENDING JOB
        # ======================================================

        logger.warning(
            (
                "Stale QuickBooks export found. "
                "It will be queued again. "
                "export_record=%s report=%s"
            ),
            pending_export.id,
            report.id,
        )

        export_record = pending_export

    else:

    # ======================================================
    # CREATE / REUSE EXPORT RECORD
    # ======================================================

        external_reference = (
        f"ZEP-RPT-{report.id}"
    )

    export_record, _ = (
        QuickBooksExportRecord.objects
        .get_or_create(
            integration=integration,
            report=report,
            defaults={
                "external_reference": (
                    external_reference
                ),
                "status": (
                    QuickBooksExportRecord
                    .STATUS_PENDING
                ),
                "exported_amount": (
                    report.total_amount
                ),
            },
        )
    )
    # A previous FAILED record can be reused.

    export_record.status = (
        QuickBooksExportRecord
        .STATUS_PENDING
    )

    export_record.error_message = None

    export_record.save(
        update_fields=[
            "status",
            "error_message",
            "updated_at",
        ]
    )

    # ==========================================================
    # 9. QUEUE CELERY TASK
    # ==========================================================

    try:

        task = (
            export_report_to_quickbooks_task
            .delay(
                str(report.id),
                str(profile.company.id),
            )
        )
        create_integration_audit_log(
    company=profile.company,
    integration=integration,
    provider="QUICKBOOKS",
    action="QUICKBOOKS_EXPORT_QUEUED",
    action_by=profile,
    message=(
        "Expense report queued for "
        "QuickBooks export."
    ),
    metadata={
        "report_id": str(
            report.id
        ),
        "export_record_id": str(
            export_record.id
        ),
        "task_id": str(
            task.id
        ),
        "amount": str(
            report.total_amount
        ),
    },
)
    except Exception:

        logger.exception(
            "Unable to queue QuickBooks export."
        )

        export_record.status = (
            QuickBooksExportRecord
            .STATUS_FAILED
        )

        export_record.error_message = (
            "Unable to queue QuickBooks export."
        )

        export_record.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to queue QuickBooks "
                    "export."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 10. IMMEDIATE RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,

            "message": (
                "QuickBooks export has been queued."
            ),

            "report_id": str(
                report.id
            ),

            "export_status": "PENDING",

            "export_record_id": str(
                export_record.id
            ),

            "task_id": str(
                task.id
            ),
        },
        status=status.HTTP_202_ACCEPTED,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def quickbooks_report_export_status(
    request,
    report_id,
):
    profile = request.user.profile

    # ==========================================================
    # COMPANY
    # ==========================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # PERMISSION
    # ==========================================================

    allowed = (
        profile.role
        in (
            "COMPANY_ADMIN",
            "ACCOUNTS",
        )
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not allowed:
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to view "
                    "QuickBooks export status."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # REPORT
    # ==========================================================

    try:
        report = ExpenseReport.objects.get(
            id=report_id,
            company=profile.company,
        )

    except ExpenseReport.DoesNotExist:
        return Response(
            {
                "success": False,
                "error": "Expense report not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # ==========================================================
    # QUICKBOOKS INTEGRATION
    # ==========================================================

    integration = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_QUICKBOOKS
            ),
        )
        .first()
    )

    if not integration:
        return Response(
            {
                "success": True,
                "report_id": str(report.id),
                "quickbooks_connected": False,
                "export_status": "NOT_EXPORTED",
                "export": None,
            },
            status=status.HTTP_200_OK,
        )

    # ==========================================================
    # EXPORT RECORD
    # ==========================================================

    export_record = (
        QuickBooksExportRecord.objects
        .filter(
            integration=integration,
            report=report,
        )
        .order_by(
            "-created_at"
        )
        .first()
    )

    if not export_record:
        return Response(
            {
                "success": True,
                "report_id": str(report.id),
                "report_status": report.status,
                "quickbooks_connected": (
                    integration.is_connected
                ),
                "export_status": "NOT_EXPORTED",
                "export": None,
            },
            status=status.HTTP_200_OK,
        )

    # ==========================================================
    # RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,

            "report_id": str(
                report.id
            ),

            "report_status": (
                report.status
            ),

            "quickbooks_connected": (
                integration.is_connected
            ),

            "export_status": (
                export_record.status
            ),

            "export": {
                "id": str(
                    export_record.id
                ),

                "external_reference": (
                    export_record.external_reference
                ),

                "quickbooks_transaction_id": (
                    export_record
                    .quickbooks_transaction_id
                ),

                "amount": (
                    str(
                        export_record.exported_amount
                    )
                    if (
                        export_record.exported_amount
                        is not None
                    )
                    else None
                ),

                "error_message": (
                    export_record.error_message
                ),

                "exported_at": (
                    export_record.exported_at
                ),

                "created_at": (
                    export_record.created_at
                ),
            },
        },
        status=status.HTTP_200_OK,
    )


# ==============================================================
# BAMBOOHR — CHANGE HISTORY
# ==============================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bamboohr_change_history(request):
    """
    Return individual changes made in ZepEx by BambooHR sync.

    Examples:

        Employee created
        Employee activated/deactivated
        Department changed
        Manager changed
        Employee details updated
        Department created

    Optional query params:

        resource_type=EMPLOYEE
        resource_type=DEPARTMENT

        change_type=CREATED
        change_type=UPDATED
        change_type=ACTIVATED
        change_type=DEACTIVATED
        change_type=MANAGER_CHANGED
        change_type=DEPARTMENT_CHANGED

        sync_log_id=<id>

        limit=50
    """

    profile = request.user.profile

    # ==========================================================
    # 1. COMPANY CHECK
    # ==========================================================

    if not profile.company:

        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. PERMISSION CHECK
    # ==========================================================

    can_view = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not can_view:

        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "view integration changes."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 3. FIND BAMBOOHR INTEGRATION
    # ==========================================================

    try:

        integration = (
            CompanyIntegration.objects
            .get(
                company=profile.company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_BAMBOOHR
                ),
            )
        )

    except CompanyIntegration.DoesNotExist:

        return Response(
            {
                "success": False,
                "error": (
                    "BambooHR integration "
                    "not found."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # ==========================================================
    # 4. READ FILTERS
    # ==========================================================

    resource_type = (
        request.query_params.get(
            "resource_type",
            "",
        )
        or ""
    ).strip().upper()

    change_type = (
        request.query_params.get(
            "change_type",
            "",
        )
        or ""
    ).strip().upper()

    sync_log_id = (
        request.query_params.get(
            "sync_log_id",
            "",
        )
        or ""
    ).strip()

    # ==========================================================
    # 5. VALIDATE RESOURCE TYPE
    # ==========================================================

    allowed_resource_types = {
        IntegrationChangeLog.RESOURCE_EMPLOYEE,
        IntegrationChangeLog.RESOURCE_DEPARTMENT,
    }

    if (
        resource_type
        and resource_type
        not in allowed_resource_types
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "Invalid resource_type. "
                    "Allowed values are: "
                    "EMPLOYEE, DEPARTMENT."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 6. VALIDATE CHANGE TYPE
    # ==========================================================

    allowed_change_types = {
        IntegrationChangeLog.CHANGE_CREATED,
        IntegrationChangeLog.CHANGE_UPDATED,
        IntegrationChangeLog.CHANGE_ACTIVATED,
        IntegrationChangeLog.CHANGE_DEACTIVATED,
        IntegrationChangeLog.CHANGE_MANAGER_CHANGED,
        IntegrationChangeLog.CHANGE_DEPARTMENT_CHANGED,
    }

    if (
        change_type
        and change_type
        not in allowed_change_types
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "Invalid change_type. "
                    "Allowed values are: "
                    "CREATED, UPDATED, ACTIVATED, "
                    "DEACTIVATED, MANAGER_CHANGED, "
                    "DEPARTMENT_CHANGED."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 7. LIMIT
    # ==========================================================

    try:

        limit = int(
            request.query_params.get(
                "limit",
                50,
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        limit = 50

    limit = max(
        1,
        min(
            limit,
            200,
        ),
    )

    # ==========================================================
    # 8. BASE QUERY
    # ==========================================================

    changes = (
        IntegrationChangeLog.objects
        .filter(
            integration=integration,
        )
        .select_related(
            "sync_log",
        )
    )

    # ==========================================================
    # 9. APPLY FILTERS
    # ==========================================================

    if resource_type:

        changes = changes.filter(
            resource_type=resource_type,
        )

    if change_type:

        changes = changes.filter(
            change_type=change_type,
        )

    if sync_log_id:

        changes = changes.filter(
            sync_log_id=sync_log_id,
        )

    # ==========================================================
    # 10. TOTAL BEFORE LIMIT
    # ==========================================================

    total = changes.count()

    # ==========================================================
    # 11. ORDER + LIMIT
    # ==========================================================

    changes = (
        changes
        .order_by(
            "-created_at",
        )[:limit]
    )

    # ==========================================================
    # 12. BUILD RESPONSE
    # ==========================================================

    results = []

    for change in changes:

        results.append(
            {
                "id": str(
                    change.id
                ),

                "resource_type": (
                    change.resource_type
                ),

                "external_resource_id": (
                    change.external_resource_id
                ),

                "resource_name": (
                    change.resource_name
                ),

                "change_type": (
                    change.change_type
                ),

                "field_name": (
                    change.field_name
                ),

                "old_value": (
                    change.old_value
                ),

                "new_value": (
                    change.new_value
                ),

                "details": (
                    change.details
                    or {}
                ),

                "sync_log_id": (
                    str(change.sync_log_id)
                    if change.sync_log_id
                    else None
                ),

                "created_at": (
                    change.created_at
                ),
            }
        )

    # ==========================================================
    # 13. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,

            "provider": "BAMBOOHR",

            "integration_id": str(
                integration.id
            ),

            "filters": {
                "resource_type": (
                    resource_type
                    or None
                ),

                "change_type": (
                    change_type
                    or None
                ),

                "sync_log_id": (
                    sync_log_id
                    or None
                ),

                "limit": limit,
            },

            "total": total,

            "count": len(
                results
            ),

            "results": results,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def quickbooks_export_history(request):

    profile = request.user.profile

    # ==========================================================
    # 1. COMPANY
    # ==========================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. PERMISSION
    # ==========================================================

    allowed = (
        profile.role
        in (
            "COMPANY_ADMIN",
            "ACCOUNTS",
        )
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not allowed:
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to view "
                    "QuickBooks export history."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 3. QUICKBOOKS INTEGRATION
    # ==========================================================

    integration = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_QUICKBOOKS
            ),
        )
        .first()
    )

    if not integration:
        return Response(
            {
                "success": True,
                "provider": "QUICKBOOKS",
                "connected": False,
                "count": 0,
                "results": [],
            },
            status=status.HTTP_200_OK,
        )

    # ==========================================================
    # 4. QUERY PARAMETERS
    # ==========================================================

    export_status = (
        request.query_params.get(
            "status"
        )
        or ""
    ).strip().upper()

    try:
        limit = int(
            request.query_params.get(
                "limit",
                20,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        limit = 20

    limit = max(
        1,
        min(
            limit,
            100,
        ),
    )

    # ==========================================================
    # 5. EXPORT RECORDS
    # ==========================================================

    exports = (
        QuickBooksExportRecord.objects
        .filter(
            integration=integration,
        )
        .select_related(
            "report",
            "report__employee",
            "report__employee__user",
            "report__department",
        )
        .order_by(
            "-created_at"
        )
    )

    # Optional status filter

    if export_status:

        valid_statuses = {
            QuickBooksExportRecord.STATUS_PENDING,
            QuickBooksExportRecord.STATUS_SUCCESS,
            QuickBooksExportRecord.STATUS_FAILED,
        }

        if export_status not in valid_statuses:

            return Response(
                {
                    "success": False,
                    "error": (
                        "Invalid export status. "
                        "Allowed values are "
                        "PENDING, SUCCESS and FAILED."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        exports = exports.filter(
            status=export_status,
        )

    exports = exports[:limit]

    # ==========================================================
    # 6. BUILD RESPONSE
    # ==========================================================

    results = []

    for export_record in exports:

        report = export_record.report

        employee = report.employee

        employee_name = (
            employee.user.get_full_name()
            or employee.user.email
        )

        results.append(
            {
                "id": str(
                    export_record.id
                ),

                "status": (
                    export_record.status
                ),

                "report": {
                    "id": str(
                        report.id
                    ),

                    "month": (
                        report.month
                    ),

                    "status": (
                        report.status
                    ),

                    "total_amount": str(
                        report.total_amount
                    ),

                    "employee": {
                        "id": str(
                            employee.id
                        ),

                        "name": (
                            employee_name
                        ),

                        "email": (
                            employee.user.email
                        ),
                    },

                    "department": (
                        report.department.name
                        if report.department
                        else None
                    ),
                },

                "external_reference": (
                    export_record.external_reference
                ),

                "quickbooks_transaction_id": (
                    export_record
                    .quickbooks_transaction_id
                ),

                "exported_amount": (
                    str(
                        export_record.exported_amount
                    )
                    if (
                        export_record.exported_amount
                        is not None
                    )
                    else None
                ),

                "error_message": (
                    export_record.error_message
                ),

                "exported_at": (
                    export_record.exported_at
                ),

                "created_at": (
                    export_record.created_at
                ),

                "updated_at": (
                    export_record.updated_at
                ),
            }
        )

    # ==========================================================
    # 7. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,

            "provider": "QUICKBOOKS",

            "connected": (
                integration.is_connected
            ),

            "count": len(
                results
            ),

            "results": results,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def disconnect_quickbooks(request):

    profile = request.user.profile

    # ==========================================================
    # 1. COMPANY
    # ==========================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. PERMISSION
    # ==========================================================

    if not (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    ):
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "manage integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 3. FIND QUICKBOOKS INTEGRATION
    # ==========================================================

    try:

        integration = (
            CompanyIntegration.objects
            .select_related(
                "credential"
            )
            .get(
                company=profile.company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_QUICKBOOKS
                ),
            )
        )

    except CompanyIntegration.DoesNotExist:

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks integration "
                    "was not found."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # ==========================================================
    # 4. REMOVE STORED OAUTH CREDENTIALS
    # ==========================================================

    try:
        credential = integration.credential

    except Exception:
        credential = None

    if credential:
        credential.delete()

    # ==========================================================
    # 5. MARK INTEGRATION DISCONNECTED
    # ==========================================================

    integration.is_connected = False
    integration.is_active = False

    integration.last_sync_status = None
    integration.last_sync_error = None

    integration.save(
        update_fields=[
            "is_connected",
            "is_active",
            "last_sync_status",
            "last_sync_error",
            "updated_at",
        ]
    )
    create_integration_audit_log(
    company=profile.company,
    integration=integration,
    provider="QUICKBOOKS",
    action="QUICKBOOKS_DISCONNECTED",
    action_by=profile,
    message="QuickBooks disconnected successfully.",
    metadata={
        "integration_id": str(
            integration.id
        ),
    },
)
    # ==========================================================
    # 6. IMPORTANT
    #
    # DO NOT DELETE:
    #
    # - QuickBooksCategoryMapping
    # - QuickBooksExportRecord
    # - ExpenseReport
    # - ExpenseReceipt
    # - ExpenseLineItem
    # - QuickBooks transaction IDs
    #
    # Historical accounting data must remain available.
    # ==========================================================

    return Response(
        {
            "success": True,
            "message": (
                "QuickBooks disconnected successfully."
            ),
            "provider": "QUICKBOOKS",
            "connected": False,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def retry_quickbooks_export(
    request,
    report_id,
):
    profile = request.user.profile

    # ==========================================================
    # 1. COMPANY
    # ==========================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. PERMISSION
    # ==========================================================

    allowed = (
        profile.role
        in (
            "COMPANY_ADMIN",
            "ACCOUNTS",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not allowed:
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to retry "
                    "QuickBooks exports."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 3. REPORT
    # ==========================================================

    try:
        report = (
            ExpenseReport.objects
            .get(
                id=report_id,
                company=profile.company,
            )
        )

    except ExpenseReport.DoesNotExist:
        return Response(
            {
                "success": False,
                "error": "Expense report not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # ==========================================================
    # 4. REPORT MUST STILL BE PAID
    # ==========================================================

    if (
        report.status
        != ExpenseReport.STATUS_PAID
    ):
        return Response(
            {
                "success": False,
                "error": (
                    "Only PAID expense reports "
                    "can be exported to QuickBooks."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 5. QUICKBOOKS INTEGRATION
    # ==========================================================

    try:
        integration = (
            CompanyIntegration.objects
            .get(
                company=profile.company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_QUICKBOOKS
                ),
                is_connected=True,
                is_active=True,
            )
        )

    except CompanyIntegration.DoesNotExist:
        return Response(
            {
                "success": False,
                "error": "QuickBooks is not connected.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 6. FIND EXISTING EXPORT RECORD
    # ==========================================================

    export_record = (
        QuickBooksExportRecord.objects
        .filter(
            integration=integration,
            report=report,
        )
        .first()
    )

    # ==========================================================
    # 7. NO EXPORT RECORD
    # ==========================================================
    #
    # IMPORTANT:
    #
    # An export record may not exist when the previous export
    # failed BEFORE export-record creation.
    #
    # Example:
    #
    #   PAID
    #     ↓
    #   Celery starts
    #     ↓
    #   validate category mappings
    #     ↓
    #   missing "gratuity"
    #     ↓
    #   QuickBooksExportError
    #
    # Because validation happens before export-record creation,
    # there is nothing for the old retry endpoint to retry.
    #
    # Now that the configuration has been corrected, simply
    # queue the export service again.
    # ==========================================================

    if not export_record:

        try:
            task = (
                export_report_to_quickbooks_task
                .delay(
                    str(report.id),
                    str(profile.company.id),
                )
            )

            create_integration_audit_log(
                company=profile.company,
                integration=integration,
                provider="QUICKBOOKS",
                action="QUICKBOOKS_EXPORT_RETRIED",
                action_by=profile,
                message=(
                    "QuickBooks export retry queued "
                    "after a pre-validation failure."
                ),
                metadata={
                    "report_id": str(
                        report.id
                    ),
                    "export_record_id": None,
                    "task_id": str(
                        task.id
                    ),
                    "amount": str(
                        report.total_amount
                    ),
                    "retry_reason": (
                        "NO_EXPORT_RECORD"
                    ),
                },
            )

        except Exception as exc:

            logger.exception(
                (
                    "Unable to queue QuickBooks retry. "
                    "report=%s"
                ),
                report.id,
            )

            return Response(
                {
                    "success": False,
                    "error": (
                        "Unable to queue QuickBooks "
                        "retry."
                    ),
                    "detail": str(exc),
                },
                status=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        return Response(
            {
                "success": True,
                "message": (
                    "QuickBooks export retry "
                    "has been queued."
                ),
                "report_id": str(
                    report.id
                ),
                "export_status": "QUEUED",
                "export_record_id": None,
                "task_id": str(
                    task.id
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )

    # ==========================================================
    # 8. SUCCESS CANNOT BE RETRIED
    # ==========================================================

    if (
        export_record.status
        == QuickBooksExportRecord.STATUS_SUCCESS
    ):
        return Response(
            {
                "success": False,
                "error": (
                    "This report has already been "
                    "successfully exported to QuickBooks."
                ),
                "report_id": str(
                    report.id
                ),
                "export_status": (
                    QuickBooksExportRecord.STATUS_SUCCESS
                ),
                "export_record_id": str(
                    export_record.id
                ),
                "quickbooks_transaction_id": (
                    export_record
                    .quickbooks_transaction_id
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 9. PROCESSING CANNOT BE RETRIED
    # ==========================================================

    if (
        export_record.status
        == QuickBooksExportRecord.STATUS_PROCESSING
    ):
        return Response(
            {
                "success": True,
                "message": (
                    "QuickBooks export is currently "
                    "being processed."
                ),
                "report_id": str(
                    report.id
                ),
                "export_status": "PROCESSING",
                "export_record_id": str(
                    export_record.id
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )

    # ==========================================================
    # 10. HANDLE PENDING
    # ==========================================================

    if (
        export_record.status
        == QuickBooksExportRecord.STATUS_PENDING
    ):

        # ------------------------------------------------------
        # Recent PENDING:
        # Don't create another Celery task.
        # ------------------------------------------------------

        if not is_quickbooks_export_stale(
            export_record
        ):
            return Response(
                {
                    "success": True,
                    "message": (
                        "QuickBooks export is already "
                        "being processed."
                    ),
                    "report_id": str(
                        report.id
                    ),
                    "export_status": "PENDING",
                    "export_record_id": str(
                        export_record.id
                    ),
                },
                status=status.HTTP_202_ACCEPTED,
            )

        # ------------------------------------------------------
        # Stale PENDING:
        # It can safely be queued again.
        # ------------------------------------------------------

        logger.warning(
            (
                "Retrying stale QuickBooks export. "
                "export_record=%s report=%s"
            ),
            export_record.id,
            report.id,
        )

    # ==========================================================
    # 11. FAILED OR STALE PENDING -> RESET TO PENDING
    # ==========================================================

    export_record.status = (
        QuickBooksExportRecord.STATUS_PENDING
    )

    export_record.error_message = None

    export_record.save(
        update_fields=[
            "status",
            "error_message",
            "updated_at",
        ]
    )

    # ==========================================================
    # 12. QUEUE CELERY TASK
    # ==========================================================

    try:
        task = (
            export_report_to_quickbooks_task
            .delay(
                str(report.id),
                str(profile.company.id),
            )
        )

        create_integration_audit_log(
            company=profile.company,
            integration=integration,
            provider="QUICKBOOKS",
            action="QUICKBOOKS_EXPORT_RETRIED",
            action_by=profile,
            message=(
                "QuickBooks export retry queued."
            ),
            metadata={
                "report_id": str(
                    report.id
                ),
                "export_record_id": str(
                    export_record.id
                ),
                "task_id": str(
                    task.id
                ),
                "amount": str(
                    report.total_amount
                ),
                "previous_status": (
                    export_record.status
                ),
            },
        )

    except Exception:

        logger.exception(
            (
                "Unable to queue QuickBooks retry. "
                "report=%s"
            ),
            report.id,
        )

        export_record.status = (
            QuickBooksExportRecord.STATUS_FAILED
        )

        export_record.error_message = (
            "Unable to queue QuickBooks retry."
        )

        export_record.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to queue QuickBooks "
                    "retry."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 13. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,
            "message": (
                "QuickBooks export retry "
                "has been queued."
            ),
            "report_id": str(
                report.id
            ),
            "export_status": "PENDING",
            "export_record_id": str(
                export_record.id
            ),
            "task_id": str(
                task.id
            ),
        },
        status=status.HTTP_202_ACCEPTED,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integration_activity(request):

    profile = request.user.profile

    # ==========================================================
    # 1. COMPANY
    # ==========================================================

    if not profile.company:

        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. PERMISSION
    # ==========================================================

    allowed = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not allowed:

        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to view "
                    "integration activity."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 3. QUERY PARAMETERS
    # ==========================================================

    provider = (
        request.query_params.get(
            "provider",
            "",
        )
        or ""
    ).strip().upper()

    action = (
        request.query_params.get(
            "action",
            "",
        )
        or ""
    ).strip().upper()

    try:

        limit = int(
            request.query_params.get(
                "limit",
                50,
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        limit = 50

    limit = max(
        1,
        min(
            limit,
            100,
        ),
    )

    # ==========================================================
    # 4. INTEGRATION ACTIONS
    # ==========================================================

    integration_actions = [
        # BambooHR
        "BAMBOOHR_CONNECTED",
        "BAMBOOHR_CONNECTION_FAILED",
        "BAMBOOHR_SYNC_STARTED",
        "BAMBOOHR_SYNC_COMPLETED",
        "BAMBOOHR_SYNC_FAILED",
        "BAMBOOHR_DISCONNECTED",

        # QuickBooks
        "QUICKBOOKS_CONNECTED",
        "QUICKBOOKS_CONNECTION_FAILED",
        "QUICKBOOKS_DISCONNECTED",

        "QUICKBOOKS_MAPPING_CREATED",
        "QUICKBOOKS_MAPPING_UPDATED",
        "QUICKBOOKS_MAPPING_DELETED",

        "QUICKBOOKS_EXPORT_QUEUED",
        "QUICKBOOKS_EXPORT_STARTED",
        "QUICKBOOKS_EXPORT_SUCCESS",
        "QUICKBOOKS_EXPORT_FAILED",
        "QUICKBOOKS_EXPORT_RETRIED",
    ]

    # ==========================================================
    # 5. BASE QUERY
    # ==========================================================

    logs = (
        AuditLog.objects
        .filter(
            company=profile.company,
            action__in=integration_actions,
        )
        .select_related(
            "action_by",
            "action_by__user",
        )
        .order_by(
            "-created_at"
        )
    )

    # ==========================================================
    # 6. PROVIDER FILTER
    # ==========================================================

    if provider:

        if provider not in (
            "BAMBOOHR",
            "QUICKBOOKS",
        ):

            return Response(
                {
                    "success": False,
                    "error": (
                        "Invalid provider. "
                        "Allowed values are "
                        "BAMBOOHR and QUICKBOOKS."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        logs = logs.filter(
            metadata__provider=provider,
        )

    # ==========================================================
    # 7. ACTION FILTER
    # ==========================================================

    if action:

        if action not in integration_actions:

            return Response(
                {
                    "success": False,
                    "error": (
                        "Invalid integration action."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        logs = logs.filter(
            action=action,
        )

    # ==========================================================
    # 8. LIMIT
    # ==========================================================

    logs = logs[:limit]

    # ==========================================================
    # 9. RESPONSE BUILD
    # ==========================================================

    results = []

    for log in logs:

        action_by = None

        if log.action_by:

            action_by = {
                "id": str(
                    log.action_by.id
                ),
                "email": (
                    log.action_by.user.email
                    if log.action_by.user
                    else None
                ),
                "name": (
                    log.action_by.user.get_full_name()
                    if (
                        log.action_by.user
                        and log.action_by.user.get_full_name()
                    )
                    else (
                        log.action_by.user.email
                        if log.action_by.user
                        else None
                    )
                ),
            }

        provider_name = (
            log.metadata.get(
                "provider"
            )
            if isinstance(
                log.metadata,
                dict,
            )
            else None
        )

        results.append(
            {
                "id": str(
                    log.id
                ),

                "provider": (
                    provider_name
                ),

                "action": (
                    log.action
                ),

                "action_label": (
                    log.get_action_display()
                ),

                "message": (
                    log.message
                ),

                "action_by": (
                    action_by
                ),

                "metadata": (
                    log.metadata
                    if isinstance(
                        log.metadata,
                        dict,
                    )
                    else {}
                ),

                "created_at": (
                    log.created_at
                ),
            }
        )

    # ==========================================================
    # 10. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,
            "count": len(
                results
            ),
            "filters": {
                "provider": (
                    provider
                    or None
                ),
                "action": (
                    action
                    or None
                ),
                "limit": limit,
            },
            "results": results,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integration_dashboard_summary(request):

    profile = request.user.profile

    # ==========================================================
    # 1. COMPANY
    # ==========================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 2. PERMISSION
    # ==========================================================

    allowed = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not allowed:
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to view "
                    "integration dashboard."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 3. BAMBOOHR
    # ==========================================================

    bamboohr = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_BAMBOOHR
            ),
        )
        .first()
    )

    bamboohr_data = {
        "provider": "BAMBOOHR",
        "connected": False,
        "active": False,
        "last_synced_at": None,
        "last_sync_status": None,
        "last_sync_error": None,
        "syncs": {
            "total": 0,
            "success": 0,
            "failed": 0,
        },
    }

    if bamboohr:

        bamboohr_logs = (
            IntegrationSyncLog.objects
            .filter(
                integration=bamboohr,
            )
        )

        bamboohr_data = {
            "provider": "BAMBOOHR",

            "connected": (
                bamboohr.is_connected
            ),

            "active": (
                bamboohr.is_active
            ),

            "last_synced_at": (
                bamboohr.last_synced_at
            ),

            "last_sync_status": (
                bamboohr.last_sync_status
            ),

            "last_sync_error": (
                bamboohr.last_sync_error
            ),

            "syncs": {
                "total": (
                    bamboohr_logs.count()
                ),

                "success": (
                    bamboohr_logs.filter(
                        status=(
                            IntegrationSyncLog
                            .STATUS_SUCCESS
                        )
                    ).count()
                ),

                "failed": (
                    bamboohr_logs.filter(
                        status=(
                            IntegrationSyncLog
                            .STATUS_FAILED
                        )
                    ).count()
                ),
            },
        }

    # ==========================================================
    # 4. QUICKBOOKS
    # ==========================================================

    quickbooks = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_QUICKBOOKS
            ),
        )
        .first()
    )

    quickbooks_data = {
        "provider": "QUICKBOOKS",
        "connected": False,
        "active": False,
        "exports": {
            "total": 0,
            "pending": 0,
            "success": 0,
            "failed": 0,
        },
        "last_export_at": None,
    }

    if quickbooks:

        export_records = (
            QuickBooksExportRecord.objects
            .filter(
                integration=quickbooks,
            )
        )

        last_success_export = (
            export_records
            .filter(
                status=(
                    QuickBooksExportRecord
                    .STATUS_SUCCESS
                ),
            )
            .order_by(
                "-exported_at"
            )
            .first()
        )

        quickbooks_data = {
            "provider": "QUICKBOOKS",

            "connected": (
                quickbooks.is_connected
            ),

            "active": (
                quickbooks.is_active
            ),

            "exports": {
                "total": (
                    export_records.count()
                ),

                "pending": (
                    export_records.filter(
                        status=(
                            QuickBooksExportRecord
                            .STATUS_PENDING
                        )
                    ).count()
                ),

                "success": (
                    export_records.filter(
                        status=(
                            QuickBooksExportRecord
                            .STATUS_SUCCESS
                        )
                    ).count()
                ),

                "failed": (
                    export_records.filter(
                        status=(
                            QuickBooksExportRecord
                            .STATUS_FAILED
                        )
                    ).count()
                ),
            },

            "last_export_at": (
                last_success_export.exported_at
                if last_success_export
                else None
            ),
        }

    # ==========================================================
    # 5. RECENT INTEGRATION ACTIVITY
    # ==========================================================

    integration_actions = [
        "BAMBOOHR_CONNECTED",
        "BAMBOOHR_CONNECTION_FAILED",
        "BAMBOOHR_SYNC_STARTED",
        "BAMBOOHR_SYNC_COMPLETED",
        "BAMBOOHR_SYNC_FAILED",
        "BAMBOOHR_DISCONNECTED",

        "QUICKBOOKS_CONNECTED",
        "QUICKBOOKS_CONNECTION_FAILED",
        "QUICKBOOKS_DISCONNECTED",

        "QUICKBOOKS_MAPPING_CREATED",
        "QUICKBOOKS_MAPPING_UPDATED",
        "QUICKBOOKS_MAPPING_DELETED",

        "QUICKBOOKS_EXPORT_QUEUED",
        "QUICKBOOKS_EXPORT_STARTED",
        "QUICKBOOKS_EXPORT_SUCCESS",
        "QUICKBOOKS_EXPORT_FAILED",
        "QUICKBOOKS_EXPORT_RETRIED",
    ]

    recent_logs = (
        AuditLog.objects
        .filter(
            company=profile.company,
            action__in=integration_actions,
        )
        .select_related(
            "action_by",
            "action_by__user",
        )
        .order_by(
            "-created_at"
        )[:10]
    )

    recent_activity = []

    for log in recent_logs:

        action_by = None

        if log.action_by:

            action_by = {
                "id": str(
                    log.action_by.id
                ),
                "email": (
                    log.action_by.user.email
                    if log.action_by.user
                    else None
                ),
            }

        metadata = (
            log.metadata
            if isinstance(
                log.metadata,
                dict,
            )
            else {}
        )

        recent_activity.append(
            {
                "id": str(
                    log.id
                ),

                "provider": (
                    metadata.get(
                        "provider"
                    )
                ),

                "action": (
                    log.action
                ),

                "action_label": (
                    log.get_action_display()
                ),

                "message": (
                    log.message
                ),

                "action_by": (
                    action_by
                ),

                "created_at": (
                    log.created_at
                ),
            }
        )

    # ==========================================================
    # 6. SUMMARY
    # ==========================================================

    connected_count = sum(
        [
            1
            if bamboohr_data[
                "connected"
            ]
            else 0,

            1
            if quickbooks_data[
                "connected"
            ]
            else 0,
        ]
    )

    # ==========================================================
    # 7. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,

            "summary": {
                "supported_integrations": 5,

                "configured_integrations": (
                    CompanyIntegration.objects
                    .filter(
                        company=profile.company,
                    )
                    .count()
                ),

                "connected_integrations": (
                    connected_count
                ),
            },

            "integrations": {
                "bamboohr": (
                    bamboohr_data
                ),

                "quickbooks": (
                    quickbooks_data
                ),
            },

            "recent_activity": (
                recent_activity
            ),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def quickbooks_payment_accounts(request):

    profile = request.user.profile

    # ==========================================================
    # 1. PERMISSION
    # ==========================================================

    can_view = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not can_view:
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "view integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 2. COMPANY
    # ==========================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 3. QUICKBOOKS INTEGRATION
    # ==========================================================

    try:
        integration = (
            CompanyIntegration.objects
            .select_related("credential")
            .get(
                company=profile.company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_QUICKBOOKS
                ),
                is_connected=True,
                is_active=True,
            )
        )

    except CompanyIntegration.DoesNotExist:
        return Response(
            {
                "success": False,
                "error": "QuickBooks is not connected.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 4. FETCH PAYMENT ACCOUNTS
    # ==========================================================

    try:

        token_result = (
            get_valid_quickbooks_access_token(
                integration=integration,
            )
        )

        config = token_result["config"]

        realm_id = config.get("realm_id")

        if not realm_id:
            return Response(
                {
                    "success": False,
                    "error": (
                        "QuickBooks realm ID "
                        "is missing."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = QuickBooksClient()

        accounts = (
            client.get_payment_accounts(
                realm_id=realm_id,
                access_token=(
                    token_result["access_token"]
                ),
            )
        )

    except QuickBooksIntegrationError as exc:
        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except Exception:
        logger.exception(
            "Unable to fetch QuickBooks payment accounts."
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to fetch QuickBooks "
                    "payment accounts."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 5. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,
            "provider": "QUICKBOOKS",

            "selected_account": {
                "id": (
                    integration
                    .quickbooks_payment_account_id
                ),
                "name": (
                    integration
                    .quickbooks_payment_account_name
                ),
                "account_type": (
                    integration
                    .quickbooks_payment_account_type
                ),
            },

            "count": len(accounts),

            "accounts": accounts,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_quickbooks_payment_account(request):

    profile = request.user.profile

    # ==========================================================
    # 1. PERMISSION
    # ==========================================================

    if not (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    ):
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "manage integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 2. COMPANY
    # ==========================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 3. QUICKBOOKS INTEGRATION
    # ==========================================================

    try:
        integration = (
            CompanyIntegration.objects
            .select_related("credential")
            .get(
                company=profile.company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_QUICKBOOKS
                ),
                is_connected=True,
                is_active=True,
            )
        )

    except CompanyIntegration.DoesNotExist:
        return Response(
            {
                "success": False,
                "error": "QuickBooks is not connected.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 4. REQUEST DATA
    # ==========================================================

    account_id = (
        request.data.get(
            "quickbooks_account_id"
        )
        or ""
    ).strip()

    if not account_id:
        return Response(
            {
                "success": False,
                "error": (
                    "quickbooks_account_id "
                    "is required."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 5. FETCH VALID QUICKBOOKS PAYMENT ACCOUNTS
    # ==========================================================

    try:

        token_result = (
            get_valid_quickbooks_access_token(
                integration=integration,
            )
        )

        config = token_result["config"]

        realm_id = config.get("realm_id")

        if not realm_id:
            return Response(
                {
                    "success": False,
                    "error": (
                        "QuickBooks realm ID "
                        "is missing."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = QuickBooksClient()

        accounts = (
            client.get_payment_accounts(
                realm_id=realm_id,
                access_token=(
                    token_result["access_token"]
                ),
            )
        )

    except QuickBooksIntegrationError as exc:
        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except Exception:
        logger.exception(
            "Unable to validate QuickBooks payment account."
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to validate QuickBooks "
                    "payment account."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 6. FIND SELECTED ACCOUNT
    # ==========================================================

    selected_account = next(
        (
            account
            for account in accounts
            if str(
                account.get("id")
            ) == account_id
        ),
        None,
    )

    if not selected_account:
        return Response(
            {
                "success": False,
                "error": (
                    "Selected QuickBooks payment "
                    "account was not found."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 7. SAVE
    # ==========================================================

    integration.quickbooks_payment_account_id = str(
        selected_account.get("id")
    )

    integration.quickbooks_payment_account_name = (
        selected_account.get("name")
        or ""
    )

    integration.quickbooks_payment_account_type = (
        selected_account.get("account_type")
    )

    integration.save(
        update_fields=[
            "quickbooks_payment_account_id",
            "quickbooks_payment_account_name",
            "quickbooks_payment_account_type",
            "updated_at",
        ]
    )

    # ==========================================================
    # 8. AUDIT LOG
    # ==========================================================

    create_integration_audit_log(
        company=profile.company,
        integration=integration,
        provider="QUICKBOOKS",
        action="QUICKBOOKS_PAYMENT_ACCOUNT_UPDATED",
        action_by=profile,
        message=(
            "QuickBooks payment account updated."
        ),
        metadata={
            "quickbooks_account_id": (
                integration
                .quickbooks_payment_account_id
            ),
            "quickbooks_account_name": (
                integration
                .quickbooks_payment_account_name
            ),
            "quickbooks_account_type": (
                integration
                .quickbooks_payment_account_type
            ),
        },
    )

    # ==========================================================
    # 9. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,
            "message": (
                "QuickBooks payment account "
                "saved successfully."
            ),
            "provider": "QUICKBOOKS",
            "payment_account": {
                "id": (
                    integration
                    .quickbooks_payment_account_id
                ),
                "name": (
                    integration
                    .quickbooks_payment_account_name
                ),
                "account_type": (
                    integration
                    .quickbooks_payment_account_type
                ),
            },
        },
        status=status.HTTP_200_OK,
    )

# ==========================================================
# QUICKBOOKS — INTEGRATION SETTINGS
# ==========================================================


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def quickbooks_settings(request):
    """
    Get or update company-level QuickBooks settings.

    GET:
        Return current QuickBooks configuration.

    PATCH:
        Update QuickBooks automatic export setting.

    Only Company Admin can modify the setting.
    """

    profile = request.user.profile

    # ======================================================
    # 1. COMPANY VALIDATION
    # ======================================================

    if not profile.company:

        return Response(
            {
                "success": False,
                "error": (
                    "Your user is not assigned "
                    "to a company."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ======================================================
    # 2. FIND QUICKBOOKS INTEGRATION
    # ======================================================

    try:

        integration = (
            CompanyIntegration.objects
            .get(
                company=profile.company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_QUICKBOOKS
                ),
            )
        )

    except CompanyIntegration.DoesNotExist:

        return Response(
            {
                "success": False,
                "error": (
                    "QuickBooks integration "
                    "is not configured."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # ======================================================
    # 3. GET SETTINGS
    # ======================================================

    if request.method == "GET":

        return Response(
            {
                "success": True,

                "quickbooks": {
                    "is_connected": (
                        integration.is_connected
                    ),

                    "is_active": (
                        integration.is_active
                    ),

                    "auto_export": (
                        integration.quickbooks_auto_export
                    ),

                    "payment_account": {
                        "id": (
                            integration
                            .quickbooks_payment_account_id
                        ),
                        "name": (
                            integration
                            .quickbooks_payment_account_name
                        ),
                        "type": (
                            integration
                            .quickbooks_payment_account_type
                        ),
                    },
                },
            },
            status=status.HTTP_200_OK,
        )

    # ======================================================
    # 4. PATCH PERMISSION
    # ======================================================

    if profile.role != "COMPANY_ADMIN":

        return Response(
            {
                "success": False,
                "error": (
                    "Only Company Admin can update "
                    "QuickBooks settings."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ======================================================
    # 5. VALIDATE AUTO EXPORT
    # ======================================================

    if "auto_export" not in request.data:

        return Response(
            {
                "success": False,
                "error": (
                    "auto_export is required."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    auto_export = (
        request.data.get(
            "auto_export"
        )
    )

    if not isinstance(
        auto_export,
        bool,
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "auto_export must be "
                    "true or false."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ======================================================
    # 6. ENABLING AUTO EXPORT — SAFETY CHECKS
    # ======================================================

    if auto_export:

        # QuickBooks must be connected.

        if not integration.is_connected:

            return Response(
                {
                    "success": False,
                    "error": (
                        "Connect QuickBooks before "
                        "enabling automatic export."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Integration must be active.

        if not integration.is_active:

            return Response(
                {
                    "success": False,
                    "error": (
                        "QuickBooks integration is "
                        "currently inactive."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Payment account must be configured.

        if not (
            integration
            .quickbooks_payment_account_id
        ):

            return Response(
                {
                    "success": False,
                    "error": (
                        "Configure a QuickBooks payment "
                        "account before enabling "
                        "automatic export."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Payment account must be Bank / Credit Card.

        if (
            integration.quickbooks_payment_account_type
            not in (
                "Bank",
                "Credit Card",
            )
        ):

            return Response(
                {
                    "success": False,
                    "error": (
                        "The QuickBooks payment account "
                        "must be a Bank or Credit Card "
                        "account."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    # ======================================================
    # 7. SAVE SETTING
    # ======================================================

    previous_value = (
        integration.quickbooks_auto_export
    )

    integration.quickbooks_auto_export = (
        auto_export
    )

    integration.save(
        update_fields=[
            "quickbooks_auto_export",
            "updated_at",
        ]
    )

    # ======================================================
    # 8. RESPONSE
    # ======================================================

    return Response(
        {
            "success": True,

            "message": (
                "QuickBooks automatic export enabled."
                if auto_export
                else (
                    "QuickBooks automatic "
                    "export disabled."
                )
            ),

            "previous_auto_export": (
                previous_value
            ),

            "auto_export": (
                integration.quickbooks_auto_export
            ),

            "quickbooks_connected": (
                integration.is_connected
            ),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reconcile_quickbooks_report(
    request,
    report_id,
):
    """
    Verify an exported ZepEx expense report against
    the actual Purchase transaction in QuickBooks.

    The reconciliation compares the ZepEx export record
    with the real QuickBooks Purchase transaction.
    """

    # ==========================================================
    # 1. USER PROFILE
    # ==========================================================

    try:
        profile = request.user.profile

    except Exception:

        return Response(
            {
                "success": False,
                "error": "User profile not found.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 2. COMPANY CHECK
    # ==========================================================

    if not profile.company:

        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 3. PERMISSION
    # ==========================================================

    if not (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    ):

        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "manage integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ==========================================================
    # 4. RUN QUICKBOOKS RECONCILIATION
    # ==========================================================

    try:

        result = reconcile_quickbooks_export(
            report_id=report_id,
            company=profile.company,
        )

    # ==========================================================
    # 5. BUSINESS / VALIDATION ERROR
    # ==========================================================

    except QuickBooksExportError as exc:

        return Response(
            {
                "success": False,
                "error": str(exc),
                "report_id": str(report_id),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 6. UNEXPECTED / QUICKBOOKS ERROR
    # ==========================================================

    except Exception as exc:

        logger.exception(
            (
                "QuickBooks reconciliation failed. "
                "company=%s report=%s"
            ),
            profile.company.id,
            report_id,
        )

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to reconcile QuickBooks "
                    "transaction."
                ),
                "detail": str(exc),
                "report_id": str(report_id),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    # ==========================================================
    # 7. SUCCESS / RECONCILIATION RESULT
    # ==========================================================

    return Response(
        {
            "success": result.get(
                "success",
                False,
            ),

            "report_id": result.get(
                "report_id",
            ),

            "export_record_id": result.get(
                "export_record_id",
            ),

            "quickbooks_transaction_id": result.get(
                "quickbooks_transaction_id",
            ),

            "reconciliation_status": result.get(
                "reconciliation_status",
            ),

            "mismatches": result.get(
                "mismatches",
                [],
            ),

            # --------------------------------------------------
            # QuickBooks transaction information
            # --------------------------------------------------

            "quickbooks_purchase": result.get(
                "quickbooks_purchase",
                {},
            ),

            "reconciled_at": result.get(
                "reconciled_at",
            ),
        },
        status=status.HTTP_200_OK,
    )


# ==========================================================
# QUICKBOOKS — INTEGRATION HEALTH
# ==========================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def quickbooks_health(request):
    """
    Return the operational health of the company's
    QuickBooks integration.

    Checks:
        - connection state
        - OAuth/API reachability
        - payment account configuration
        - category mappings
        - automatic export
        - export status
        - reconciliation status
    """

    # ======================================================
    # 1. USER PROFILE
    # ======================================================

    try:
        profile = request.user.profile

    except Exception:
        return Response(
            {
                "success": False,
                "error": "User profile not found.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ======================================================
    # 2. COMPANY
    # ======================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ======================================================
    # 3. PERMISSION
    # ======================================================

    can_view = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not can_view:
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "view integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ======================================================
    # 4. FIND QUICKBOOKS INTEGRATION
    # ======================================================

    integration = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_QUICKBOOKS
            ),
        )
        .select_related(
            "credential",
        )
        .first()
    )

    # ------------------------------------------------------
    # Not configured
    # ------------------------------------------------------

    if not integration:
        return Response(
            {
                "success": True,
                "provider": "QUICKBOOKS",
                "overall_status": "NOT_CONFIGURED",

                "connection": {
                    "connected": False,
                    "active": False,
                    "company_reachable": False,
                },

                "configuration": {
                    "auto_export_enabled": False,
                    "payment_account_configured": False,
                    "payment_account": None,
                    "category_mapping_count": 0,
                },

                "exports": {
                    "total": 0,
                    "successful": 0,
                    "failed": 0,
                    "pending": 0,
                    "processing": 0,
                },

                "reconciliation": {
                    "verified": 0,
                    "mismatch": 0,
                    "missing": 0,
                    "error": 0,
                    "not_checked": 0,
                },

                "issues": [
                    {
                        "type": "NOT_CONFIGURED",
                        "message": (
                            "QuickBooks integration "
                            "is not configured."
                        ),
                    }
                ],
            },
            status=status.HTTP_200_OK,
        )

    # ======================================================
    # 5. CONNECTION HEALTH
    # ======================================================

    company_reachable = False
    connection_error = None
    realm_id = None
    quickbooks_company_name = None

    if (
        integration.is_connected
        and integration.is_active
    ):

        try:

            token_result = (
                get_valid_quickbooks_access_token(
                    integration=integration,
                )
            )

            config = (
                token_result.get("config")
                or {}
            )

            realm_id = config.get(
                "realm_id"
            )

            quickbooks_company_name = (
                config.get(
                    "quickbooks_company_name"
                )
            )

            if not realm_id:
                connection_error = (
                    "QuickBooks realm ID is missing."
                )

            else:

                client = QuickBooksClient()

                # This performs a real API request and proves
                # that the realm/token can access QuickBooks.
                company_info = (
                    client.get_company_info(
                        realm_id=realm_id,
                        access_token=(
                            token_result[
                                "access_token"
                            ]
                        ),
                    )
                )

                company_reachable = True

                if isinstance(
                    company_info,
                    dict,
                ):
                    quickbooks_company_name = (
                        company_info.get(
                            "CompanyName"
                        )
                        or quickbooks_company_name
                    )

        except QuickBooksIntegrationError as exc:

            connection_error = str(exc)

        except Exception as exc:

            logger.exception(
                "Unexpected QuickBooks health "
                "connection check error."
            )

            connection_error = str(exc)

    else:

        if not integration.is_connected:
            connection_error = (
                "QuickBooks is not connected."
            )

        elif not integration.is_active:
            connection_error = (
                "QuickBooks integration is inactive."
            )

    # ======================================================
    # 6. CONFIGURATION HEALTH
    # ======================================================

    payment_account_configured = bool(
        integration.quickbooks_payment_account_id
    )

    mapping_count = (
        QuickBooksCategoryMapping.objects
        .filter(
            integration=integration,
        )
        .count()
    )

    # ======================================================
    # 7. EXPORT HEALTH
    # ======================================================

    exports = (
        QuickBooksExportRecord.objects
        .filter(
            integration=integration,
        )
    )

    export_total = exports.count()

    export_success = exports.filter(
        status=(
            QuickBooksExportRecord
            .STATUS_SUCCESS
        ),
    ).count()

    export_failed = exports.filter(
        status=(
            QuickBooksExportRecord
            .STATUS_FAILED
        ),
    ).count()

    export_pending = exports.filter(
        status=(
            QuickBooksExportRecord
            .STATUS_PENDING
        ),
    ).count()

    export_processing = exports.filter(
        status=(
            QuickBooksExportRecord
            .STATUS_PROCESSING
        ),
    ).count()

    # ======================================================
    # 8. RECONCILIATION HEALTH
    # ======================================================

    reconciliation_verified = (
        exports.filter(
            reconciliation_status=(
                QuickBooksExportRecord
                .RECONCILIATION_VERIFIED
            ),
        ).count()
    )

    reconciliation_mismatch = (
        exports.filter(
            reconciliation_status=(
                QuickBooksExportRecord
                .RECONCILIATION_MISMATCH
            ),
        ).count()
    )

    reconciliation_missing = (
        exports.filter(
            reconciliation_status=(
                QuickBooksExportRecord
                .RECONCILIATION_MISSING
            ),
        ).count()
    )

    reconciliation_error = (
        exports.filter(
            reconciliation_status=(
                QuickBooksExportRecord
                .RECONCILIATION_ERROR
            ),
        ).count()
    )

    reconciliation_not_checked = (
        exports.filter(
            reconciliation_status=(
                QuickBooksExportRecord
                .RECONCILIATION_NOT_CHECKED
            ),
        ).count()
    )

    # ======================================================
    # 9. BUILD ISSUES
    # ======================================================

    issues = []

    if not integration.is_connected:

        issues.append(
            {
                "type": "DISCONNECTED",
                "message": (
                    "QuickBooks is not connected."
                ),
            }
        )

    elif not integration.is_active:

        issues.append(
            {
                "type": "INACTIVE",
                "message": (
                    "QuickBooks integration "
                    "is inactive."
                ),
            }
        )

    elif not company_reachable:

        issues.append(
            {
                "type": "CONNECTION_ERROR",
                "message": (
                    connection_error
                    or (
                        "Unable to reach "
                        "QuickBooks."
                    )
                ),
            }
        )

    if not payment_account_configured:

        issues.append(
            {
                "type": (
                    "PAYMENT_ACCOUNT_MISSING"
                ),
                "message": (
                    "QuickBooks payment account "
                    "is not configured."
                ),
            }
        )

    if mapping_count == 0:

        issues.append(
            {
                "type": "CATEGORY_MAPPING_MISSING",
                "message": (
                    "No QuickBooks category "
                    "mappings are configured."
                ),
            }
        )

    if export_failed:

        issues.append(
            {
                "type": "EXPORT_FAILURES",
                "count": export_failed,
                "message": (
                    f"{export_failed} QuickBooks "
                    "export(s) have failed."
                ),
            }
        )

    if reconciliation_mismatch:

        issues.append(
            {
                "type": (
                    "RECONCILIATION_MISMATCH"
                ),
                "count": (
                    reconciliation_mismatch
                ),
                "message": (
                    f"{reconciliation_mismatch} "
                    "QuickBooks transaction(s) "
                    "have reconciliation mismatches."
                ),
            }
        )

    if reconciliation_missing:

        issues.append(
            {
                "type": "MISSING_TRANSACTION",
                "count": (
                    reconciliation_missing
                ),
                "message": (
                    f"{reconciliation_missing} "
                    "QuickBooks transaction(s) "
                    "are missing."
                ),
            }
        )

    if reconciliation_error:

        issues.append(
            {
                "type": "RECONCILIATION_ERROR",
                "count": (
                    reconciliation_error
                ),
                "message": (
                    f"{reconciliation_error} "
                    "QuickBooks reconciliation "
                    "check(s) failed."
                ),
            }
        )

    # ======================================================
    # 10. OVERALL STATUS
    # ======================================================

    critical_issue = (
        not integration.is_connected
        or not integration.is_active
        or not company_reachable
        or not payment_account_configured
    )

    warning_issue = (
        mapping_count == 0
        or export_failed > 0
        or reconciliation_mismatch > 0
        or reconciliation_missing > 0
        or reconciliation_error > 0
    )

    if critical_issue:
        overall_status = "UNHEALTHY"

    elif warning_issue:
        overall_status = "WARNING"

    else:
        overall_status = "HEALTHY"

    # ======================================================
    # 11. RESPONSE
    # ======================================================

    return Response(
        {
            "success": True,

            "provider": "QUICKBOOKS",

            "overall_status": (
                overall_status
            ),

            "connection": {
                "connected": (
                    integration.is_connected
                ),
                "active": (
                    integration.is_active
                ),
                "company_reachable": (
                    company_reachable
                ),
                "realm_id": realm_id,
                "quickbooks_company_name": (
                    quickbooks_company_name
                ),
                "error": connection_error,
            },

            "configuration": {
                "auto_export_enabled": (
                    integration
                    .quickbooks_auto_export
                ),

                "payment_account_configured": (
                    payment_account_configured
                ),

                "payment_account": {
                    "id": (
                        integration
                        .quickbooks_payment_account_id
                    ),
                    "name": (
                        integration
                        .quickbooks_payment_account_name
                    ),
                    "type": (
                        integration
                        .quickbooks_payment_account_type
                    ),
                }
                if payment_account_configured
                else None,

                "category_mapping_count": (
                    mapping_count
                ),
            },

            "exports": {
                "total": export_total,
                "successful": export_success,
                "failed": export_failed,
                "pending": export_pending,
                "processing": (
                    export_processing
                ),
            },

            "reconciliation": {
                "verified": (
                    reconciliation_verified
                ),
                "mismatch": (
                    reconciliation_mismatch
                ),
                "missing": (
                    reconciliation_missing
                ),
                "error": (
                    reconciliation_error
                ),
                "not_checked": (
                    reconciliation_not_checked
                ),
            },

            "issues": issues,

            "checked_at": (
                timezone.now()
            ),
        },
        status=status.HTTP_200_OK,
    )

# ==========================================================
# BAMBOOHR — INTEGRATION HEALTH
# ==========================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bamboohr_health(request):
    """
    Return operational health information for the
    company's BambooHR integration.

    Checks:
        - integration configured
        - integration connected / active
        - OAuth credentials available
        - BambooHR API reachable
        - latest synchronization status
        - recent sync failures
    """

    # ======================================================
    # 1. USER PROFILE
    # ======================================================

    try:
        profile = request.user.profile

    except Exception:
        return Response(
            {
                "success": False,
                "error": "User profile not found.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ======================================================
    # 2. COMPANY
    # ======================================================

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ======================================================
    # 3. PERMISSION
    # ======================================================

    can_view = (
        profile.role == "COMPANY_ADMIN"
        or has_company_permission(
            profile,
            "can_view_integrations",
        )
        or has_company_permission(
            profile,
            "can_manage_integrations",
        )
    )

    if not can_view:
        return Response(
            {
                "success": False,
                "error": (
                    "You are not allowed to "
                    "view integrations."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ======================================================
    # 4. FIND BAMBOOHR INTEGRATION
    # ======================================================

    integration = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration
                .PROVIDER_BAMBOOHR
            ),
        )
        .select_related(
            "credential",
        )
        .first()
    )

    # ======================================================
    # 5. NOT CONFIGURED
    # ======================================================

    if not integration:
        return Response(
            {
                "success": True,
                "provider": "BAMBOOHR",

                "overall_status": "NOT_CONFIGURED",

                "connection": {
                    "connected": False,
                    "active": False,
                    "company_reachable": False,
                    "company_domain": None,
                    "error": None,
                },

                "sync": {
                    "last_synced_at": None,
                    "last_sync_status": None,
                    "last_sync_error": None,

                    "departments": None,
                    "employees": None,
                    "managers": None,
                    "all": None,
                },

                "sync_summary": {
                    "total": 0,
                    "successful": 0,
                    "failed": 0,
                    "running": 0,
                },

                "issues": [
                    {
                        "type": "NOT_CONFIGURED",
                        "message": (
                            "BambooHR integration "
                            "is not configured."
                        ),
                    }
                ],

                "checked_at": timezone.now(),
            },
            status=status.HTTP_200_OK,
        )

    # ======================================================
    # 6. CONNECTION HEALTH
    # ======================================================

    company_reachable = False
    company_domain = None
    connection_error = None

    if (
        integration.is_connected
        and integration.is_active
    ):

        try:

            # ----------------------------------------------
            # Read encrypted OAuth configuration
            # ----------------------------------------------

            credential = integration.credential

            config = decrypt_integration_config(
                credential.encrypted_config
            )

            company_domain = (
                config.get("company_domain")
                or ""
            ).strip()

            access_token = (
                config.get("access_token")
                or ""
            ).strip()

            refresh_token = (
                config.get("refresh_token")
                or ""
            ).strip()

            if not company_domain:
                connection_error = (
                    "BambooHR company domain is missing."
                )

            elif not access_token:
                connection_error = (
                    "BambooHR access token is missing."
                )

            else:

                # ------------------------------------------
                # Test real BambooHR API connection
                # ------------------------------------------

                client = BambooHRClient(
                    company_domain=company_domain,
                    access_token=access_token,
                )

                try:

                    client.test_connection()

                    company_reachable = True

                # ------------------------------------------
                # Access token may have expired
                # ------------------------------------------

                except BambooHRAuthenticationError:

                    if not refresh_token:
                        raise BambooHRAuthenticationError(
                            (
                                "BambooHR access token "
                                "expired and no refresh "
                                "token is available."
                            )
                        )

                    oauth_service = (
                        BambooHROAuthService(
                            company_domain=company_domain,
                        )
                    )

                    token_data = (
                        oauth_service
                        .refresh_access_token(
                            refresh_token=refresh_token,
                        )
                    )

                    new_access_token = (
                        token_data.get(
                            "access_token"
                        )
                    )

                    new_refresh_token = (
                        token_data.get(
                            "refresh_token"
                        )
                        or refresh_token
                    )

                    expires_in = (
                        token_data.get(
                            "expires_in"
                        )
                    )

                    if not new_access_token:
                        raise BambooHRAuthenticationError(
                            (
                                "BambooHR token refresh "
                                "did not return an "
                                "access token."
                            )
                        )

                    # --------------------------------------
                    # Save refreshed credentials
                    # --------------------------------------

                    config[
                        "access_token"
                    ] = new_access_token

                    config[
                        "refresh_token"
                    ] = new_refresh_token

                    if expires_in:
                        config[
                            "access_token_expires_at"
                        ] = (
                            timezone.now()
                            + timedelta(
                                seconds=int(
                                    expires_in
                                )
                            )
                        ).isoformat()

                    encrypted_config = (
                        encrypt_integration_config(
                            config
                        )
                    )

                    IntegrationCredential.objects.update_or_create(
                        integration=integration,
                        defaults={
                            "encrypted_config": (
                                encrypted_config
                            ),
                        },
                    )

                    # --------------------------------------
                    # Retry connection using new token
                    # --------------------------------------

                    client = BambooHRClient(
                        company_domain=company_domain,
                        access_token=new_access_token,
                    )

                    client.test_connection()

                    company_reachable = True

        except (
            BambooHRAuthenticationError,
            BambooHRPermissionError,
            BambooHRConnectionError,
            BambooHRIntegrationError,
            ValueError,
        ) as exc:

            connection_error = str(exc)

        except Exception as exc:

            logger.exception(
                (
                    "Unexpected BambooHR health "
                    "connection check error."
                )
            )

            connection_error = str(exc)

    else:

        if not integration.is_connected:
            connection_error = (
                "BambooHR is not connected."
            )

        elif not integration.is_active:
            connection_error = (
                "BambooHR integration is inactive."
            )

    # ======================================================
    # 7. SYNC LOGS
    # ======================================================

    sync_logs = (
        IntegrationSyncLog.objects
        .filter(
            integration=integration,
        )
    )

    sync_total = sync_logs.count()

    sync_success = sync_logs.filter(
        status=(
            IntegrationSyncLog
            .STATUS_SUCCESS
        ),
    ).count()

    sync_failed = sync_logs.filter(
        status=(
            IntegrationSyncLog
            .STATUS_FAILED
        ),
    ).count()

    sync_running = sync_logs.filter(
        status=(
            IntegrationSyncLog
            .STATUS_RUNNING
        ),
    ).count()

    # ======================================================
    # 8. LATEST SYNC BY RESOURCE
    # ======================================================

    def latest_sync(resource):

        sync_log = (
            sync_logs
            .filter(
                stats__resource=resource,
            )
            .order_by(
                "-started_at",
            )
            .first()
        )

        if not sync_log:
            return None

        return {
            "id": str(
                sync_log.id
            ),

            "status": (
                sync_log.status
            ),

            "trigger": (
                sync_log.trigger
            ),

            "records_received": (
                sync_log.records_received
            ),

            "records_created": (
                sync_log.records_created
            ),

            "records_updated": (
                sync_log.records_updated
            ),

            "records_skipped": (
                sync_log.records_skipped
            ),

            "error_message": (
                sync_log.error_message
            ),

            "started_at": (
                sync_log.started_at
            ),

            "completed_at": (
                sync_log.completed_at
            ),
        }

    departments_sync = latest_sync(
        "DEPARTMENTS"
    )

    employees_sync = latest_sync(
        "EMPLOYEES"
    )

    managers_sync = latest_sync(
        "MANAGERS"
    )

    all_sync = latest_sync(
        "ALL"
    )

    # ======================================================
    # 9. BUILD ISSUES
    # ======================================================

    issues = []

    if not integration.is_connected:

        issues.append(
            {
                "type": "DISCONNECTED",
                "message": (
                    "BambooHR is not connected."
                ),
            }
        )

    elif not integration.is_active:

        issues.append(
            {
                "type": "INACTIVE",
                "message": (
                    "BambooHR integration is inactive."
                ),
            }
        )

    elif not company_reachable:

        issues.append(
            {
                "type": "CONNECTION_ERROR",
                "message": (
                    connection_error
                    or (
                        "Unable to reach BambooHR."
                    )
                ),
            }
        )

    # ------------------------------------------------------
    # Latest ALL sync failure
    # ------------------------------------------------------

    if (
        all_sync
        and all_sync.get("status")
        == IntegrationSyncLog.STATUS_FAILED
    ):

        issues.append(
            {
                "type": "FULL_SYNC_FAILED",
                "message": (
                    all_sync.get(
                        "error_message"
                    )
                    or (
                        "The latest BambooHR full "
                        "sync failed."
                    )
                ),
            }
        )

    # ------------------------------------------------------
    # Resource-specific sync failures
    # ------------------------------------------------------

    resource_syncs = {
        "DEPARTMENTS": departments_sync,
        "EMPLOYEES": employees_sync,
        "MANAGERS": managers_sync,
    }

    for resource_name, resource_sync in (
        resource_syncs.items()
    ):

        if (
            resource_sync
            and resource_sync.get(
                "status"
            )
            == IntegrationSyncLog.STATUS_FAILED
        ):

            issues.append(
                {
                    "type": (
                        f"{resource_name}_SYNC_FAILED"
                    ),
                    "message": (
                        resource_sync.get(
                            "error_message"
                        )
                        or (
                            f"Latest {resource_name.lower()} "
                            "sync failed."
                        )
                    ),
                }
            )

    # ------------------------------------------------------
    # Never synchronized
    # ------------------------------------------------------

    if sync_total == 0:

        issues.append(
            {
                "type": "NEVER_SYNCED",
                "message": (
                    "BambooHR has not been "
                    "synchronized yet."
                ),
            }
        )

    # ======================================================
    # 10. OVERALL STATUS
    # ======================================================

    critical_issue = (
        not integration.is_connected
        or not integration.is_active
        or not company_reachable
    )

    warning_issue = (
        sync_total == 0
        or bool(
            [
                issue
                for issue in issues
                if (
                    "SYNC_FAILED"
                    in issue.get(
                        "type",
                        ""
                    )
                )
            ]
        )
    )

    if critical_issue:
        overall_status = "UNHEALTHY"

    elif warning_issue:
        overall_status = "WARNING"

    else:
        overall_status = "HEALTHY"

    # ======================================================
    # 11. RESPONSE
    # ======================================================

    return Response(
        {
            "success": True,

            "provider": "BAMBOOHR",

            "overall_status": (
                overall_status
            ),

            "connection": {
                "connected": (
                    integration.is_connected
                ),

                "active": (
                    integration.is_active
                ),

                "company_reachable": (
                    company_reachable
                ),

                "company_domain": (
                    company_domain
                ),

                "error": (
                    connection_error
                ),
            },

            "sync": {
                "last_synced_at": (
                    integration.last_synced_at
                ),

                "last_sync_status": (
                    integration.last_sync_status
                ),

                "last_sync_error": (
                    integration.last_sync_error
                ),

                "departments": (
                    departments_sync
                ),

                "employees": (
                    employees_sync
                ),

                "managers": (
                    managers_sync
                ),

                "all": (
                    all_sync
                ),
            },

            "sync_summary": {
                "total": (
                    sync_total
                ),

                "successful": (
                    sync_success
                ),

                "failed": (
                    sync_failed
                ),

                "running": (
                    sync_running
                ),
            },

            "issues": issues,

            "checked_at": (
                timezone.now()
            ),
        },
        status=status.HTTP_200_OK,
    )
