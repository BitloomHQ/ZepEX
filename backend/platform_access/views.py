from django.shortcuts import render

# Create your views here.
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@platform_permission_required("create_platform_user")
def create_platform_admin(request):

    profile = request.user.profile

    # Only Platform Owner can create Platform Admins
    

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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@platform_permission_required("view_platform_users")
def list_platform_permissions(request):

    profile = request.user.profile

    
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

    serializer = PlatformAdminSerializer(
        admins,
        many=True,
    )

    return Response(serializer.data)

@api_view(["PUT"])
@permission_classes([IsAuthenticated])
@platform_permission_required("edit_platform_user")
def update_platform_admin(request, admin_id):

    profile = request.user.profile

    try:
        platform_admin = PlatformAdmin.objects.get(
            id=admin_id,
            company=profile.company,
        )

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

    profile = request.user.profile

    try:
        platform_admin = PlatformAdmin.objects.get(
            id=admin_id,
            company=profile.company,
        )

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

    profile = request.user.profile

    try:
        platform_admin = PlatformAdmin.objects.get(
            id=admin_id,
            company=profile.company,
        )

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