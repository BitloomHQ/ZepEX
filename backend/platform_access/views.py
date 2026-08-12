from django.shortcuts import render

# Create your views here.
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

import secrets

from tenants.models import UserProfile

from .models import (
    PlatformAdmin,
    PlatformPermission,
)
from .serializers import PlatformAdminSerializer, PlatformPermissionSerializer
from .services import assign_permissions
from platform_access.decorators import (
    platform_permission_required,
)
from .permissions import get_user_profile, is_legacy_platform_owner


def _get_platform_admin_for_request(request, admin_id):
    profile = get_user_profile(request.user)
    queryset = PlatformAdmin.objects.all()
    if profile is not None and not is_legacy_platform_owner(request.user):
        queryset = queryset.filter(company=profile.company)
    return queryset.get(id=admin_id)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@platform_permission_required("create_platform_user")
def create_platform_admin(request):

    profile = getattr(request.user, "profile", None)

    if profile is None:
        return Response(
            {"error": "Platform owner accounts without a company profile cannot assign tenant platform admins."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user_id = request.data.get("user_id")
    permission_codes = request.data.get("permissions", [])

    if not user_id:
        return Response(
            {
                "error": "user_id is required."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = UserProfile.objects.get(
            id=user_id,
            company=profile.company,
        )
    except UserProfile.DoesNotExist:
        return Response(
            {
                "error": "User not found."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    platform_admin, created = PlatformAdmin.objects.get_or_create(
        user=user,
        defaults={
            "company": profile.company,
            "created_by": profile,
            "is_owner": False,
        },
    )

    assign_permissions(
        platform_admin=platform_admin,
        permission_codes=permission_codes,
    )

    serializer = PlatformAdminSerializer(platform_admin)

    return Response(
        {
            "message": (
                "Platform Admin created successfully."
                if created
                else "Platform Admin updated successfully."
            ),
            "data": serializer.data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@platform_permission_required("create_platform_user")
def create_platform_user(request):
    """
    Create a new platform staff user (email + password).

    Works for legacy PlatformOwner accounts that have no UserProfile.
    """
    email = str(request.data.get("email") or "").strip().lower()
    first_name = str(request.data.get("first_name") or "").strip()
    last_name = str(request.data.get("last_name") or "").strip()
    password = str(request.data.get("password") or "").strip()
    permission_codes = request.data.get("permissions") or []

    if not email:
        return Response(
            {"error": "email is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not first_name:
        return Response(
            {"error": "first_name is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(permission_codes, list):
        return Response(
            {"error": "permissions must be a list of permission codes."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(email__iexact=email).exists() or User.objects.filter(
        username__iexact=email
    ).exists():
        return Response(
            {"error": "A user with this email already exists."},
            status=status.HTTP_409_CONFLICT,
        )

    password_generated = False
    if not password:
        password = secrets.token_urlsafe(12)
        password_generated = True
    else:
        try:
            validate_password(password)
        except ValidationError as exc:
            return Response(
                {"error": " ".join(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    unknown_codes = []
    if permission_codes:
        known = set(
            PlatformPermission.objects.filter(
                code__in=permission_codes,
                is_active=True,
            ).values_list("code", flat=True)
        )
        unknown_codes = [code for code in permission_codes if code not in known]
        if unknown_codes:
            return Response(
                {
                    "error": "Unknown or inactive permission codes.",
                    "invalid_permissions": unknown_codes,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    creator_profile = get_user_profile(request.user)

    with transaction.atomic():
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        profile = UserProfile.objects.create(
            user=user,
            company=None,
            role="PLATFORM_ADMIN",
            temporary_password=password if password_generated else None,
            force_password_change=password_generated,
            invite_email_sent=False,
        )

        platform_admin = PlatformAdmin.objects.create(
            company=None,
            user=profile,
            is_owner=False,
            is_active=True,
            created_by=creator_profile,
        )

        assign_permissions(
            platform_admin=platform_admin,
            permission_codes=permission_codes,
        )

    serializer = PlatformAdminSerializer(platform_admin)

    return Response(
        {
            "message": "Platform user created successfully.",
            "temporary_password": password if password_generated else None,
            "password_generated": password_generated,
            "data": serializer.data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@platform_permission_required("view_platform_users")
def list_platform_permissions(request):

    permissions = PlatformPermission.objects.filter(
        is_active=True,
    ).order_by(
        "module",
        "name",
    )

    serializer = PlatformPermissionSerializer(
        permissions,
        many=True,
    )

    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@platform_permission_required("view_platform_users")
def list_platform_admins(request):

    admins = (
        PlatformAdmin.objects
        .select_related(
            "user",
            "user__user",
            "company",
        )
        .prefetch_related(
            "permissions__permission",
        )
        .order_by("-created_at")
    )

    results = list(PlatformAdminSerializer(admins, many=True).data)
    listed_emails = {
        (item.get("user_email") or "").lower()
        for item in results
    }

    from platform_management.models import PlatformOwner

    for owner in PlatformOwner.objects.select_related("user").order_by("created_at"):
        email = (owner.user.email or owner.user.username or "").lower()
        if not email or email in listed_emails:
            continue
        listed_emails.add(email)
        results.insert(
            0,
            {
                "id": f"owner-{owner.id}",
                "company": None,
                "user": owner.user_id,
                "user_name": owner.user.get_full_name() or owner.user.username,
                "user_email": owner.user.email or owner.user.username,
                "is_owner": True,
                "is_active": owner.user.is_active,
                "permissions": ["*"],
                "created_at": owner.created_at,
            },
        )

    for user in User.objects.filter(is_superuser=True, is_active=True):
        email = (user.email or user.username or "").lower()
        if not email or email in listed_emails:
            continue
        listed_emails.add(email)
        results.insert(
            0,
            {
                "id": f"superuser-{user.id}",
                "company": None,
                "user": user.id,
                "user_name": user.get_full_name() or user.username,
                "user_email": user.email or user.username,
                "is_owner": True,
                "is_active": True,
                "permissions": ["*"],
                "created_at": user.date_joined,
            },
        )

    return Response(results)

@api_view(["PUT"])
@permission_classes([IsAuthenticated])
@platform_permission_required("edit_platform_user")
def update_platform_admin(request, admin_id):

    try:
        platform_admin = _get_platform_admin_for_request(request, admin_id)

    except PlatformAdmin.DoesNotExist:
        return Response(
            {"error": "Platform Admin not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if platform_admin.is_owner:
        return Response(
            {"error": "Platform Owner cannot be edited."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    permission_codes = request.data.get("permissions", [])

    assign_permissions(
        platform_admin=platform_admin,
        permission_codes=permission_codes,
    )

    serializer = PlatformAdminSerializer(platform_admin)

    return Response(
        {
            "message": "Permissions updated successfully.",
            "data": serializer.data,
        }
    )

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@platform_permission_required("edit_platform_user")
def toggle_platform_admin(request, admin_id):

    try:
        platform_admin = _get_platform_admin_for_request(request, admin_id)

    except PlatformAdmin.DoesNotExist:
        return Response(
            {"error": "Platform Admin not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if platform_admin.is_owner:
        return Response(
            {"error": "Owner cannot be disabled."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    platform_admin.is_active = not platform_admin.is_active

    platform_admin.save(
        update_fields=[
            "is_active",
        ]
    )

    serializer = PlatformAdminSerializer(platform_admin)

    return Response(
        {
            "message": (
                "Platform Admin enabled."
                if platform_admin.is_active
                else "Platform Admin disabled."
            ),
            "data": serializer.data,
        }
    )

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@platform_permission_required("delete_platform_user")
def delete_platform_admin(request, admin_id):

    try:
        platform_admin = _get_platform_admin_for_request(request, admin_id)

    except PlatformAdmin.DoesNotExist:
        return Response(
            {"error": "Platform Admin not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if platform_admin.is_owner:
        return Response(
            {"error": "Owner cannot be deleted."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    platform_admin.delete()

    return Response(
        {
            "message": "Platform Admin deleted successfully."
        }
    )