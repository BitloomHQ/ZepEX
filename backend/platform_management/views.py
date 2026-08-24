import profile

from django.shortcuts import render

# Create your views here.
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import CompanyRegistrationRequest, PlatformOwner
from .serializers import CompanyRegistrationRequestSerializer
from .permissions import IsPlatformOwner

from tenants.models import Company, UserProfile
from django.contrib.auth.models import User
from tenants.permissions import IsCompanyAdmin
from tenants.models import Company
# decorators, permissions, response and status already imported above

from django.core.paginator import Paginator
from django.db.models import Q
from datetime import datetime

from tenants.models import (
    Company,
    Department,
    UserProfile,
    CompanyRole,
    CompanyPolicy,
    PolicyCategoryRule,
)

from expenses.models import ApprovalWorkflow, ApprovalWorkflowStep, ExpenseReport
from tenants.role_schema import defer_missing_company_role_fields
from tenants.serializers import (
    CompanySerializer,
    DepartmentSerializer,
    UserProfileSerializer,
    CompanyRoleSerializer,
    PolicyCategoryRuleSerializer,
)
from .serializers import CompanyRegistrationRequestSerializer, PlatformSettingsSerializer
from expenses.serializers import ApprovalWorkflowSerializer, ExpenseReportSerializer
from django.utils import timezone
from tenants.email_utils import send_company_registration_otp
from django.conf import settings
from platform_management.email_service import (
    send_company_approved_email,
    send_company_rejected_email,
)

from platform_management.domain_validator import (
    validate_registration_admin_email,
)
from platform_access.decorators import platform_permission_required
from django.db import IntegrityError, transaction
from .utils import generate_inbound_email_code
from tenants.role_utils import ensure_default_company_roles


def _resolve_platform_owner(user):
    owner = getattr(user, "platform_owner", None)
    if owner is not None:
        return owner
    return PlatformOwner.objects.order_by("id").first()


