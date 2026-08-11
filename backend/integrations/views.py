from django.shortcuts import render

# Create your views here.
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

from .models import Integration
from .serializers import IntegrationSerializer
from .provider_config import PROVIDER_CONFIG
from .services import IntegrationService

from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Integration
from .serializers import IntegrationSerializer
from .services import IntegrationService

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integration_list(request):
    """
    Return all integrations configured for the logged-in user's company.
    """

    company = request.user.employee.company

    integrations = Integration.objects.filter(
        company=company
    ).order_by(
        "category",
        "provider",
    )

    serializer = IntegrationSerializer(
        integrations,
        many=True,
    )

    return Response({
        "success": True,
        "integrations": serializer.data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integration_detail(request, integration_id):
    """
    Return one integration belonging to the logged-in user's company.
    """

    company = request.user.employee.company

    integration = get_object_or_404(
        Integration,
        id=integration_id,
        company=company,
    )

    serializer = IntegrationSerializer(integration)

    return Response({
        "success": True,
        "integration": serializer.data,
    })


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def integration_delete(request, integration_id):
    """
    Disconnect/remove an integration from the company.
    """

    company = request.user.employee.company

    integration = get_object_or_404(
        Integration,
        id=integration_id,
        company=company,
    )

    integration.delete()

    return Response({
        "success": True,
        "message": "Integration disconnected successfully.",
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def connect_integration(request):
    """
    Start the connection process for an integration provider.
    """

    company = request.user.employee.company

    category = request.data.get("category")
    provider = request.data.get("provider")

    if not category or not provider:
        return Response(
            {
                "success": False,
                "message": "category and provider are required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate category
    valid_categories = dict(Integration.CATEGORY_CHOICES)

    if category not in valid_categories:
        return Response(
            {
                "success": False,
                "message": "Invalid integration category.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate provider
    valid_providers = dict(Integration.PROVIDER_CHOICES)

    if provider not in valid_providers:
        return Response(
            {
                "success": False,
                "message": "Invalid integration provider.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Make sure provider belongs to the selected category
    provider_category_map = {
        Integration.PROVIDER_BAMBOOHR: Integration.CATEGORY_HRMS,
        Integration.PROVIDER_RIPPLING: Integration.CATEGORY_HRMS,
        Integration.PROVIDER_WORKDAY: Integration.CATEGORY_HRMS,
        Integration.PROVIDER_HIBOB: Integration.CATEGORY_HRMS,
        Integration.PROVIDER_DEEL: Integration.CATEGORY_HRMS,
        Integration.PROVIDER_ZOHO_PEOPLE: Integration.CATEGORY_HRMS,

        Integration.PROVIDER_ADP: Integration.CATEGORY_PAYROLL,
        Integration.PROVIDER_GUSTO: Integration.CATEGORY_PAYROLL,
        Integration.PROVIDER_PAYCHEX: Integration.CATEGORY_PAYROLL,
        Integration.PROVIDER_UKG: Integration.CATEGORY_PAYROLL,
        Integration.PROVIDER_PAYLOCITY: Integration.CATEGORY_PAYROLL,

        Integration.PROVIDER_QUICKBOOKS: Integration.CATEGORY_ACCOUNTING,
        Integration.PROVIDER_XERO: Integration.CATEGORY_ACCOUNTING,
        Integration.PROVIDER_SAGE: Integration.CATEGORY_ACCOUNTING,
        Integration.PROVIDER_ZOHO_BOOKS: Integration.CATEGORY_ACCOUNTING,
        Integration.PROVIDER_FRESHBOOKS: Integration.CATEGORY_ACCOUNTING,
        Integration.PROVIDER_NETSUITE: Integration.CATEGORY_ACCOUNTING,

        Integration.PROVIDER_MICROSOFT_ENTRA: Integration.CATEGORY_IT,
        Integration.PROVIDER_OKTA: Integration.CATEGORY_IT,
        Integration.PROVIDER_GOOGLE_WORKSPACE: Integration.CATEGORY_IT,
        Integration.PROVIDER_ONELOGIN: Integration.CATEGORY_IT,
        Integration.PROVIDER_JUMPCLOUD: Integration.CATEGORY_IT,
        Integration.PROVIDER_PING_IDENTITY: Integration.CATEGORY_IT,

        Integration.PROVIDER_SAP: Integration.CATEGORY_ERP,
        Integration.PROVIDER_ORACLE: Integration.CATEGORY_ERP,
        Integration.PROVIDER_MICROSOFT_DYNAMICS: Integration.CATEGORY_ERP,
        Integration.PROVIDER_ODOO: Integration.CATEGORY_ERP,
        Integration.PROVIDER_ACUMATICA: Integration.CATEGORY_ERP,
    }

    expected_category = provider_category_map.get(provider)

    if expected_category != category:
        return Response(
            {
                "success": False,
                "message": (
                    f"{provider} does not belong to "
                    f"{category}."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    integration, created = Integration.objects.get_or_create(
        company=company,
        provider=provider,
        defaults={
            "category": category,
            "status": Integration.STATUS_DISCONNECTED,
        },
    )

    # Keep category synchronized if the record already exists
    if integration.category != category:
        integration.category = category
        integration.save(update_fields=["category", "updated_at"])

    serializer = IntegrationSerializer(integration)

    return Response(
        {
            "success": True,
            "message": (
                "Integration connection initialized."
                if created
                else "Integration connection already exists."
            ),
            "integration": serializer.data,
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integration_provider_config(request, provider):
    """
    Return connection requirements for a provider.
    """

    config = PROVIDER_CONFIG.get(provider.upper())

    if not config:
        return Response(
            {
                "success": False,
                "message": "Unsupported integration provider.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        "success": True,
        "provider": provider.upper(),
        "config": config,
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integration_authorize(request, provider):

    company = request.user.employee.company

    provider = provider.upper()

    integration = get_object_or_404(
        Integration,
        company=company,
        provider=provider,
    )

    try:

        authorization_url = (
            IntegrationService.get_authorization_url(
                integration,
                request,
            )
        )

    except ValueError as exc:

        return Response(
            {
                "success": False,
                "message": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "success": True,
            "provider": provider,
            "integration_id": str(integration.id),
            "authorization_url": authorization_url,
        }
    )

@api_view(["GET"])
@permission_classes([])
def integration_oauth_callback(request, provider):

    provider = provider.upper()

    code = request.GET.get("code")
    state = request.GET.get("state")
    error = request.GET.get("error")

    if error:
        return Response(
            {
                "success": False,
                "provider": provider,
                "error": error,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not code:
        return Response(
            {
                "success": False,
                "message": "Authorization code was not provided.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        state_data = (
            IntegrationService.verify_oauth_state(
                state
            )
        )

    except ValueError as exc:
        return Response(
            {
                "success": False,
                "message": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if state_data.get("provider") != provider:
        return Response(
            {
                "success": False,
                "message": "OAuth provider mismatch.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    integration = get_object_or_404(
        Integration,
        id=state_data.get("integration_id"),
        company_id=state_data.get("company_id"),
        provider=provider,
    )

    try:

        IntegrationService.exchange_code_for_token(
            integration=integration,
            code=code,
            request=request,
        )

    except Exception as exc:

        integration.status = Integration.STATUS_ERROR
        integration.last_error = str(exc)

        integration.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )

        return Response(
            {
                "success": False,
                "provider": provider,
                "message": "Unable to connect integration.",
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "success": True,
            "provider": provider,
            "integration_id": str(integration.id),
            "status": integration.status,
            "message": "Integration connected successfully.",
        }
    )

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def integration_list(request):

    company = request.user.employee.company

    if request.method == "GET":

        integrations = Integration.objects.filter(
            company=company
        ).order_by(
            "category",
            "provider",
        )

        serializer = IntegrationSerializer(
            integrations,
            many=True,
        )

        return Response({
            "success": True,
            "integrations": serializer.data,
        })

    serializer = IntegrationSerializer(
        data=request.data,
        context={
            "request": request,
        },
    )

    serializer.is_valid(
        raise_exception=True
    )

    integration = serializer.save(
        company=company,
        status=Integration.STATUS_DISCONNECTED,
    )

    return Response(
        {
            "success": True,
            "message": "Integration created successfully.",
            "integration": IntegrationSerializer(
                integration
            ).data,
        },
        status=status.HTTP_201_CREATED,
    )

@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def integration_detail(
    request,
    integration_id,
):

    company = request.user.employee.company

    integration = get_object_or_404(
        Integration,
        id=integration_id,
        company=company,
    )

    if request.method == "GET":

        serializer = IntegrationSerializer(
            integration
        )

        return Response({
            "success": True,
            "integration": serializer.data,
        })

    if request.method == "PUT":

        serializer = IntegrationSerializer(
            integration,
            data=request.data,
            partial=True,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        serializer.save()

        return Response({
            "success": True,
            "message": "Integration updated successfully.",
            "integration": serializer.data,
        })

    integration.delete()

    return Response(
        {
            "success": True,
            "message": "Integration deleted successfully.",
        },
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def integration_test_connection(
    request,
    integration_id,
):

    company = request.user.employee.company

    integration = get_object_or_404(
        Integration,
        id=integration_id,
        company=company,
    )

    try:

        connected = (
            IntegrationService.test_connection(
                integration
            )
        )

    except Exception as exc:

        integration.status = Integration.STATUS_ERROR
        integration.last_error = str(exc)

        integration.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )

        return Response(
            {
                "success": False,
                "message": "Connection test failed.",
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if connected:

        integration.status = (
            Integration.STATUS_CONNECTED
        )
        integration.last_error = None
        integration.last_synced_at = timezone.now()

        integration.save(
            update_fields=[
                "status",
                "last_error",
                "last_synced_at",
                "updated_at",
            ]
        )

        return Response({
            "success": True,
            "connected": True,
            "status": integration.status,
            "message": "Connection is working.",
        })

    integration.status = Integration.STATUS_ERROR

    integration.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    return Response({
        "success": False,
        "connected": False,
        "status": integration.status,
        "message": "Connection test failed.",
    })

from rest_framework.decorators import (
    api_view,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Integration
from .sync_service import IntegrationSyncService

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_integration(request, integration_id):

    company = request.user.employee.company

    integration = get_object_or_404(
        Integration,
        id=integration_id,
        company=company,
    )

    try:
        result = IntegrationSyncService.sync_integration(
            integration
        )

        return Response(
            result,
            status=status.HTTP_200_OK,
        )

    except Exception as exc:

        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )