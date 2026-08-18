from asyncio.log import logger
from datetime import timedelta
import secrets

from rest_framework.decorators import (
    api_view,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from audit_logs.utils import create_integration_audit_log
from audit_logs.models import AuditLog

from .tasks import export_report_to_quickbooks_task

from .services.quickbooks import QuickBooksClient, QuickBooksIntegrationError
from .services.quickbooks_auth import get_valid_quickbooks_access_token
from tenants.permission_utils import (
    has_company_permission,
)

from .models import CompanyIntegration, IntegrationSyncLog, QuickBooksCategoryMapping, QuickBooksOAuthState
from .serializers import (
    BambooHRStatusSerializer,
    CompanyIntegrationSerializer,
    IntegrationSyncLogSerializer,
    QuickBooksCategoryMappingSerializer,
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

    integrations = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
        )
        .select_related(
            "company",
        )
        .order_by(
            "provider",
        )
    )

    serializer = CompanyIntegrationSerializer(
        integrations,
        many=True,
    )

    return Response(
        {
            "success": True,
            "count": integrations.count(),
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
        for integration in (
            CompanyIntegration.objects
            .filter(
                company=profile.company,
            )
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

                "configured": bool(
                    integration
                    and hasattr(
                        integration,
                        "credential",
                    )
                    and integration.credential.encrypted_config
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def test_bamboohr_connection(request):

    profile = request.user.profile

    # ==========================================================
    # Permission
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

    # ==========================================================
    # Request data
    # ==========================================================

    company_domain = str(
        request.data.get(
            "company_domain",
            "",
        )
    ).strip()

    api_key = str(
        request.data.get(
            "api_key",
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

    if not api_key:
        return Response(
            {
                "success": False,
                "error": "api_key is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # Test BambooHR
    # ==========================================================

    try:

        client = BambooHRClient(
            company_domain=company_domain,
            api_key=api_key,
        )

        result = client.test_connection()

    except BambooHRAuthenticationError as exc:

        return Response(
            {
                "success": False,
                "connected": False,
                "error": str(exc),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    except BambooHRPermissionError as exc:

        return Response(
            {
                "success": False,
                "connected": False,
                "error": str(exc),
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
                "connected": False,
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "success": True,
            "connected": True,
            "message": (
                "BambooHR connection successful."
            ),
            "company_domain": (
                result.get("company_domain")
            ),
            "bamboohr_user": (
                result.get("employee")
            ),
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
    # 2. REQUEST DATA
    # ==========================================================

    company_domain = str(
        request.data.get(
            "company_domain",
            "",
        )
    ).strip()

    api_key = str(
        request.data.get(
            "api_key",
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

    if not api_key:
        return Response(
            {
                "success": False,
                "error": "api_key is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 3. TEST CONNECTION BEFORE SAVING
    # ==========================================================

    try:

        client = BambooHRClient(
            company_domain=company_domain,
            api_key=api_key,
        )

        test_result = (
            client.test_connection()
        )

    except BambooHRAuthenticationError as exc:

        create_integration_audit_log(
            company=profile.company,
            provider="BAMBOOHR",
            action="BAMBOOHR_CONNECTION_FAILED",
            action_by=profile,
            message=(
                "BambooHR connection failed "
                "because authentication was rejected."
            ),
            metadata={
                "company_domain": company_domain,
                "stage": "AUTHENTICATION",
                "error": str(exc),
            },
        )

        return Response(
            {
                "success": False,
                "connected": False,
                "error": str(exc),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    except BambooHRPermissionError as exc:

        create_integration_audit_log(
            company=profile.company,
            provider="BAMBOOHR",
            action="BAMBOOHR_CONNECTION_FAILED",
            action_by=profile,
            message=(
                "BambooHR connection failed "
                "because access was denied."
            ),
            metadata={
                "company_domain": company_domain,
                "stage": "PERMISSION",
                "error": str(exc),
            },
        )

        return Response(
            {
                "success": False,
                "connected": False,
                "error": str(exc),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    except (
        BambooHRConnectionError,
        BambooHRIntegrationError,
        ValueError,
    ) as exc:

        create_integration_audit_log(
            company=profile.company,
            provider="BAMBOOHR",
            action="BAMBOOHR_CONNECTION_FAILED",
            action_by=profile,
            message=(
                "BambooHR connection test failed."
            ),
            metadata={
                "company_domain": company_domain,
                "stage": "CONNECTION_TEST",
                "error": str(exc),
            },
        )

        return Response(
            {
                "success": False,
                "connected": False,
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 4. CREATE / GET COMPANY INTEGRATION
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
    # 5. ENCRYPT CONFIG
    # ==========================================================

    try:

        encrypted_config = (
            encrypt_integration_config(
                {
                    "company_domain": (
                        client.company_domain
                    ),
                    "api_key": api_key,
                }
            )
        )

    except Exception as exc:

        create_integration_audit_log(
            company=profile.company,
            integration=integration,
            provider="BAMBOOHR",
            action="BAMBOOHR_CONNECTION_FAILED",
            action_by=profile,
            message=(
                "BambooHR connection failed "
                "while encrypting credentials."
            ),
            metadata={
                "company_domain": (
                    client.company_domain
                ),
                "stage": "CREDENTIAL_ENCRYPTION",
                "error": str(exc),
            },
        )

        return Response(
            {
                "success": False,
                "connected": False,
                "error": (
                    "Unable to securely store "
                    "BambooHR credentials."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 6. SAVE CREDENTIALS
    # ==========================================================

    try:

        IntegrationCredential.objects.update_or_create(
            integration=integration,
            defaults={
                "encrypted_config": (
                    encrypted_config
                ),
            },
        )

    except Exception as exc:

        create_integration_audit_log(
            company=profile.company,
            integration=integration,
            provider="BAMBOOHR",
            action="BAMBOOHR_CONNECTION_FAILED",
            action_by=profile,
            message=(
                "BambooHR connection failed "
                "while saving credentials."
            ),
            metadata={
                "company_domain": (
                    client.company_domain
                ),
                "stage": "CREDENTIAL_STORAGE",
                "error": str(exc),
            },
        )

        return Response(
            {
                "success": False,
                "connected": False,
                "error": (
                    "Unable to save BambooHR "
                    "credentials."
                ),
            },
            status=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    # ==========================================================
    # 7. MARK CONNECTED
    # ==========================================================

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
    # 8. SUCCESS AUDIT LOG
    # ==========================================================

    create_integration_audit_log(
        company=profile.company,
        integration=integration,
        provider="BAMBOOHR",
        action="BAMBOOHR_CONNECTED",
        action_by=profile,
        message=(
            "BambooHR connected successfully."
        ),
        metadata={
            "company_domain": (
                client.company_domain
            ),
            "integration_id": str(
                integration.id
            ),
        },
    )

    # ==========================================================
    # 9. RESPONSE
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
                integration.id
            ),
            "company_domain": (
                client.company_domain
            ),
            "bamboohr_user": (
                test_result.get(
                    "employee"
                )
            ),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preview_bamboohr_employees(request):

    profile = request.user.profile

    # ==========================================================
    # Permission
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
    # Find BambooHR integration
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
                "error": (
                    "BambooHR is not connected."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # Decrypt credentials
    # ==========================================================

    try:

        config = decrypt_integration_config(
            integration
            .credential
            .encrypted_config
        )

    except Exception:

        return Response(
            {
                "success": False,
                "error": (
                    "Unable to read BambooHR "
                    "credentials."
                ),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # ==========================================================
    # Create BambooHR client
    # ==========================================================

    try:

        client = BambooHRClient(
            company_domain=(
                config.get(
                    "company_domain"
                )
            ),
            api_key=(
                config.get(
                    "api_key"
                )
            ),
        )

        employees = (
            client.get_all_employees()
        )

    except BambooHRAuthenticationError as exc:

        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    except BambooHRPermissionError as exc:

        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    except BambooHRIntegrationError as exc:

        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # Return BambooHR data
    # ==========================================================

    return Response(
        {
            "success": True,
            "provider": "BAMBOOHR",
            "count": len(employees),
            "employees": employees,
        },
        status=status.HTTP_200_OK,
    )

from django.utils import timezone

from .models import CompanyIntegration

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
    sync_bamboohr_employees,
)


from .services.integration_sync import (
    run_bamboohr_sync,
)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_bamboohr(request):

    profile = request.user.profile

    # ==========================================================
    # Permission
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
    # Find integration
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
                "error": (
                    "BambooHR is not connected."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # Run common sync service
    # ==========================================================

    result = run_bamboohr_sync(
        integration=integration,
        trigger=(
            IntegrationSyncLog.TRIGGER_MANUAL
        ),
    )

    if not result.get(
        "success"
    ):

        return Response(
            result,
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        result,
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bamboohr_status(request):

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

    if not profile.company:
        return Response(
            {
                "success": False,
                "error": "Company is not assigned.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    integration = (
        CompanyIntegration.objects
        .filter(
            company=profile.company,
            provider=(
                CompanyIntegration.PROVIDER_BAMBOOHR
            ),
        )
        .select_related(
            "credential"
        )
        .first()
    )

    if not integration:
        return Response(
            {
                "success": True,
                "provider": "BAMBOOHR",
                "connected": False,
                "configured": False,
                "integration": None,
            },
            status=status.HTTP_200_OK,
        )

    serializer = BambooHRStatusSerializer(
        integration
    )

    return Response(
        {
            "success": True,
            "provider": "BAMBOOHR",
            "connected": (
                integration.is_connected
            ),
            "configured": (
                serializer.data["configured"]
            ),
            "integration": serializer.data,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bamboohr_sync_history(request):

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
                    "BambooHR integration not found."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # Optional limit
    try:
        limit = int(
            request.query_params.get(
                "limit",
                20,
            )
        )

    except ValueError:
        limit = 20

    limit = max(
        1,
        min(
            limit,
            100,
        ),
    )

    logs = (
        IntegrationSyncLog.objects
        .filter(
            integration=integration,
        )
        .order_by(
            "-started_at"
        )[:limit]
    )

    serializer = IntegrationSyncLogSerializer(
        logs,
        many=True,
    )

    return Response(
        {
            "success": True,
            "provider": "BAMBOOHR",
            "count": len(
                serializer.data
            ),
            "results": serializer.data,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def disconnect_bamboohr(request):

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
    # 3. FIND BAMBOOHR INTEGRATION
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
    # 4. REMOVE STORED CREDENTIALS
    # ==========================================================

    try:

        credential = (
            integration.credential
        )

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

    # ==========================================================
    # 6. AUDIT LOG
    # ==========================================================

    create_integration_audit_log(
        company=profile.company,
        integration=integration,
        provider="BAMBOOHR",
        action="BAMBOOHR_DISCONNECTED",
        action_by=profile,
        message=(
            "BambooHR disconnected successfully."
        ),
        metadata={
            "integration_id": str(
                integration.id
            ),
        },
    )

    # ==========================================================
    # 7. RESPONSE
    # ==========================================================

    return Response(
        {
            "success": True,
            "message": (
                "BambooHR disconnected successfully."
            ),
            "provider": "BAMBOOHR",
            "connected": False,
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

    existing = (
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
            "credential"
        )
        .first()
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

    try:

        token_result = (
            get_valid_quickbooks_access_token(
                integration=integration,
            )
        )

        config = token_result["config"]

        client = QuickBooksClient()

        accounts = client.get_expense_accounts(
            realm_id=config.get(
                "realm_id"
            ),
            access_token=(
                token_result[
                    "access_token"
                ]
            ),
        )

    except Exception as exc:

        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = []

    for account in accounts:

        results.append(
            {
                "id": account.get("Id"),
                "name": account.get("Name"),
                "fully_qualified_name": (
                    account.get(
                        "FullyQualifiedName"
                    )
                ),
                "account_type": (
                    account.get(
                        "AccountType"
                    )
                ),
                "account_sub_type": (
                    account.get(
                        "AccountSubType"
                    )
                ),
                "active": (
                    account.get(
                        "Active"
                    )
                ),
            }
        )

    return Response(
        {
            "success": True,
            "provider": "QUICKBOOKS",
            "count": len(results),
            "accounts": results,
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
    # PERMISSION
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
    # REQUEST DATA
    # ==========================================================

    zepex_category = (
        request.data.get(
            "zepex_category"
        )
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
                "error": (
                    "zepex_category is required."
                ),
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
    # VERIFY ACCOUNT WITH QUICKBOOKS
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

        client = QuickBooksClient()

        accounts = (
            client.get_expense_accounts(
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

    except Exception as exc:

        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # FIND SELECTED ACCOUNT
    # ==========================================================

    selected_account = next(
        (
            account
            for account in accounts
            if str(
                account.get("Id")
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
    # SAVE / UPDATE
    # ==========================================================

    mapping, created = (
        QuickBooksCategoryMapping.objects
        .update_or_create(
            integration=integration,
            zepex_category=zepex_category,
            defaults={
                "quickbooks_account_id": (
                    str(
                        selected_account.get(
                            "Id"
                        )
                    )
                ),
                "quickbooks_account_name": (
                    selected_account.get(
                        "Name"
                    )
                    or ""
                ),
                "quickbooks_account_type": (
                    selected_account.get(
                        "AccountType"
                    )
                ),
                "quickbooks_account_sub_type": (
                    selected_account.get(
                        "AccountSubType"
                    )
                ),
                "is_active": True,
            },
        )
    )

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
from .services.quickbooks_export import (
    export_report_to_quickbooks,
    QuickBooksExportError,
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

    # ==========================================================
    # 8. CREATE PENDING EXPORT RECORD
    # ==========================================================

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

from expenses.models import ExpenseReport

from integrations.models import (
    CompanyIntegration,
    QuickBooksExportRecord,
)

from tenants.permission_utils import (
    has_company_permission,
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
    # 6. EXPORT RECORD
    # ==========================================================

    export_record = (
        QuickBooksExportRecord.objects
        .filter(
            integration=integration,
            report=report,
        )
        .first()
    )

    if not export_record:
        return Response(
            {
                "success": False,
                "error": (
                    "No QuickBooks export attempt "
                    "exists for this report."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # ==========================================================
    # 7. SUCCESS CANNOT BE RETRIED
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
                "quickbooks_transaction_id": (
                    export_record
                    .quickbooks_transaction_id
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ==========================================================
    # 8. PENDING CANNOT BE RETRIED AGAIN
    # ==========================================================

    if (
        export_record.status
        == QuickBooksExportRecord.STATUS_PENDING
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

    # ==========================================================
    # 9. ONLY FAILED EXPORTS REACH HERE
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
    # 10. QUEUE CELERY TASK
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
    },
)
    except Exception:
        logger.exception(
            "Unable to queue QuickBooks retry."
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
    # 11. RESPONSE
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