def _registration_email_validation_response(admin_email, company_domain, *, verify_domain):
    """Return a 400 Response when registration email/domain checks fail."""
    ok, message, details, error_code = validate_registration_admin_email(
        admin_email,
        company_domain,
        verify_domain=verify_domain,
    )
    if ok:
        return None

    payload = {
        "success": False,
        "error": message,
        "error_code": error_code,
    }
    if details:
        payload["details"] = details
    return Response(payload, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def create_company_request(request):

    required_fields = [
        "company_name",
        "company_domain",
        "admin_name",
        "admin_email",
        "expected_employee_count",
    ]

    for field in required_fields:
        if not request.data.get(field):
            return Response(
                {"error": f"{field} is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

    admin_email = request.data.get("admin_email", "").lower().strip()
    company_domain = request.data.get("company_domain", "").strip().lower()

    validation_error = _registration_email_validation_response(
        admin_email,
        company_domain,
        verify_domain=False,
    )
    if validation_error:
        return validation_error

    otp = request.data.get("otp", "").strip()

    try:
        company_request = CompanyRegistrationRequest.objects.get(
            admin_email__iexact=admin_email,
        )
    except CompanyRegistrationRequest.DoesNotExist:
        return Response(
            {"error": "Please request an OTP first."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if company_request.status == "APPROVED":
        return Response(
            {"error": "This email is already registered and approved."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not company_request.is_email_verified:
        if not otp:
            return Response(
                {"error": "otp is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if company_request.otp != otp:
            return Response(
                {"error": "Invalid OTP or email does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            company_request.otp_expires_at
            and company_request.otp_expires_at < timezone.now()
        ):
            return Response(
                {"error": "OTP expired. Please request a new OTP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company_request.is_email_verified = True
        company_request.email_verified_via = (
            CompanyRegistrationRequest.EMAIL_VERIFIED_VIA_EMAIL
        )

    serializer = CompanyRegistrationRequestSerializer(
        company_request,
        data=request.data,
        partial=True,
    )

    if serializer.is_valid():
        company_request.is_email_verified = True
        company_request.email_verified_via = (
            company_request.email_verified_via
            or CompanyRegistrationRequest.EMAIL_VERIFIED_VIA_EMAIL
        )
        company_request.status = "PENDING"
        company_request.otp = None
        company_request.otp_expires_at = None
        serializer.save()

        return Response(
            {
                "message": "Company registration request submitted successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST,
    )
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@platform_permission_required("view_companies")
def list_company_requests(request):

    requests_data = CompanyRegistrationRequest.objects.exclude(
        company_name="PENDING",
        company_domain="pending.com",
    ).order_by(
        "-created_at"
    )

    serializer = CompanyRegistrationRequestSerializer(
        requests_data,
        many=True
    )

    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@platform_permission_required("approve_company")
@transaction.atomic
def approve_company_request(request, request_id):

    # =========================================================
    # Lock registration request
    # =========================================================

    try:
        company_request = (
            CompanyRegistrationRequest.objects
            .select_for_update()
            .get(id=request_id)
        )

    except CompanyRegistrationRequest.DoesNotExist:
        return Response(
            {
                "success": False,
                "error": "Company registration request not found.",
                "error_code": "REGISTRATION_REQUEST_NOT_FOUND",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # =========================================================
    # Validate registration request
    # =========================================================

    if company_request.status != "PENDING":
        return Response(
            {
                "success": False,
                "error": "Only pending requests can be approved.",
                "error_code": "REQUEST_ALREADY_PROCESSED",
                "current_status": company_request.status,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    email_verified_by_admin = not company_request.is_email_verified

    company_name = str(
        company_request.company_name or ""
    ).strip()

    company_domain = str(
        company_request.company_domain or ""
    ).strip().lower()

    admin_name = str(
        company_request.admin_name or ""
    ).strip()

    admin_email = str(
        company_request.admin_email or ""
    ).strip().lower()

    reimbursement_email = str(
        company_request.reimbursement_email or ""
    ).strip().lower() or None

    if not company_name or company_name.upper() == "PENDING":
        return Response(
            {
                "success": False,
                "error": (
                    "Registration details are incomplete. "
                    "A valid company name is required."
                ),
                "error_code": "INVALID_COMPANY_NAME",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not company_domain:
        return Response(
            {
                "success": False,
                "error": "Company domain is required.",
                "error_code": "COMPANY_DOMAIN_REQUIRED",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not admin_email:
        return Response(
            {
                "success": False,
                "error": "Company admin email is required.",
                "error_code": "ADMIN_EMAIL_REQUIRED",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # =========================================================
    # Prevent duplicates
    # =========================================================

    if User.objects.filter(
        email__iexact=admin_email
    ).exists():
        return Response(
            {
                "success": False,
                "error": (
                    "A user with this admin email already exists."
                ),
                "error_code": "ADMIN_EMAIL_ALREADY_EXISTS",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if Company.objects.filter(
        domain__iexact=company_domain
    ).exists():
        return Response(
            {
                "success": False,
                "error": (
                    "A company with this domain already exists."
                ),
                "error_code": "COMPANY_DOMAIN_ALREADY_EXISTS",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if (
        reimbursement_email
        and Company.objects.filter(
            reimbursement_email__iexact=reimbursement_email
        ).exists()
    ):
        return Response(
            {
                "success": False,
                "error": (
                    "This reimbursement email is already assigned "
                    "to another company."
                ),
                "error_code": (
                    "REIMBURSEMENT_EMAIL_ALREADY_EXISTS"
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # =========================================================
    # Resolve platform owner
    # =========================================================

    platform_owner = _resolve_platform_owner(request.user)

    if platform_owner is None:
        return Response(
            {
                "success": False,
                "error": (
                    "The logged-in platform owner profile "
                    "is not configured."
                ),
                "error_code": "PLATFORM_OWNER_PROFILE_NOT_FOUND",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    temp_password = "Admin@123"

    try:
        # =====================================================
        # Create company admin user
        # =====================================================

        user = User.objects.create_user(
            username=admin_email,
            email=admin_email,
            password=temp_password,
            first_name=admin_name,
        )

        # =====================================================
        # Create company
        # =====================================================

        company = Company.objects.create(
            owner=platform_owner,
            name=company_name,
            domain=company_domain,

            # Important:
            # Blank reimbursement email must be stored as NULL,
            # not as an empty string.
            reimbursement_email=reimbursement_email,

            is_verified=True,
        )

        # =====================================================
        # Create default company roles
        # =====================================================

        ensure_default_company_roles(company)

        # =====================================================
        # Create company admin profile
        # =====================================================

        profile = UserProfile.objects.create(
            user=user,
            company=company,
            role="COMPANY_ADMIN",
            temporary_password=temp_password,
            force_password_change=True,
            invite_email_sent=False,
            invite_email_sent_at=None,
        )
        # Company admins must not receive platform-console access.
        # =====================================================
        # Mark registration request approved
        # =====================================================

        company_request.status = "APPROVED"
        company_request.is_email_verified = True
        if email_verified_by_admin:
            company_request.email_verified_via = (
                CompanyRegistrationRequest.EMAIL_VERIFIED_VIA_ADMIN
            )
        elif not company_request.email_verified_via:
            company_request.email_verified_via = (
                CompanyRegistrationRequest.EMAIL_VERIFIED_VIA_EMAIL
            )
        company_request.save(
            update_fields=[
                "status",
                "is_email_verified",
                "email_verified_via",
            ]
        )

    except IntegrityError as exc:
        # Because the API is atomic, created records are rolled back.
        transaction.set_rollback(True)

        return Response(
            {
                "success": False,
                "error": (
                    "Company approval failed because one of the "
                    "user, domain, or email values already exists."
                ),
                "error_code": "COMPANY_APPROVAL_CONFLICT",
                "details": str(exc),
            },
            status=status.HTTP_409_CONFLICT,
        )

    except Exception as exc:
        transaction.set_rollback(True)

        return Response(
            {
                "success": False,
                "error": (
                    "An unexpected error occurred while approving "
                    "the company."
                ),
                "error_code": "COMPANY_APPROVAL_FAILED",
                "details": str(exc),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # =========================================================
    # Platform receipt email
    # =========================================================

    platform_receipt_email = getattr(
        settings,
        "PLATFORM_RECEIPT_EMAIL",
        "receipts@zepex.ai",
    )

    # =========================================================
    # Send approval email
    # =========================================================

    email_sent = False
    email_error = None

    try:
        send_company_approved_email(
            company=company,
            company_request=company_request,
            temporary_password=temp_password,
            platform_receipt_email=platform_receipt_email,
        )

        profile.invite_email_sent = True
        profile.invite_email_sent_at = timezone.now()

        profile.save(
            update_fields=[
                "invite_email_sent",
                "invite_email_sent_at",
            ]
        )

        email_sent = True

    except Exception as exc:
        email_error = str(exc)

        print(
            "Company approval email failed:",
            email_error,
        )

    # =========================================================
    # Forwarding information
    # =========================================================

    forwarding_instruction = None

    if reimbursement_email:
        forwarding_instruction = (
            f"Forward all reimbursement emails from "
            f"{reimbursement_email} to "
            f"{platform_receipt_email}."
        )

    # =========================================================
    # Response
    # =========================================================

    return Response(
        {
            "success": True,
            "message": (
                "Company approved successfully. "
                "Admin email was marked as verified by platform admin."
                if email_verified_by_admin
                else "Company approved successfully."
            ),
            "admin_email": user.email,
            "temporary_password": temp_password,
            "email_verified_by_admin": email_verified_by_admin,

            "company": {
                "id": str(company.id),
                "name": company.name,
                "domain": company.domain,
                "is_verified": company.is_verified,
            },

            "company_admin": {
                "user_id": user.id,
                "profile_id": str(profile.id),
                "name": admin_name,
                "email": user.email,
                "temporary_password": temp_password,
                "force_password_change": (
                    profile.force_password_change
                ),
            },

            "reimbursement_email": (
                company.reimbursement_email
            ),

            "platform_receipt_email": (
                platform_receipt_email
            ),

            "forwarding_required": bool(
                reimbursement_email
            ),

            "forwarding_instruction": (
                forwarding_instruction
            ),

            "invite_email": {
                "sent": email_sent,
                "error": email_error,
            },

            "registration_request": {
                "id": str(company_request.id),
                "status": company_request.status,
            },
        },
        status=status.HTTP_201_CREATED,
    )
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@platform_permission_required("reject_company")
def reject_company_request(request, request_id):

    try:
        company_request = CompanyRegistrationRequest.objects.get(
            id=request_id
        )

    except CompanyRegistrationRequest.DoesNotExist:

        return Response(
            {
                "error": "Request not found"
            },
            status=status.HTTP_404_NOT_FOUND
        )

    if company_request.status != "PENDING":

        return Response(
            {
                "error": "Request already processed."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    reject_reason = request.data.get(
        "reject_reason",
        ""
    ).strip()

    if not reject_reason:

        return Response(
            {
                "error": "reject_reason is required."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    company_request.status = "REJECTED"

    company_request.reject_reason = reject_reason

    company_request.save(update_fields=[
        "status",
        "reject_reason",
    ])

    try:

        send_company_rejected_email(
            company_request=company_request
        )

    except Exception as e:

        print("Company rejection email failed:", e)

    return Response({

        "success": True,

        "message": "Company request rejected successfully.",

        "company_name": company_request.company_name,

        "admin_email": company_request.admin_email,

        "reject_reason": reject_reason,

    })

from tenants.serializers import CompanySerializer
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@platform_permission_required("view_companies")
def company_list(request):

    companies = Company.objects.filter(
        is_verified=True
    ).order_by("-created_at")

    serializer = CompanySerializer(
        companies,
        many=True
    )

    return Response({
        "count": companies.count(),
        "results": serializer.data
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@platform_permission_required("view_companies")
def pending_company_list(request):

    companies = Company.objects.filter(
        is_verified=False
    ).order_by("-created_at")

    serializer = CompanySerializer(
        companies,
        many=True
    )

    return Response({
        "count": companies.count(),
        "results": serializer.data
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@platform_permission_required("edit_company")
def update_platform_company(request, company_id):

    try:
        company = Company.objects.get(id=company_id)
    except Company.DoesNotExist:
        return Response(
            {"error": "Company not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = CompanySerializer(
        company,
        data=request.data,
        partial=True,
    )

    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer.save()

    return Response(
        {
            "success": True,
            "message": "Company details updated successfully.",
            "company": serializer.data,
        }
    )


from audit_logs.utils import create_audit_log
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@platform_permission_required("manage_companies")
def deactivate_company(request, company_id):

    try:
        company = Company.objects.get(
            id=company_id
        )

    except Company.DoesNotExist:

        return Response(
            {"error": "Company not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    company.is_active = False

    company.save(update_fields=[
        "is_active",
        "updated_at"
    ])

    create_audit_log(
        company=company,
        action="COMPANY_DEACTIVATED",
        action_by=None,
        message=f"Company {company.name} deactivated.",
        metadata={
            "company_id": str(company.id),
            "company_name": company.name,
        }
    )

    return Response({
        "message": "Company deactivated successfully."
    })

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@platform_permission_required("manage_companies")
def activate_company(request, company_id):

    try:
        company = Company.objects.get(
            id=company_id
        )

    except Company.DoesNotExist:

        return Response(
            {"error": "Company not found."
        },
        status=status.HTTP_404_NOT_FOUND
    )

    company.is_active = True

    company.save(update_fields=[
        "is_active",
        "updated_at"
    ])

    create_audit_log(
        company=company,
        action="COMPANY_ACTIVATED",
        action_by=None,
        message=f"Company {company.name} activated.",
        metadata={
            "company_id": str(company.id),
            "company_name": company.name,
        }
    )

    return Response({
        "message": "Company activated successfully."
    })
from tenants.models import Company
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@platform_permission_required("delete_company")
def delete_company(request, company_id):

    

    try:
        company = Company.objects.get(id=company_id)

    except Company.DoesNotExist:
        return Response(
            {"error": "Company not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    company_name = company.name
    company_id_value = str(company.id)

    company.delete()

    return Response({
        "message": "Company deleted successfully.",
        "deleted_company": {
            "id": company_id_value,
            "name": company_name
        }
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@platform_permission_required("view_company_details")
def platform_company_details(request, company_id):

    try:
        company = Company.objects.get(id=company_id)

    except Company.DoesNotExist:
        return Response(
            {"error": "Company not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    page = request.GET.get("page", 1)
    page_size = int(request.GET.get("page_size", 10))
    section = request.GET.get("section", "all")

    search = request.GET.get("search")
    department_id = request.GET.get("department_id")
    role = request.GET.get("role")
    company_role_id = request.GET.get("company_role_id")
    category = request.GET.get("category")
    report_status = request.GET.get("status")
    report_month = request.GET.get("month")

    def paginate_queryset(queryset, serializer_class):
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        serializer = serializer_class(
            page_obj,
            many=True,
            context={"request": request},
        )

        return {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "page_size": page_size,
            "results": serializer.data
        }

    response_data = {
        "company": CompanySerializer(company).data,
        "filters": {
            "section": section,
            "search": search,
            "department_id": department_id,
            "role": role,
            "company_role_id": company_role_id,
            "category": category,
            "page": page,
            "page_size": page_size,
        }
    }

    if section in ["all", "departments"]:
        departments = Department.objects.select_related(
            "manager__user"
        ).filter(
            company=company
        )

        if search:
            departments = departments.filter(
                name__icontains=search
            )

        departments = departments.order_by("name")

        response_data["departments"] = paginate_queryset(
            departments,
            DepartmentSerializer
        )

    if section in ["all", "employees"]:
        employees = defer_missing_company_role_fields(
            UserProfile.objects.select_related(
            "user",
            "department",
            "company_role"
        ).filter(
            company=company
        ),
            prefix="company_role__",
        )

        if search:
            employees = employees.filter(
                Q(user__first_name__icontains=search)
                |
                Q(user__last_name__icontains=search)
                |
                Q(user__email__icontains=search)
            )

        if department_id:
            employees = employees.filter(
                department_id=department_id
            )

        if role:
            employees = employees.filter(
                role=role
            )

        if company_role_id:
            employees = employees.filter(
                company_role_id=company_role_id
            )

        employees = employees.order_by("user__first_name")

        response_data["employees"] = paginate_queryset(
            employees,
            UserProfileSerializer
        )

    if section in ["all", "roles"]:
        roles = defer_missing_company_role_fields(
            CompanyRole.objects.filter(
            company=company
        )
        )

        if search:
            roles = roles.filter(
                name__icontains=search
            )

        roles = roles.order_by("name")

        response_data["roles"] = paginate_queryset(
            roles,
            CompanyRoleSerializer
        )

    if section in ["all", "policy_rules"]:
        policy, created = CompanyPolicy.objects.get_or_create(
            company=company
        )

        policy_rules = (
        PolicyCategoryRule.objects
        .select_related("company_role")
        .filter(policy=policy)
)

        if category:
            policy_rules = policy_rules.filter(
                category_name__iexact=category
            )

        if company_role_id:
            policy_rules = policy_rules.filter(
                company_role_id=company_role_id
            )

        if search:
            policy_rules = policy_rules.filter(
                Q(category_name__icontains=search)
                | Q(category_description__icontains=search)
            )

        policy_rules = policy_rules.order_by(
        "company_role__name",
        "category_name",
)

        response_data["policy_rules"] = paginate_queryset(
            policy_rules,
            PolicyCategoryRuleSerializer
        )

    if section in ["all", "workflow"]:
        workflow = ApprovalWorkflow.objects.filter(
            company=company,
            is_active=True
        ).prefetch_related(
            "steps",
            "steps__approver_role",
            "steps__department"
        ).first()

        response_data["workflow"] = (
            ApprovalWorkflowSerializer(workflow).data
            if workflow else None
        )

    if section in ["all", "reports"]:
        reports = (
            ExpenseReport.objects
            .select_related(
                "employee__user",
                "department",
            )
            .prefetch_related(
                "receipts",
                "approval_history",
            )
            .filter(company=company)
            .order_by("-month", "-submitted_at")
        )

        if search:
            reports = reports.filter(
                Q(employee__user__first_name__icontains=search)
                | Q(employee__user__last_name__icontains=search)
                | Q(employee__user__email__icontains=search)
            )

        if report_status:
            reports = reports.filter(status__iexact=report_status)

        if report_month:
            try:
                month_date = datetime.strptime(
                    report_month[:7],
                    "%Y-%m",
                ).date().replace(day=1)
                reports = reports.filter(month=month_date)
            except (TypeError, ValueError):
                pass

        response_data["reports"] = paginate_queryset(
            reports,
            ExpenseReportSerializer,
        )

    return Response(response_data)

import random
from datetime import timedelta

from django.utils import timezone
from tenants.email_utils import send_company_registration_otp


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def request_company_registration_otp(request):
    try:
        return _request_company_registration_otp(request)
    except Exception as exc:
        return Response(
            {
                "success": False,
                "error": str(exc),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _request_company_registration_otp(request):

    admin_email = request.data.get("admin_email", "").lower().strip()
    company_name = request.data.get("company_name", "").strip()
    company_domain = request.data.get("company_domain", "").strip().lower()
    admin_name = request.data.get("admin_name", "").strip()
    expected_employee_count = request.data.get("expected_employee_count")

    if not admin_email:
        return Response(
            {"error": "admin_email is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not company_name:
        return Response(
            {"error": "company_name is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not company_domain:
        return Response(
            {"error": "company_domain is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not admin_name:
        return Response(
            {"error": "admin_name is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        expected_employee_count = int(expected_employee_count)
        if expected_employee_count < 1:
            raise ValueError
    except (TypeError, ValueError):
        return Response(
            {"error": "expected_employee_count must be a positive number."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    validation_error = _registration_email_validation_response(
        admin_email,
        company_domain,
        verify_domain=getattr(settings, "VERIFY_COMPANY_EMAIL_DOMAIN", False),
    )
    if validation_error:
        return validation_error

    if CompanyRegistrationRequest.objects.filter(
        company_domain__iexact=company_domain,
    ).exclude(
        admin_email__iexact=admin_email,
    ).exists():
        return Response(
            {"error": "This company domain is already registered or pending approval."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp = str(random.randint(100000, 999999))
    reimbursement_email = f"expenses@{company_domain}"

    company_request, created = CompanyRegistrationRequest.objects.get_or_create(
        admin_email=admin_email,
        defaults={
            "company_name": company_name,
            "company_domain": company_domain,
            "admin_name": admin_name,
            "expected_employee_count": expected_employee_count,
            "reimbursement_email": reimbursement_email,
        }
    )

    if not created:
        if company_request.status == "APPROVED":
            return Response(
                {"error": "This email is already registered and approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company_request.company_name = company_name
        company_request.company_domain = company_domain
        company_request.admin_name = admin_name
        company_request.expected_employee_count = expected_employee_count
        if not company_request.reimbursement_email:
            company_request.reimbursement_email = reimbursement_email

    company_request.otp = otp
    company_request.otp_expires_at = timezone.now() + timedelta(minutes=10)
    company_request.is_email_verified = False
    company_request.email_verified_via = ""

    company_request.save()

    result = send_company_registration_otp(
        email=admin_email,
        otp=otp,
    )

    if not result.get("success"):
        return Response(
            {
                "success": False,
                "error": result.get(
                    "error",
                    "Unable to send OTP email."
                )
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response({
        "success": True,
        "message": "OTP sent successfully."
    })

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def verify_company_registration_otp(request):

    admin_email = request.data.get("admin_email", "").lower().strip()
    otp = request.data.get("otp", "").strip()

    if not admin_email:
        return Response(
            {"error": "admin_email is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not otp:
        return Response(
            {"error": "otp is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        company_request = CompanyRegistrationRequest.objects.get(
            admin_email__iexact=admin_email,
            otp=otp,
        )

    except CompanyRegistrationRequest.DoesNotExist:
        return Response(
            {"error": "Invalid OTP or email does not exist."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if company_request.otp_expires_at and company_request.otp_expires_at < timezone.now():
        return Response(
            {"error": "OTP expired. Please request a new OTP."},
            status=status.HTTP_400_BAD_REQUEST
        )

    company_request.is_email_verified = True
    company_request.email_verified_via = (
        CompanyRegistrationRequest.EMAIL_VERIFIED_VIA_EMAIL
    )
    company_request.otp = None
    company_request.otp_expires_at = None

    company_request.save(update_fields=[
        "is_email_verified",
        "email_verified_via",
        "otp",
        "otp_expires_at",
    ])

    return Response({
        "success": True,
        "message": "OTP verified successfully."
    })

from .models import PlatformSettings        


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@platform_permission_required("manage_platform_settings")
def platform_settings(request):

    settings_obj, created = PlatformSettings.objects.get_or_create(
        id=1
    )

    serializer = PlatformSettingsSerializer(settings_obj)

    return Response(serializer.data)

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@platform_permission_required("manage_platform_settings")
def update_platform_settings(request):

    settings_obj, created = PlatformSettings.objects.get_or_create(
        id=1
    )

    serializer = PlatformSettingsSerializer(
        settings_obj,
        data=request.data,
        partial=True
    )

    if serializer.is_valid():
        serializer.save()
        return Response({
            "success": True,
            "message": "Platform settings updated successfully.",
            "settings": serializer.data
        })

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )