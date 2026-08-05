from django.shortcuts import render

#m rest_framework import status
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .serializers import LoginSerializer

from tenants.role_utils import permissions_for_profile

from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives
from platform_access.models import PlatformAdmin

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import (
    urlsafe_base64_encode,
    urlsafe_base64_decode,
)
from django.utils.encoding import force_bytes, force_str

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

@api_view(["POST"])
@permission_classes([AllowAny])
def login_api(request):
    serializer = LoginSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = serializer.validated_data["user"]

    token, created = Token.objects.get_or_create(user=user)

    platform_admin = None

    # -------------------------------------------------
    # Check Platform Admin / Platform Owner
    # -------------------------------------------------

    try:
        platform_admin = (
            PlatformAdmin.objects
            .prefetch_related("permissions__permission")
            .get(
                user=user.profile,
                is_active=True,
            )
        )
    except Exception:
        platform_admin = None

    if platform_admin:

        system_role = (
            "PLATFORM_OWNER"
            if platform_admin.is_owner
            else "PLATFORM_ADMIN"
        )

        company_role = None
        company_role_id = None
        company = None
        department = None

        permissions = {
            "can_upload_receipt": False,
            "can_submit_expense": False,
            "can_approve_expense": False,
            "can_mark_paid": False,
            "can_manage_users": False,
            "can_manage_policy": False,
            "can_manage_workflow": False,
            "can_view_all_reports": False,
            "can_view_audit_logs": True,
        }

        if platform_admin.is_owner:

            platform_permissions = [
                "view_dashboard",
                "view_companies",
                "approve_company",
                "reject_company",
                "edit_company",
                "delete_company",
                "view_platform_users",
                "create_platform_user",
                "edit_platform_user",
                "delete_platform_user",
                "view_company_users",
                "create_company_user",
                "edit_company_user",
                "delete_company_user",
                "manage_departments",
                "manage_policies",
                "manage_workflow",
                "view_reports",
                "export_reports",
                "view_audit_logs",
                "manage_billing",
                "manage_settings",
            ]

        else:

            platform_permissions = list(
                platform_admin.permissions.values_list(
                    "permission__code",
                    flat=True,
                )
            )

    else:

        # -------------------------------------------------
        # Company User
        # -------------------------------------------------

        try:
            profile = user.profile

        except Exception:
            return Response(
                {
                    "error": "User profile not found."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        system_role = profile.role

        company_role = (
            profile.company_role.name
            if profile.company_role
            else None
        )

        company_role_id = (
            profile.company_role.id
            if profile.company_role
            else None
        )

        company = {
            "id": str(profile.company.id),
            "name": profile.company.name,
        }

        department = (
            {
                "id": str(profile.department.id),
                "name": profile.department.name,
            }
            if profile.department
            else None
        )

        platform_permissions = []

        if profile.role == "COMPANY_ADMIN":

            permissions = {
                "can_upload_receipt": True,
                "can_submit_expense": True,
                "can_approve_expense": True,
                "can_mark_paid": True,
                "can_manage_users": True,
                "can_manage_policy": True,
                "can_manage_workflow": True,
                "can_view_all_reports": True,
                "can_view_audit_logs": True,
            }

        else:

            permissions = {
                "can_upload_receipt": (
                    profile.company_role.can_upload_receipt
                    if profile.company_role
                    else False
                ),
                "can_submit_expense": (
                    profile.company_role.can_submit_expense
                    if profile.company_role
                    else False
                ),
                "can_approve_expense": (
                    profile.company_role.can_approve_expense
                    if profile.company_role
                    else False
                ),
                "can_mark_paid": (
                    profile.company_role.can_mark_paid
                    if profile.company_role
                    else False
                ),
                "can_manage_users": False,
                "can_manage_policy": False,
                "can_manage_workflow": False,
                "can_view_all_reports": False,
                "can_view_audit_logs": False,
            }

    redirect_map = {
        "PLATFORM_OWNER": "/platform-dashboard",
        "PLATFORM_ADMIN": "/platform-dashboard",
        "COMPANY_ADMIN": "/company-admin-dashboard",
        "EMPLOYEE": "/employee-dashboard",
        "MANAGER": "/approver-dashboard",
        "ACCOUNTS": "/payment-dashboard",
    }

    return Response(
        {
            "message": "Login successful.",
            "token": token.key,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,

                "system_role": system_role,

                "is_platform_admin": platform_admin is not None,
                "is_platform_owner": (
                    platform_admin.is_owner
                    if platform_admin
                    else False
                ),

                "platform_permissions": platform_permissions,

                "company_role": company_role,
                "company_role_id": company_role_id,

                "company": company,
                "department": department,

                "permissions": permissions,
            },
            "redirect_to": redirect_map.get(system_role),
        }
    )
from rest_framework.permissions import IsAuthenticated
from .serializers import ChangePasswordSerializer

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password_api(request):
    serializer = ChangePasswordSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = request.user

    old_password = serializer.validated_data["old_password"]
    new_password = serializer.validated_data["new_password"]

    if not user.check_password(old_password):
        return Response(
            {"error": "Old password is incorrect."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user.set_password(new_password)
    user.save()

    Token.objects.filter(user=user).delete()

    return Response({
        "message": "Password changed successfully. Please login again."
    })


import random
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.authtoken.models import Token

from .models import PasswordResetOTP
from .serializers import (
    ForgotPasswordSerializer,
    VerifyResetOTPSerializer,
    ResetPasswordSerializer,
)
from .models import PasswordResetOTP
from .serializers import (
    ForgotPasswordSerializer,
    VerifyResetOTPSerializer,
    ResetPasswordSerializer,
)

@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password_api(request):

    serializer = ForgotPasswordSerializer(data=request.data)

    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data["email"]

    try:
        user = User.objects.get(email=email)

        uid = urlsafe_base64_encode(
            force_bytes(user.pk)
        )

        token = default_token_generator.make_token(user)

        reset_link = (
            f"{settings.FRONTEND_URL}"
            f"/reset-password?uid={uid}&token={token}"
        )

        html = render_to_string(
            "emails/reset_password.html",
            {
                "user": user,
                "reset_link": reset_link,
            },
        )

        text = strip_tags(html)

        email_message = EmailMultiAlternatives(
            subject="Reset your ZepEx password",
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )

        email_message.attach_alternative(
            html,
            "text/html",
        )

        email_message.send()

    except User.DoesNotExist:
        pass

    return Response(
        {
            "message": "If the email exists, a password reset link has been sent."
        }
    )



@api_view(["POST"])
@permission_classes([AllowAny])
def reset_password_api(request):

    uid = request.data.get("uid")
    token = request.data.get("token")
    new_password = request.data.get("new_password")

    if not uid or not token or not new_password:
        return Response(
            {
                "error": "uid, token and new_password are required."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        uid = force_str(
            urlsafe_base64_decode(uid)
        )

        user = User.objects.get(pk=uid)

    except Exception:
        return Response(
            {
                "error": "Invalid reset link."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not default_token_generator.check_token(
        user,
        token,
    ):
        return Response(
            {
                "error": "Reset link is invalid or expired."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(new_password)
    user.save()

    Token.objects.filter(user=user).delete()

    return Response(
        {
            "message": "Password reset successfully. Please login again."
        }
    )


from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import parser_classes
from .serializers import EditProfileSerializer

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def profile_detail_api(request):
    """
    Return the authenticated user's profile.

    Supports:
    - Platform Owner / superuser without UserProfile
    - Company Admin
    - Employee
    - Approver
    - Accounts / Payment users
    """

    user = request.user

    profile = getattr(
        user,
        "profile",
        None,
    )

    # =========================================================
    # Platform owner / superuser
    # =========================================================

    if profile is None:
        platform_owner = getattr(
            user,
            "platform_owner",
            None,
        )

        if user.is_superuser or platform_owner:
            return Response(
                {
                    "success": True,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "full_name": (
                            user.get_full_name()
                            or user.username
                        ),
                        "role": "PLATFORM_OWNER",
                        "is_superuser": user.is_superuser,
                        "is_staff": user.is_staff,
                    },
                    "profile": None,
                    "permissions": {},
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "success": False,
                "error": "User profile is not configured.",
                "error_code": "PROFILE_NOT_FOUND",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # =========================================================
    # Company user profile
    # =========================================================

    company = getattr(
        profile,
        "company",
        None,
    )

    company_role = getattr(
        profile,
        "company_role",
        None,
    )

    department = getattr(
        profile,
        "department",
        None,
    )

    profile_picture_url = None

    if profile.profile_picture:
        try:
            profile_picture_url = (
                request.build_absolute_uri(
                    profile.profile_picture.url
                )
            )
        except ValueError:
            profile_picture_url = None

    return Response(
        {
            "success": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "full_name": (
                    user.get_full_name()
                    or user.username
                ),
                "is_superuser": user.is_superuser,
                "is_staff": user.is_staff,
            },
            "profile": {
                "role": profile.role,

                "company_role": (
                    company_role.name
                    if company_role
                    else None
                ),

                "company_role_id": (
                    str(company_role.id)
                    if company_role
                    else None
                ),

                "company": (
                    company.name
                    if company
                    else None
                ),

                "company_id": (
                    str(company.id)
                    if company
                    else None
                ),

                "department": (
                    department.name
                    if department
                    else None
                ),

                "department_id": (
                    str(department.id)
                    if department
                    else None
                ),

                "phone_number": (
                    profile.phone_number
                ),

                "address": (
                    profile.address
                ),

                "profile_picture": (
                    profile_picture_url
                ),
            },
            "permissions": (
                permissions_for_profile(
                    profile
                )
            ),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def edit_profile_api(request):
    serializer = EditProfileSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    profile = user.profile

    user.first_name = serializer.validated_data.get("first_name", user.first_name)
    user.last_name = serializer.validated_data.get("last_name", user.last_name)
    user.save(update_fields=["first_name", "last_name"])

    profile.phone_number = serializer.validated_data.get("phone_number", profile.phone_number)
    profile.address = serializer.validated_data.get("address", profile.address)

    if "profile_picture" in serializer.validated_data:
        profile.profile_picture = serializer.validated_data["profile_picture"]

    profile.save(update_fields=["phone_number", "address", "profile_picture"])

    return Response({
        "message": "Profile updated successfully."
    })