from django.contrib.auth.models import User

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Company,
    Department,
    UserProfile,
    CompanyRole,
)

from .serializers import (
    DepartmentSerializer,
    EmployeeCreateSerializer,
    UserProfileSerializer,
    PolicyCategoryRuleSerializer,
    CompanyPolicySerializer,
)

from .models import (
    CompanyPolicy,
    PolicyCategoryRule
)
from .policy_utils import filter_admin_policy_rules

from .serializers import (
    DepartmentSerializer,
    UserProfileSerializer,
    EmployeeCreateSerializer,
    CompanyRoleSerializer,
)
from .permissions import IsCompanyAdmin
from .models import ExternalDatabaseConfig
from .serializers import ExternalDatabaseConfigSerializer

from rest_framework.permissions import (
    IsAuthenticated,
    AllowAny
)
from django.core.paginator import Paginator
from django.db.models import Q

from decimal import Decimal
from .serializers import CompanyFinanceSettingsSerializer

import secrets
import string
from django.db import transaction

from .email_utils import send_employee_invite_email
import secrets
import string

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .ai_difference_service import (
    generate_ai_difference_summary,
)
from .models import (
    PolicyVersion,
    PolicyVersionComparison,
)
from audit_logs.utils import create_audit_log

from .language_utils import (
    get_company_output_language,
)

from .policy_difference import (
    compare_policy_versions,
)

from .ai_difference_service import (
    generate_ai_difference_summary,
)


def generate_employee_password(length=12):
    alphabet = (
        string.ascii_uppercase
        + string.ascii_lowercase
        + string.digits
        + "@#$%&!"
    )

    while True:
        password = "".join(
            secrets.choice(alphabet)
            for _ in range(length)
        )

        if (
            any(c.isupper() for c in password)
            and any(c.islower() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "@#$%&!" for c in password)
        ):
            return password

@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def create_department(request):

    serializer = DepartmentSerializer(
        data=request.data,
        context={"request": request}
    )

    if not serializer.is_valid():

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    department = serializer.save(
        company=request.user.profile.company
    )

    create_audit_log(
        company=request.user.profile.company,
        action="DEPARTMENT_CREATED",
        action_by=request.user.profile,
        message=f"Created department {department.name}",
        metadata={
            "department_id": str(department.id),
            "department_name": department.name,
        }
    )

    return Response(
        {
            "message": "Department created successfully.",
            "department": DepartmentSerializer(
                department
            ).data
        },
        status=status.HTTP_201_CREATED
    )


@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def list_departments(request):

    search = request.GET.get("search")

    departments = Department.objects.select_related(
        "manager__user"
    ).filter(
        company=request.user.profile.company
    )

    if search:
        departments = departments.filter(
            name__icontains=search
        )

    departments = departments.order_by(
        "name"
    )

    page = request.GET.get("page", 1)

    paginator = Paginator(
        departments,
        10
    )

    page_obj = paginator.get_page(page)

    serializer = DepartmentSerializer(
        page_obj,
        many=True
    )

    return Response({
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "filters": {
            "search": search,
        },
        "results": serializer.data
    })

def generate_employee_password(length=10):
    alphabet = string.ascii_letters + string.digits + "@#$!"
    return "".join(secrets.choice(alphabet) for _ in range(length))



@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def create_employee(request):

    serializer = EmployeeCreateSerializer(
        data=request.data,
        context={"request": request}
    )

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    data = serializer.validated_data
    company = request.user.profile.company

    email = data["email"].lower().strip()

    raw_password = data.get("password", "").strip()

    if not raw_password:
        raw_password = generate_employee_password()

    user = User.objects.create_user(
        username=email,
        email=email,
        password=raw_password,
        first_name=data["first_name"],
        last_name=data.get("last_name", "")
    )

    department = None

    if data.get("department_id"):
        department = Department.objects.get(
            id=data["department_id"],
            company=company
        )

    company_role = None

    if data.get("company_role_id"):
        company_role = CompanyRole.objects.get(
            id=data["company_role_id"],
            company=company,
            is_active=True
        )
    else:
        from tenants.role_utils import resolve_company_role

        company_role = resolve_company_role(
            company,
            data["role"],
        )

    if not company_role and data["role"] in ("EMPLOYEE", "MANAGER", "ACCOUNTS"):
        user.delete()

        return Response(
            {
                "error": (
                    "No company role assigned. Create default roles under "
                    "Admin → Roles, then try again."
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    profile = UserProfile.objects.create(
        user=user,
        company=company,
        department=department,
        role=data["role"],
        company_role=company_role,
        temporary_password=raw_password,
        force_password_change=True,
        invite_email_sent=False,
        invite_email_sent_at=None,
    )

    email_sent = False
    email_error = None

    try:
        result = send_employee_invite_email(
            company=company,
            employee=profile,
            raw_password=raw_password,
        )

        if result.get("success"):
            email_sent = True
            profile.invite_email_sent = True
            profile.invite_email_sent_at = timezone.now()
            profile.save(update_fields=[
                "invite_email_sent",
                "invite_email_sent_at",
            ])
        else:
            email_error = result.get("error", "Invite email failed.")

    except Exception as e:
        email_error = str(e)

    create_audit_log(
        company=company,
        action="USER_CREATED",
        action_by=request.user.profile,
        message=f"Created user {profile.user.email}.",
        metadata={
            "created_user": profile.user.email,
            "role": profile.role,
            "company_role": (
                profile.company_role.name
                if profile.company_role else None
            ),
            "department": (
                profile.department.name
                if profile.department else None
            ),
            "invite_email_sent": email_sent,
            "invite_status": (
                "SENT"
                if email_sent else "FAILED"
            ),
            "email_error": email_error,
            "force_password_change": True,
        }
    )

    return Response(
        {
            "message": (
                "Employee created successfully. Invite email sent successfully."
                if email_sent
                else "Employee created successfully, but invite email failed."
            ),
            "invite_email_sent": email_sent,
            "invite_status": (
                "SENT"
                if email_sent else "FAILED"
            ),
            "email_error": email_error,
            "employee": UserProfileSerializer(
                profile,
                context={"request": request}
            ).data
        },
        status=status.HTTP_201_CREATED
    )


@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def list_employees(request):

    search = request.GET.get("search")
    department_id = request.GET.get("department_id")
    role = request.GET.get("role")
    company_role_id = request.GET.get("company_role_id")

    employees = UserProfile.objects.select_related(
        "user",
        "department",
        "company_role"
    ).filter(
        company=request.user.profile.company
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

    employees = employees.order_by(
        "user__first_name"
    )

    page = request.GET.get("page", 1)

    paginator = Paginator(
        employees,
        10
    )

    page_obj = paginator.get_page(page)

    serializer = UserProfileSerializer(
        page_obj,
        many=True,
        context={"request": request},
    )

    return Response({
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "filters": {
            "search": search,
            "department_id": department_id,
            "role": role,
            "company_role_id": company_role_id,
        },
        "results": serializer.data
    })


@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def assign_missing_company_roles_view(request):
    from tenants.role_utils import assign_missing_company_roles

    company = request.user.profile.company
    updated_count = assign_missing_company_roles(company)

    return Response({
        "message": f"Assigned default company roles to {updated_count} user(s).",
        "updated_count": updated_count,
    })


@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def assign_manager(request):

    department_id = request.data.get(
        "department_id"
    )

    manager_id = request.data.get(
        "manager_id"
    )

    if not department_id or not manager_id:

        return Response(
            {
                "error": "department_id and manager_id are required."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:

        department = Department.objects.get(
            id=department_id,
            company=request.user.profile.company
        )

    except Department.DoesNotExist:

        return Response(
            {
                "error": "Department not found."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    try:

        manager = UserProfile.objects.get(
            id=manager_id,
            company=request.user.profile.company,
            role="MANAGER"
        )

    except UserProfile.DoesNotExist:

        return Response(
            {
                "error": "Manager not found."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    department.manager = manager
    department.save()

    return Response(
        {
            "message": "Manager assigned successfully.",
            "department": department.name,
            "manager": manager.user.email
        },
        status=status.HTTP_200_OK
    )

@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def save_database_config(request):

    company = request.user.profile.company

    try:
        config = ExternalDatabaseConfig.objects.get(
            company=company
        )

        serializer = ExternalDatabaseConfigSerializer(
            config,
            data=request.data,
            partial=True
        )

    except ExternalDatabaseConfig.DoesNotExist:

        serializer = ExternalDatabaseConfigSerializer(
            data=request.data
        )

    if serializer.is_valid():

        serializer.save(company=company)

        return Response(
            {
                "message": "Database configuration saved successfully.",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )

@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def get_database_config(request):

    company = request.user.profile.company

    try:

        config = ExternalDatabaseConfig.objects.get(
            company=company
        )

    except ExternalDatabaseConfig.DoesNotExist:

        return Response(
            {
                "message": "Database configuration not found."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = ExternalDatabaseConfigSerializer(
        config
    )

    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def create_company_policy(request):

    company = request.user.profile.company

    policy, created = CompanyPolicy.objects.get_or_create(
        company=company
    )

    serializer = CompanyPolicySerializer(
        policy
    )

    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def create_policy_rule(request):

    company = request.user.profile.company

    policy, created = CompanyPolicy.objects.get_or_create(
        company=company
    )

    _version_rules, active_version = filter_admin_policy_rules(policy)

    serializer = PolicyCategoryRuleSerializer(
        data=request.data,
        context={
            "policy": policy,
            "policy_version": active_version,
        },
    )

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    company_role = serializer.validated_data.get(
        "company_role"
    )

    if not company_role:
        return Response(
            {
                "error": "company_role is required."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if company_role.company != company:
        return Response(
            {
                "error": "Selected role does not belong to your company."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if not company_role.is_active:
        return Response(
            {
                "error": "Selected company role is inactive."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    category_name = serializer.validated_data["category_name"]

    version_rules, active_version = filter_admin_policy_rules(policy)

    if version_rules.filter(
        company_role=company_role,
        category_name__iexact=category_name,
    ).exists():

        return Response(
            {
                "error": (
                    f"A policy for category '{category_name}' "
                    f"already exists for role '{company_role.name}'."
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    rule = serializer.save(
        policy=policy,
        policy_version=active_version,
    )

    create_audit_log(
        company=company,
        action="POLICY_RULE_CREATED",
        action_by=request.user.profile,
        message=(
            f"Created '{rule.category_name}' policy "
            f"for role '{rule.company_role.name}'."
        ),
        metadata={
            "rule_id": str(rule.id),
            "company_role": rule.company_role.name,
            "category_name": rule.category_name,
            "max_amount": str(rule.max_amount),
            "is_active": rule.is_active,
        }
    )

    return Response(
        {
            "message": "Policy rule created successfully.",
            "rule": PolicyCategoryRuleSerializer(rule).data,
        },
        status=status.HTTP_201_CREATED
    )

@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def list_policy_rules(request):

    company = request.user.profile.company

    search = request.GET.get("search")
    category = request.GET.get("category")
    company_role_id = request.GET.get("company_role_id")
    page = request.GET.get("page", 1)

    policy, created = CompanyPolicy.objects.get_or_create(
        company=company
    )

    rules = PolicyCategoryRule.objects.select_related(
        "company_role"
    ).filter(
        policy=policy
    )
    rules, _active_version = filter_admin_policy_rules(policy, rules)

    if company_role_id:
        rules = rules.filter(
            company_role_id=company_role_id
        )

    if category:
        rules = rules.filter(
            category_name__iexact=category
        )

    if search:
        rules = rules.filter(
            Q(category_name__icontains=search)
            | Q(category_description__icontains=search)
            | Q(company_role__name__icontains=search)
        )

    rules = rules.order_by(
        "company_role__name",
        "category_name"
    )

    paginator = Paginator(
        rules,
        10
    )

    page_obj = paginator.get_page(page)

    serializer = PolicyCategoryRuleSerializer(
        page_obj,
        many=True
    )

    return Response({
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "filters": {
            "search": search,
            "category": category,
            "company_role_id": company_role_id,
        },
        "results": serializer.data
    })

from .serializers import ReimbursementEmailConfigSerializer

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def get_reimbursement_email_config(request):
    company = request.user.profile.company

    platform_receipt_email = getattr(
        settings,
        "PLATFORM_RECEIPT_EMAIL",
        "receipts@zepex.ai"
    )

    return Response({
        "success": True,
        "data": {
            "company_name": company.name,
            "reimbursement_email": company.reimbursement_email,
            "platform_receipt_email": platform_receipt_email,
            "forwarding_instruction": (
                f"Forward all reimbursement emails from "
                f"{company.reimbursement_email or 'your company reimbursement email'} "
                f"to {platform_receipt_email}"
            ),
            "imap_required": False,
            "imap_removed": True
        }
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def save_reimbursement_email_config(request):
    company = request.user.profile.company

    reimbursement_email = request.data.get(
        "reimbursement_email",
        ""
    ).lower().strip()

    if not reimbursement_email:
        return Response(
            {
                "error": "reimbursement_email is required."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    company.reimbursement_email = reimbursement_email

    company.save(update_fields=[
        "reimbursement_email",
        "updated_at"
    ])

    platform_receipt_email = getattr(
        settings,
        "PLATFORM_RECEIPT_EMAIL",
        "receipts@zepex.ai"
    )

    return Response({
        "success": True,
        "message": "Reimbursement email saved successfully.",
        "data": {
            "company_name": company.name,
            "reimbursement_email": company.reimbursement_email,
            "platform_receipt_email": platform_receipt_email,
            "forwarding_instruction": (
                f"Forward all reimbursement emails from "
                f"{company.reimbursement_email} "
                f"to {platform_receipt_email}"
            ),
            "imap_required": False,
            "imap_removed": True
        }
    })



from .serializers import CompanySMTPConfigSerializer

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def get_smtp_config(request):
    return Response({
        "success": True,
        "message": "Company SMTP configuration is no longer required.",
        "data": {
            "smtp_source": "PLATFORM_ENV",
            "company_smtp_required": False,
            "company_smtp_removed": True,
            "from_email": getattr(
                settings,
                "DEFAULT_FROM_EMAIL",
                getattr(settings, "EMAIL_HOST_USER", "")
            )
        }
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def get_smtp_config(request):
    return Response({
        "success": True,
        "message": "Company SMTP configuration is no longer required.",
        "data": {
            "smtp_source": "PLATFORM_ENV",
            "company_smtp_required": False,
            "company_smtp_removed": True,
            "from_email": getattr(
                settings,
                "DEFAULT_FROM_EMAIL",
                getattr(settings, "EMAIL_HOST_USER", "")
            )
        }
    })

from django.contrib.auth.models import User
from .serializers import CompanyUserUpdateSerializer


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def edit_company_user(request, user_id):
    company = request.user.profile.company

    try:
        profile = UserProfile.objects.select_related("user").get(
            id=user_id,
            company=company
        )
    except UserProfile.DoesNotExist:
        return Response(
            {"error": "User not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = CompanyUserUpdateSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    user = profile.user

    user.first_name = data.get("first_name", user.first_name)
    user.last_name = data.get("last_name", user.last_name)
    user.save(update_fields=["first_name", "last_name"])

    if "role" in data:
        profile.role = data["role"]

    if "department_id" in data:
        department_id = data["department_id"]

        if department_id is None:
            profile.department = None
        else:
            try:
                department = Department.objects.get(
                    id=department_id,
                    company=company
                )
                profile.department = department
            except Department.DoesNotExist:
                return Response(
                    {"error": "Department not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

    profile.phone_number = data.get("phone_number", profile.phone_number)
    profile.address = data.get("address", profile.address)

    profile.save()

    return Response({
        "message": "User updated successfully.",
        "user": {
            "profile_id": str(profile.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": profile.role,
            "department": profile.department.name if profile.department else None,
            "phone_number": profile.phone_number,
            "address": profile.address,
            "is_active": user.is_active,
        }
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def deactivate_company_user(request, user_id):
    company = request.user.profile.company

    try:
        profile = UserProfile.objects.select_related("user").get(
            id=user_id,
            company=company
        )
    except UserProfile.DoesNotExist:
        return Response(
            {"error": "User not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    profile.user.is_active = False
    profile.user.save(update_fields=["is_active"])

    return Response({
        "message": "User deactivated successfully."
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def activate_company_user(request, user_id):
    company = request.user.profile.company

    try:
        profile = UserProfile.objects.select_related("user").get(
            id=user_id,
            company=company
        )
    except UserProfile.DoesNotExist:
        return Response(
            {"error": "User not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    profile.user.is_active = True
    profile.user.save(update_fields=["is_active"])

    return Response({
        "message": "User activated successfully."
    })

from django.contrib.auth.models import User

from audit_logs.utils import create_audit_log

from .serializers import CompanyUserUpdateSerializer


def active_company_admin_count(company):
    return UserProfile.objects.filter(
        company=company,
        role="COMPANY_ADMIN",
        user__is_active=True,
    ).count()


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def edit_company_user(request, user_id):

    company = request.user.profile.company

    try:
        profile = UserProfile.objects.select_related(
            "user",
            "department",
            "company_role"
        ).get(
            id=user_id,
            company=company
        )

    except UserProfile.DoesNotExist:

        return Response(
            {"error": "User not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = CompanyUserUpdateSerializer(
        data=request.data,
        context={
            "request": request,
            "profile_id": profile.id,
            "user_id": profile.user_id,
            "profile_role": profile.role,
        },
    )

    if not serializer.is_valid():

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    data = serializer.validated_data

    if profile.user == request.user and "role" in data:

        return Response(
            {"error": "You cannot change your own system role."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if (
        profile.role == "COMPANY_ADMIN"
        and "role" in data
        and data["role"] != "COMPANY_ADMIN"
        and active_company_admin_count(company) <= 1
    ):
        return Response(
            {"error": "Cannot change role of the only company admin."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = profile.user

    user.first_name = data.get(
        "first_name",
        user.first_name
    )

    user.last_name = data.get(
        "last_name",
        user.last_name
    )

    update_user_fields = ["first_name", "last_name"]

    if "email" in data:
        user.email = data["email"]
        user.username = data["email"]
        update_user_fields.extend(["email", "username"])

    user.save(update_fields=update_user_fields)

    if "role" in data:
        profile.role = data["role"]
        if data["role"] == "COMPANY_ADMIN":
            profile.company_role = None
            profile.department = None

    effective_role = data.get("role", profile.role)

    if "department_id" in data and effective_role != "COMPANY_ADMIN":

        department_id = data["department_id"]

        if department_id is None:
            profile.department = None

        else:
            department = Department.objects.get(
                id=department_id,
                company=company,
                is_active=True
            )

            profile.department = department

    if "company_role_id" in data:

        company_role_id = data["company_role_id"]

        if company_role_id is None:
            profile.company_role = None

        else:
            company_role = CompanyRole.objects.get(
                id=company_role_id,
                company=company,
                is_active=True
            )

            profile.company_role = company_role

    profile.phone_number = data.get(
        "phone_number",
        profile.phone_number
    )

    profile.address = data.get(
        "address",
        profile.address
    )

    profile.save()

    create_audit_log(
        company=company,
        action="USER_UPDATED",
        action_by=request.user.profile,
        message=f"Updated user {profile.user.email}",
        metadata={
            "updated_user": profile.user.email,
            "role": profile.role,
            "company_role": (
                profile.company_role.name
                if profile.company_role else None
            ),
            "department": (
                profile.department.name
                if profile.department else None
            ),
        }
    )

    return Response({
        "message": "User updated successfully.",
        "user": {
            "profile_id": str(profile.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": profile.role,
            "company_role": (
                profile.company_role.name
                if profile.company_role else None
            ),
            "company_role_id": (
                profile.company_role.id
                if profile.company_role else None
            ),
            "department": (
                profile.department.name
                if profile.department else None
            ),
            "department_id": (
                str(profile.department.id)
                if profile.department else None
            ),
            "phone_number": profile.phone_number,
            "address": profile.address,
            "is_active": user.is_active,
        }
    })
@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def deactivate_company_user(request, user_id):

    company = request.user.profile.company

    try:
        profile = UserProfile.objects.select_related(
            "user"
        ).get(
            id=user_id,
            company=company
        )

    except UserProfile.DoesNotExist:

        return Response(
            {"error": "User not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if profile.user == request.user:

        return Response(
            {"error": "You cannot deactivate your own account."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if profile.role == "COMPANY_ADMIN" and active_company_admin_count(company) <= 1:
        return Response(
            {"error": "Cannot deactivate the only company admin."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    profile.user.is_active = False

    profile.user.save(update_fields=["is_active"])

    create_audit_log(
        company=company,
        action="USER_DEACTIVATED",
        action_by=request.user.profile,
        message=f"Deactivated user {profile.user.email}",
        metadata={
            "deactivated_user": profile.user.email,
        }
    )

    return Response({
        "message": "User deactivated successfully."
    })

@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def activate_company_user(request, user_id):

    company = request.user.profile.company

    try:
        profile = UserProfile.objects.select_related(
            "user"
        ).get(
            id=user_id,
            company=company
        )

    except UserProfile.DoesNotExist:

        return Response(
            {"error": "User not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    profile.user.is_active = True

    profile.user.save(update_fields=["is_active"])

    create_audit_log(
        company=company,
        action="USER_ACTIVATED",
        action_by=request.user.profile,
        message=f"Activated user {profile.user.email}",
        metadata={
            "activated_user": profile.user.email,
        }
    )

    return Response({
        "message": "User activated successfully."
    })

from .serializers import DepartmentUpdateSerializer
@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def update_department(request, department_id):
    company = request.user.profile.company

    try:
        department = Department.objects.get(
            id=department_id,
            company=company
        )
    except Department.DoesNotExist:
        return Response(
            {"error": "Department not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = DepartmentUpdateSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    if "name" in data:
        department.name = data["name"]

    if "manager_id" in data:
        manager_id = data["manager_id"]

        if manager_id is None:
            department.manager = None
        else:
            try:
                manager = UserProfile.objects.get(
                    id=manager_id,
                    company=company,
                    role="MANAGER",
                    user__is_active=True
                )
            except UserProfile.DoesNotExist:
                return Response(
                    {"error": "Active manager not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            department.manager = manager

            UserProfile.objects.filter(
                company=company,
                department=department,
                role="MANAGER"
            ).exclude(id=manager.id).update(role="EMPLOYEE")

            manager.department = department
            manager.role = "MANAGER"
            manager.save(update_fields=["department", "role"])

    department.save()

    create_audit_log(
        company=company,
        action="DEPARTMENT_UPDATED",
        action_by=request.user.profile,
        message=f"Updated department {department.name}",
        metadata={
            "department_id": str(department.id),
            "department_name": department.name,
            "manager_email": department.manager.user.email if department.manager else None,
        }
    )

    return Response({
        "message": "Department updated successfully.",
        "department": {
            "id": str(department.id),
            "name": department.name,
            "manager": str(department.manager.id) if department.manager else None,
            "manager_email": department.manager.user.email if department.manager else None,
            "is_active": department.is_active,
        }
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def deactivate_department(request, department_id):
    company = request.user.profile.company

    try:
        department = Department.objects.get(
            id=department_id,
            company=company
        )
    except Department.DoesNotExist:
        return Response(
            {"error": "Department not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if department.employees.filter(user__is_active=True).exists():
        return Response(
            {
                "error": "Cannot deactivate department with active users. Move or deactivate users first."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    department.is_active = False
    department.save(update_fields=["is_active", "updated_at"])

    create_audit_log(
        company=company,
        action="DEPARTMENT_DEACTIVATED",
        action_by=request.user.profile,
        message=f"Deactivated department {department.name}",
        metadata={
            "department_id": str(department.id),
            "department_name": department.name,
        }
    )

    return Response({
        "message": "Department deactivated successfully."
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def activate_department(request, department_id):
    company = request.user.profile.company

    try:
        department = Department.objects.get(
            id=department_id,
            company=company
        )
    except Department.DoesNotExist:
        return Response(
            {"error": "Department not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    department.is_active = True
    department.save(update_fields=["is_active", "updated_at"])

    create_audit_log(
        company=company,
        action="DEPARTMENT_ACTIVATED",
        action_by=request.user.profile,
        message=f"Activated department {department.name}",
        metadata={
            "department_id": str(department.id),
            "department_name": department.name,
        }
    )

    return Response({
        "message": "Department activated successfully."
    })

@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def update_policy_rule(request, rule_id):

    company = request.user.profile.company

    try:
        rule = PolicyCategoryRule.objects.select_related(
            "company_role"
        ).get(
            id=rule_id,
            policy__company=company
        )

    except PolicyCategoryRule.DoesNotExist:
        return Response(
            {
                "error": "Policy rule not found."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = PolicyCategoryRuleSerializer(
    rule,
    data=request.data,
    partial=True,
    context={
        "policy": rule.policy
    }
)

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    company_role = serializer.validated_data.get("company_role")

    if company_role and company_role.company != company:
        return Response(
            {
                "error": "Selected company role does not belong to your company."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    rule = serializer.save()

    create_audit_log(
        company=company,
        action="POLICY_RULE_UPDATED",
        action_by=request.user.profile,
        message=(
            f"Updated policy rule '{rule.category_name}' "
            f"for role '{rule.company_role.name}'."
        ),
        metadata={
            "rule_id": str(rule.id),
            "company_role": (
                rule.company_role.name
                if rule.company_role else None
            ),
            "category_name": rule.category_name,
            "max_amount": str(rule.max_amount),
            "is_active": rule.is_active,
        }
    )

    return Response({
        "message": "Policy rule updated successfully.",
        "rule": PolicyCategoryRuleSerializer(rule).data
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def deactivate_policy_rule(request, rule_id):

    company = request.user.profile.company

    try:
        rule = PolicyCategoryRule.objects.select_related(
            "company_role"
        ).get(
            id=rule_id,
            policy__company=company
        )

    except PolicyCategoryRule.DoesNotExist:
        return Response(
            {"error": "Policy rule not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    rule.is_active = False
    rule.save(update_fields=["is_active", "updated_at"])

    create_audit_log(
        company=company,
        action="POLICY_RULE_DEACTIVATED",
        action_by=request.user.profile,
        message=(
            f"Deactivated policy rule '{rule.category_name}' "
            f"for role '{rule.company_role.name}'."
        ),
        metadata={
            "rule_id": str(rule.id),
            "company_role": rule.company_role.name,
            "category_name": rule.category_name,
            "max_amount": str(rule.max_amount),
            "is_active": rule.is_active,
        }
    )

    return Response({
        "message": "Policy rule deactivated successfully.",
        "rule": PolicyCategoryRuleSerializer(rule).data
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def activate_policy_rule(request, rule_id):

    company = request.user.profile.company

    try:
        rule = PolicyCategoryRule.objects.select_related(
            "company_role"
        ).get(
            id=rule_id,
            policy__company=company
        )

    except PolicyCategoryRule.DoesNotExist:
        return Response(
            {"error": "Policy rule not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    rule.is_active = True
    rule.save(update_fields=["is_active", "updated_at"])

    create_audit_log(
        company=company,
        action="POLICY_RULE_ACTIVATED",
        action_by=request.user.profile,
        message=(
            f"Activated policy rule '{rule.category_name}' "
            f"for role '{rule.company_role.name}'."
        ),
        metadata={
            "rule_id": str(rule.id),
            "company_role": rule.company_role.name,
            "category_name": rule.category_name,
            "max_amount": str(rule.max_amount),
            "is_active": rule.is_active,
        }
    )

    return Response({
        "message": "Policy rule activated successfully.",
        "rule": PolicyCategoryRuleSerializer(rule).data
    })

@api_view(["DELETE"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def delete_company_user(request, user_id):

    company = request.user.profile.company

    try:
        profile = UserProfile.objects.select_related(
            "user"
        ).get(
            id=user_id,
            company=company
        )

    except UserProfile.DoesNotExist:

        return Response(
            {"error": "User not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if profile.user == request.user:

        return Response(
            {"error": "You cannot delete your own account."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if profile.role == "COMPANY_ADMIN" and active_company_admin_count(company) <= 1:
        return Response(
            {"error": "Cannot delete the only company admin."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = profile.user.email

    profile.user.delete()

    create_audit_log(
        company=company,
        action="USER_DELETED",
        action_by=request.user.profile,
        message=f"Deleted user {email}",
        metadata={
            "deleted_user": email,
        }
    )

    return Response({
        "message": "User deleted successfully."
    })    

@api_view(["DELETE"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def delete_department(request, department_id):

    company = request.user.profile.company

    try:
        department = Department.objects.get(
            id=department_id,
            company=company
        )

    except Department.DoesNotExist:

        return Response(
            {"error": "Department not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    active_users = department.employees.filter(
        user__is_active=True
    ).exists()

    if active_users:

        return Response(
            {
                "error": "Cannot delete department with active users."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    department_name = department.name

    department.delete()

    create_audit_log(
        company=company,
        action="DEPARTMENT_DELETED",
        action_by=request.user.profile,
        message=f"Deleted department {department_name}",
        metadata={
            "department_name": department_name,
        }
    )

    return Response({
        "message": "Department deleted successfully."
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_company_role(request):

    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can create roles."},
            status=status.HTTP_403_FORBIDDEN
        )

    serializer = CompanyRoleSerializer(
        data=request.data,
        context={"request": request}
    )

    if serializer.is_valid():

        serializer.save(
            company=profile.company
        )

        return Response(
            {
                "message": "Role created successfully.",
                "role": serializer.data
            },
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def company_roles(request):

    profile = request.user.profile

    search = request.GET.get("search")
    can_approve_expense = request.GET.get("can_approve_expense")

    roles = CompanyRole.objects.filter(
        company=profile.company,
        is_active=True
    )

    if search:
        roles = roles.filter(
            Q(name__icontains=search)
        )

    if can_approve_expense:
        roles = roles.filter(
            can_approve_expense=
            can_approve_expense.lower() == "true"
        )

    roles = roles.order_by("name")

    page = request.GET.get("page", 1)

    paginator = Paginator(roles, 10)

    page_obj = paginator.get_page(page)

    serializer = CompanyRoleSerializer(
        page_obj,
        many=True
    )

    return Response({
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "filters": {
            "search": search,
            "can_approve_expense": can_approve_expense,
        },
        "results": serializer.data
    })

@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_company_role(request, role_id):

    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can update roles."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        role = CompanyRole.objects.get(
            id=role_id,
            company=profile.company
        )

    except CompanyRole.DoesNotExist:

        return Response(
            {"error": "Role not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = CompanyRoleSerializer(
        role,
        data=request.data,
        partial=True,
        context={"request": request}
    )

    if serializer.is_valid():

        serializer.save()

        return Response({
            "message": "Role updated successfully.",
            "role": serializer.data
        })

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def deactivate_company_role(request, role_id):

    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can deactivate roles."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        role = CompanyRole.objects.get(
            id=role_id,
            company=profile.company
        )

    except CompanyRole.DoesNotExist:

        return Response(
            {"error": "Role not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    role.is_active = False
    role.save(update_fields=["is_active"])

    return Response({
        "message": "Role deactivated successfully."
    })

import psycopg2
import pymysql
import pyodbc
import oracledb

@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def test_database_connection(request):
    company = request.user.profile.company

    try:
        config = ExternalDatabaseConfig.objects.get(company=company)
    except ExternalDatabaseConfig.DoesNotExist:
        return Response(
            {"error": "Database configuration not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        if config.db_engine == "postgresql":
            conn = psycopg2.connect(
                host=config.db_host,
                port=config.db_port,
                dbname=config.db_name,
                user=config.db_user,
                password=config.db_password,
                connect_timeout=10,
            )

        elif config.db_engine == "mysql":
            conn = pymysql.connect(
                host=config.db_host,
                port=config.db_port,
                database=config.db_name,
                user=config.db_user,
                password=config.db_password,
                connect_timeout=10,
            )

        elif config.db_engine == "mssql":
            conn = pyodbc.connect(
                (
                    "DRIVER={ODBC Driver 17 for SQL Server};"
                    f"SERVER={config.db_host},{config.db_port};"
                    f"DATABASE={config.db_name};"
                    f"UID={config.db_user};"
                    f"PWD={config.db_password};"
                    "TrustServerCertificate=yes;"
                ),
                timeout=10
            )

        elif config.db_engine == "oracle":
            dsn = oracledb.makedsn(
                config.db_host,
                config.db_port,
                service_name=config.db_name
            )

            conn = oracledb.connect(
                user=config.db_user,
                password=config.db_password,
                dsn=dsn
            )

        else:
            return Response(
                {"error": "Unsupported database engine."},
                status=status.HTTP_400_BAD_REQUEST
            )

        conn.close()

        create_audit_log(
            company=company,
            action="DATABASE_CONNECTED",
            action_by=request.user.profile,
            message="External database connection tested successfully.",
            metadata={
                "db_engine": config.db_engine,
                "db_host": config.db_host,
                "db_name": config.db_name,
            }
        )

        return Response({
            "success": True,
            "message": "Database connection successful.",
            "db_engine": config.db_engine
        })

    except Exception as e:
        create_audit_log(
            company=company,
            action="DATABASE_CONNECTION_FAILED",
            action_by=request.user.profile,
            message="External database connection failed.",
            metadata={
                "db_engine": config.db_engine,
                "error": str(e),
            }
        )

        return Response(
            {
                "success": False,
                "error": str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
from django.utils import timezone
from .models import DatabaseSyncLog

def get_external_db_connection(config):
    if config.db_engine == "postgresql":
        return psycopg2.connect(
            host=config.db_host,
            port=config.db_port,
            dbname=config.db_name,
            user=config.db_user,
            password=config.db_password,
            connect_timeout=10,
        )

    if config.db_engine == "mysql":
        return pymysql.connect(
            host=config.db_host,
            port=config.db_port,
            database=config.db_name,
            user=config.db_user,
            password=config.db_password,
            connect_timeout=10,
        )

    if config.db_engine == "mssql":
        return pyodbc.connect(
            (
                "DRIVER={ODBC Driver 17 for SQL Server};"
                f"SERVER={config.db_host},{config.db_port};"
                f"DATABASE={config.db_name};"
                f"UID={config.db_user};"
                f"PWD={config.db_password};"
                "TrustServerCertificate=yes;"
            ),
            timeout=10
        )

    if config.db_engine == "oracle":
        dsn = oracledb.makedsn(
            config.db_host,
            config.db_port,
            service_name=config.db_name
        )

        return oracledb.connect(
            user=config.db_user,
            password=config.db_password,
            dsn=dsn
        )

    raise Exception("Unsupported database engine.")

from tenants.services import sync_company_external_database

@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def sync_external_database(request):

    result = sync_company_external_database(
        company=request.user.profile.company,
        action_by=request.user.profile
    )

    if result["success"]:
        return Response(result)

    return Response(
        result,
        status=status.HTTP_400_BAD_REQUEST
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def database_sync_status(request):

    company = request.user.profile.company

    latest_log = DatabaseSyncLog.objects.filter(
        company=company
    ).order_by("-started_at").first()

    try:
        config = ExternalDatabaseConfig.objects.get(company=company)
        last_synced_at = config.last_synced_at
    except ExternalDatabaseConfig.DoesNotExist:
        last_synced_at = None

    if not latest_log:
        return Response({
            "last_synced_at": last_synced_at,
            "latest_sync": None
        })

    return Response({
        "last_synced_at": last_synced_at,
        "latest_sync": {
            "status": latest_log.status,
            "records_created": latest_log.records_created,
            "records_updated": latest_log.records_updated,
            "error_message": latest_log.error_message,
            "started_at": latest_log.started_at,
            "completed_at": latest_log.completed_at,
        }
    })    

from .serializers import DatabaseSyncLogSerializer
from .models import DatabaseSyncLog


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def database_sync_logs(request):

    company = request.user.profile.company

    logs = DatabaseSyncLog.objects.filter(
        company=company
    ).order_by("-started_at")

    status_filter = request.GET.get("status")

    if status_filter:
        logs = logs.filter(status=status_filter.upper())

    serializer = DatabaseSyncLogSerializer(
        logs,
        many=True
    )

    return Response({
        "count": logs.count(),
        "results": serializer.data
    })

from django.db.models import Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tenants.permissions import IsCompanyAdmin
from tenants.models import DatabaseSyncLog


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def database_sync_dashboard(request):

    company = request.user.profile.company

    logs = DatabaseSyncLog.objects.filter(
        company=company
    )

    latest_sync = logs.order_by("-started_at").first()

    successful_syncs = logs.filter(
        status=DatabaseSyncLog.STATUS_SUCCESS
    )

    failed_syncs = logs.filter(
        status=DatabaseSyncLog.STATUS_FAILED
    )

    total_records_created = logs.aggregate(
        total=Sum("records_created")
    )["total"] or 0

    total_records_updated = logs.aggregate(
        total=Sum("records_updated")
    )["total"] or 0

    return Response({
        "metrics": {
            "total_syncs": logs.count(),
            "successful_syncs": successful_syncs.count(),
            "failed_syncs": failed_syncs.count(),
            "total_records_created": total_records_created,
            "total_records_updated": total_records_updated,
        },

        "latest_sync": {
            "id": str(latest_sync.id),
            "status": latest_sync.status,
            "records_created": latest_sync.records_created,
            "records_updated": latest_sync.records_updated,
            "error_message": latest_sync.error_message,
            "started_at": latest_sync.started_at,
            "completed_at": latest_sync.completed_at,
        } if latest_sync else None,

        "recent_syncs": [
            {
                "id": str(log.id),
                "status": log.status,
                "records_created": log.records_created,
                "records_updated": log.records_updated,
                "error_message": log.error_message,
                "started_at": log.started_at,
                "completed_at": log.completed_at,
            }
            for log in logs.order_by("-started_at")[:10]
        ]
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def assign_missing_company_roles_view(request):
    return Response({
        "message": "Assign missing company roles API is not implemented yet."
    })


import csv
import io

from rest_framework.parsers import MultiPartParser

@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def import_departments(request):

    profile = request.user.profile

    file = request.FILES.get("file")

    if not file:
        return Response(
            {"error": "CSV file is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        decoded_file = file.read().decode("utf-8")

        csv_data = csv.DictReader(
            io.StringIO(decoded_file)
        )

        created_count = 0
        skipped_count = 0
        errors = []

        for row_number, row in enumerate(csv_data, start=2):

            name = (
                row.get("name", "")
                .strip()
            )

            if not name:
                errors.append({
                    "row": row_number,
                    "message": "Department name is required."
                })
                continue

            exists = Department.objects.filter(
                company=profile.company,
                name__iexact=name
            ).exists()

            if exists:
                skipped_count += 1
                continue

            Department.objects.create(
                company=profile.company,
                name=name
            )

            created_count += 1

        create_audit_log(
            company=profile.company,
            action="DEPARTMENT_IMPORT",
            action_by=profile,
            message="Departments imported.",
            metadata={
                "created": created_count,
                "skipped": skipped_count,
                "errors": len(errors),
            }
        )

        return Response({
            "success": True,
            "created": created_count,
            "skipped": skipped_count,
            "errors": errors,
        })

    except Exception as e:

        return Response(
            {
                "success": False,
                "error": str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    

@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def import_company_roles(request):

    profile = request.user.profile

    file = request.FILES.get("file")

    if not file:
        return Response(
            {"error": "CSV file is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        decoded_file = file.read().decode("utf-8")

        csv_data = csv.DictReader(
            io.StringIO(decoded_file)
        )

        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        def to_bool(value):
            return str(value).strip().lower() in [
                "true",
                "1",
                "yes",
                "y"
            ]

        for row_number, row in enumerate(csv_data, start=2):

            name = row.get("name", "").strip()

            if not name:
                errors.append({
                    "row": row_number,
                    "message": "Role name is required."
                })
                continue

            role, created = CompanyRole.objects.update_or_create(
                company=profile.company,
                name=name,
                defaults={
                    "can_upload_receipt": to_bool(
                        row.get("can_upload_receipt", False)
                    ),
                    "can_submit_expense": to_bool(
                        row.get("can_submit_expense", False)
                    ),
                    "can_approve_expense": to_bool(
                        row.get("can_approve_expense", False)
                    ),
                    "can_mark_paid": to_bool(
                        row.get("can_mark_paid", False)
                    ),
                    "is_active": True,
                }
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        create_audit_log(
            company=profile.company,
            action="COMPANY_ROLES_IMPORT",
            action_by=profile,
            message="Company roles imported.",
            metadata={
                "created": created_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "errors": len(errors),
            }
        )

        return Response({
            "success": True,
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "errors": errors,
        })

    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def import_company_roles(request):

    profile = request.user.profile

    file = request.FILES.get("file")

    if not file:
        return Response(
            {"error": "CSV file is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        decoded_file = file.read().decode("utf-8")

        csv_data = csv.DictReader(
            io.StringIO(decoded_file)
        )

        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        def to_bool(value):
            return str(value).strip().lower() in [
                "true",
                "1",
                "yes",
                "y"
            ]

        for row_number, row in enumerate(csv_data, start=2):

            name = row.get("name", "").strip()

            if not name:
                errors.append({
                    "row": row_number,
                    "message": "Role name is required."
                })
                continue

            role, created = CompanyRole.objects.update_or_create(
                company=profile.company,
                name=name,
                defaults={
                    "can_upload_receipt": to_bool(
                        row.get("can_upload_receipt", False)
                    ),
                    "can_submit_expense": to_bool(
                        row.get("can_submit_expense", False)
                    ),
                    "can_approve_expense": to_bool(
                        row.get("can_approve_expense", False)
                    ),
                    "can_mark_paid": to_bool(
                        row.get("can_mark_paid", False)
                    ),
                    "is_active": True,
                }
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        create_audit_log(
            company=profile.company,
            action="COMPANY_ROLES_IMPORT",
            action_by=profile,
            message="Company roles imported.",
            metadata={
                "created": created_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "errors": len(errors),
            }
        )

        return Response({
            "success": True,
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "errors": errors,
        })

    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )        
    
@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def import_employees(request):

    profile = request.user.profile
    company = profile.company

    file = request.FILES.get("file")

    if not file:
        return Response(
            {"error": "CSV file is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        decoded_file = file.read().decode("utf-8")
        csv_data = csv.DictReader(io.StringIO(decoded_file))

        created_count = 0
        skipped_count = 0
        errors = []

        with transaction.atomic():

            for row_number, row in enumerate(csv_data, start=2):

                first_name = row.get("first_name", "").strip()
                last_name = row.get("last_name", "").strip()
                email = row.get("email", "").strip().lower()
                department_name = row.get("department", "").strip()
                role = row.get("role", "").strip().upper()
                company_role_name = row.get("company_role", "").strip()

                raw_password = row.get("password", "").strip()

                if not raw_password:
                    raw_password = generate_employee_password()

                if not email:
                    errors.append({
                        "row": row_number,
                        "message": "Email is required."
                    })
                    continue

                if not first_name:
                    errors.append({
                        "row": row_number,
                        "message": "First name is required."
                    })
                    continue

                if role not in [
                    "COMPANY_ADMIN",
                    "MANAGER",
                    "ACCOUNTS",
                    "EMPLOYEE"
                ]:
                    errors.append({
                        "row": row_number,
                        "message": "Invalid role."
                    })
                    continue

                if User.objects.filter(email=email).exists():
                    skipped_count += 1
                    continue

                department = None

                if department_name:
                    department = Department.objects.filter(
                        company=company,
                        name__iexact=department_name,
                        is_active=True
                    ).first()

                    if not department:
                        errors.append({
                            "row": row_number,
                            "message": f"Department '{department_name}' not found."
                        })
                        continue

                company_role = None

                if company_role_name:
                    company_role = CompanyRole.objects.filter(
                        company=company,
                        name__iexact=company_role_name,
                        is_active=True
                    ).first()

                    if not company_role:
                        errors.append({
                            "row": row_number,
                            "message": f"Company role '{company_role_name}' not found."
                        })
                        continue

                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=raw_password,
                    first_name=first_name,
                    last_name=last_name
                )

                UserProfile.objects.create(
                    user=user,
                    company=company,
                    department=department,
                    role=role,
                    company_role=company_role,
                    temporary_password=raw_password,
                    force_password_change=True,
                    invite_email_sent=False,
                    invite_email_sent_at=None,
                )

                created_count += 1

        create_audit_log(
            company=company,
            action="EMPLOYEE_IMPORT",
            action_by=profile,
            message="Employees imported. Invite emails are pending.",
            metadata={
                "created": created_count,
                "skipped": skipped_count,
                "pending_invites": created_count,
                "errors": len(errors),
            }
        )

        return Response({
            "success": True,
            "created": created_count,
            "skipped": skipped_count,
            "pending_invites": created_count,
            "errors": errors,
        })

    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def copy_role_policy(request):

    profile = request.user.profile
    company = profile.company

    from_role_id = request.data.get("from_role")
    to_role_id = request.data.get("to_role")
    overwrite_existing = request.data.get("overwrite_existing", False)

    if not from_role_id or not to_role_id:
        return Response(
            {
                "error": "from_role and to_role are required."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if str(from_role_id) == str(to_role_id):
        return Response(
            {
                "error": "Source and destination roles cannot be the same."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    policy, _ = CompanyPolicy.objects.get_or_create(
        company=company
    )

    try:
        from_role = CompanyRole.objects.get(
            id=from_role_id,
            company=company,
            is_active=True
        )

        to_role = CompanyRole.objects.get(
            id=to_role_id,
            company=company,
            is_active=True
        )

    except CompanyRole.DoesNotExist:
        return Response(
            {
                "error": "Invalid company role."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    source_rules, active_version = filter_admin_policy_rules(
        policy,
        PolicyCategoryRule.objects.filter(
            policy=policy,
            company_role=from_role,
            is_active=True,
        ),
    )

    if not source_rules.exists():
        return Response(
            {
                "error": "Source role has no policy rules."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    copied = 0
    updated = 0
    skipped = 0

    for rule in source_rules:

        existing_qs = PolicyCategoryRule.objects.filter(
            policy=policy,
            company_role=to_role,
            category_name__iexact=rule.category_name,
        )
        if active_version:
            existing_qs = existing_qs.filter(policy_version=active_version)
        else:
            existing_qs = existing_qs.filter(policy_version__isnull=True)
        existing = existing_qs.first()

        if existing:

            if overwrite_existing:

                existing.max_amount = rule.max_amount
                existing.is_unlimited = rule.is_unlimited
                existing.category_description = rule.category_description
                existing.is_active = rule.is_active
                existing.save()

                updated += 1

            else:

                skipped += 1

            continue

        PolicyCategoryRule.objects.create(
            policy=policy,
            policy_version=active_version,
            company_role=to_role,
            category_name=rule.category_name,
            max_amount=rule.max_amount,
            is_unlimited=rule.is_unlimited,
            category_description=rule.category_description,
            is_active=rule.is_active,
        )

        copied += 1

    create_audit_log(
        company=company,
        action="POLICY_ROLE_COPIED",
        action_by=profile,
        message=f"Copied policy from {from_role.name} to {to_role.name}.",
        metadata={
            "from_role": from_role.name,
            "to_role": to_role.name,
            "copied": copied,
            "updated": updated,
            "skipped": skipped,
            "overwrite_existing": overwrite_existing,
        }
    )

    return Response(
        {
            "message": "Policy copied successfully.",
            "from_role": from_role.name,
            "to_role": to_role.name,
            "copied": copied,
            "updated": updated,
            "skipped": skipped,
            "overwrite_existing": overwrite_existing,
        }
    )

@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def import_policy_rules(request):

    profile = request.user.profile
    company = profile.company

    file = request.FILES.get("file")

    if not file:
        return Response(
            {
                "error": "CSV file is required."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:

        policy, _ = CompanyPolicy.objects.get_or_create(
            company=company
        )

        decoded_file = file.read().decode("utf-8")

        csv_data = csv.DictReader(
            io.StringIO(decoded_file)
        )

        created_count = 0
        updated_count = 0
        errors = []

        for row_number, row in enumerate(csv_data, start=2):

            role_name = row.get(
                "company_role",
                ""
            ).strip()

            category_name = (
                row.get("category_name")
                or row.get("category")
                or ""
            ).strip()

            description = row.get(
                "category_description",
                ""
            ).strip()

            is_active = (
                row.get(
                    "is_active",
                    "true"
                ).strip().lower() == "true"
            )

            if not role_name:
                errors.append({
                    "row": row_number,
                    "message": "company_role is required."
                })
                continue

            if not category_name:
                errors.append({
                    "row": row_number,
                    "message": "category_name (or category) is required."
                })
                continue

            try:
                max_amount = Decimal(
                    row.get("max_amount")
                )

            except Exception:
                errors.append({
                    "row": row_number,
                    "message": "Invalid max_amount."
                })
                continue

            company_role = CompanyRole.objects.filter(
                company=company,
                name__iexact=role_name,
                is_active=True,
            ).first()

            if not company_role:
                errors.append({
                    "row": row_number,
                    "message": (
                        f"Role '{role_name}' does not exist."
                    )
                })
                continue

            version_rules, active_version = filter_admin_policy_rules(policy)
            existing = version_rules.filter(
                company_role=company_role,
                category_name__iexact=category_name,
            ).first()

            if existing:
                existing.category_name = category_name
                existing.category_description = description
                existing.max_amount = max_amount
                existing.is_unlimited = False
                existing.is_active = is_active
                existing.save()
                updated_count += 1
            else:
                PolicyCategoryRule.objects.create(
                    policy=policy,
                    policy_version=active_version,
                    company_role=company_role,
                    category_name=category_name,
                    category_description=description,
                    max_amount=max_amount,
                    is_unlimited=False,
                    is_active=is_active,
                )
                created_count += 1

        create_audit_log(
            company=company,
            action="POLICY_RULE_IMPORT",
            action_by=profile,
            message="Imported role based reimbursement policy rules.",
            metadata={
                "created": created_count,
                "updated": updated_count,
                "failed": len(errors),
            }
        )

        return Response({

            "success": True,

            "summary": {
                "created": created_count,
                "updated": updated_count,
                "failed": len(errors),
                "processed": (
                    created_count
                    + updated_count
                    + len(errors)
                ),
            },

            "errors": errors

        })

    except Exception as e:

        return Response(
            {
                "success": False,
                "error": str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )    
    
from django.http import HttpResponse

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def download_department_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="department_template.csv"'

    writer = csv.writer(response)
    writer.writerow(["name"])
    writer.writerow(["Engineering"])
    writer.writerow(["HR"])
    writer.writerow(["Finance"])

    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def download_roles_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="roles_template.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "name",
        "can_upload_receipt",
        "can_submit_expense",
        "can_approve_expense",
        "can_mark_paid"
    ])
    writer.writerow(["Employee", "true", "true", "false", "false"])
    writer.writerow(["Manager", "false", "false", "true", "false"])
    writer.writerow(["Accounts", "false", "false", "false", "true"])

    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def download_employees_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="employees_template.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "first_name",
        "last_name",
        "email",
        "department",
        "role",
        "company_role",
        "password"
    ])
    writer.writerow([
        "Rudraksh",
        "Kaushik",
        "rudraksh@company.com",
        "Engineering",
        "EMPLOYEE",
        "Employee",
        "Password@123"
    ])

    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def download_policy_rules_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="policy_rules_template.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "company_role",
        "category_name",
        "max_amount",
        "category_description",
        "is_active",
    ])
    writer.writerow(["Employee", "food", "1000", "Meals", "true"])
    writer.writerow(["Employee", "hotel", "5000", "Lodging", "true"])
    writer.writerow(["Employee", "fuel", "3000", "Fuel", "true"])

    return response

import csv

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def department_template_info(request):
    return Response({
        "success": True,
        "template_name": "department_template.csv",
        "description": "Import company departments in bulk.",
        "required_columns": ["name"],
        "sample_data": [
            {"name": "Engineering"},
            {"name": "HR"},
            {"name": "Finance"}
        ]
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def roles_template_info(request):
    return Response({
        "success": True,
        "template_name": "roles_template.csv",
        "description": "Import company roles and permissions.",
        "required_columns": [
            "name",
            "can_upload_receipt",
            "can_submit_expense",
            "can_approve_expense",
            "can_mark_paid"
        ],
        "sample_data": [
            {
                "name": "Employee",
                "can_upload_receipt": True,
                "can_submit_expense": True,
                "can_approve_expense": False,
                "can_mark_paid": False
            },
            {
                "name": "Manager",
                "can_upload_receipt": False,
                "can_submit_expense": False,
                "can_approve_expense": True,
                "can_mark_paid": False
            },
            {
                "name": "Accounts",
                "can_upload_receipt": False,
                "can_submit_expense": False,
                "can_approve_expense": False,
                "can_mark_paid": True
            }
        ]
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def employees_template_info(request):
    return Response({
        "success": True,
        "template_name": "employees_template.csv",
        "description": "Import employees in bulk.",
        "required_columns": [
            "first_name",
            "last_name",
            "email",
            "department",
            "role",
            "company_role",
            "password"
        ],
        "allowed_roles": [
            "COMPANY_ADMIN",
            "MANAGER",
            "ACCOUNTS",
            "EMPLOYEE"
        ],
        "sample_data": [
            {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@company.com",
                "department": "Engineering",
                "role": "EMPLOYEE",
                "company_role": "Employee",
                "password": "Password@123"
            }
        ]
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def policy_rules_template_info(request):
    return Response({
        "success": True,
        "template_name": "policy_rules_template.csv",
        "description": "Import reimbursement policy rules.",
        "required_columns": [
            "company_role",
            "category_name",
            "max_amount"
        ],
        "supported_categories": [
            "food",
            "hotel",
            "flight_ticket",
            "train_ticket",
            "car_rental",
            "fuel",
            "gas",
            "parking",
            "office_supplies",
            "medical",
            "courier",
            "telecom",
            "training",
            "relocation",
            "wfh",
            "miscellaneous"
        ],
        "sample_data": [
            {"company_role": "Employee", "category_name": "food", "max_amount": "1000"},
            {"company_role": "Employee", "category_name": "hotel", "max_amount": "5000"},
            {"company_role": "Employee", "category_name": "fuel", "max_amount": "3000"}
        ]
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def download_department_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="department_template.csv"'

    writer = csv.writer(response)
    writer.writerow(["name"])
    writer.writerow(["Engineering"])
    writer.writerow(["HR"])
    writer.writerow(["Finance"])
    writer.writerow(["Accounts"])

    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def download_roles_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="roles_template.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "name",
        "can_upload_receipt",
        "can_submit_expense",
        "can_approve_expense",
        "can_mark_paid"
    ])
    writer.writerow(["Employee", "true", "true", "false", "false"])
    writer.writerow(["Manager", "false", "false", "true", "false"])
    writer.writerow(["Accounts", "false", "false", "false", "true"])
    writer.writerow(["CEO", "false", "false", "true", "false"])

    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def download_employees_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="employees_template.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "first_name",
        "last_name",
        "email",
        "department",
        "role",
        "company_role",
        "password"
    ])
    writer.writerow([
        "John",
        "Doe",
        "john@company.com",
        "Engineering",
        "EMPLOYEE",
        "Employee",
        "Password@123"
    ])

    return response


import csv

from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated


@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin
])
def download_policy_rules_template(request):

    response = HttpResponse(
        content_type="text/csv"
    )

    response["Content-Disposition"] = (
        'attachment; filename="policy_rules_template.csv"'
    )

    writer = csv.writer(response)

    writer.writerow([
        "company_role",
        "category_name",
        "max_amount",
        "category_description",
        "is_active",
    ])

    writer.writerow([
        "Employee",
        "food",
        "1000",
        "Food reimbursement limit",
        "TRUE",
    ])

    writer.writerow([
        "Employee",
        "hotel",
        "5000",
        "Hotel reimbursement limit",
        "TRUE",
    ])

    writer.writerow([
        "Employee",
        "flight_ticket",
        "15000",
        "Domestic flight",
        "TRUE",
    ])

    writer.writerow([
        "Employee",
        "train_ticket",
        "8000",
        "Train reimbursement",
        "TRUE",
    ])

    writer.writerow([
        "Employee",
        "fuel",
        "3000",
        "Fuel reimbursement",
        "TRUE",
    ])

    writer.writerow([
        "Employee",
        "parking",
        "1000",
        "Parking reimbursement",
        "TRUE",
    ])

    writer.writerow([
        "Employee",
        "medical",
        "5000",
        "Medical reimbursement",
        "TRUE",
    ])

    writer.writerow([
        "Employee",
        "office_supplies",
        "2000",
        "Office supplies",
        "TRUE",
    ])

    writer.writerow([
        "Employee",
        "miscellaneous",
        "1000",
        "Miscellaneous expenses",
        "TRUE",
    ])

    writer.writerow([
        "Manager",
        "food",
        "1500",
        "Manager food limit",
        "TRUE",
    ])

    writer.writerow([
        "CEO",
        "food",
        "2500",
        "CEO food limit",
        "TRUE",
    ])

    return response

@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCompanyAdmin])
def send_employee_invites(request):

    profile = request.user.profile
    company = profile.company

    employee_ids = request.data.get("employee_ids", [])
    send_to_all = request.data.get("send_to_all", False)

    employees = UserProfile.objects.select_related(
        "user",
        "department",
        "company_role"
    ).filter(
        company=company,
        user__is_active=True,
        invite_email_sent=False
    )

    if not send_to_all:
        if not employee_ids:
            return Response(
                {"error": "employee_ids or send_to_all is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        employees = employees.filter(
            id__in=employee_ids
        )

    skipped_already_sent = 0

    if employee_ids:
        skipped_already_sent = UserProfile.objects.filter(
            company=company,
            id__in=employee_ids,
            invite_email_sent=True
        ).count()

    if not employees.exists():
        active_count = UserProfile.objects.filter(
            company=company,
            user__is_active=True,
        ).count()

        if active_count == 0:
            message = "No active employees to invite."
        else:
            message = "All active employees have already received invite emails."

        return Response(
            {
                "success": True,
                "message": message,
                "sent": 0,
                "failed": 0,
                "skipped_already_sent": skipped_already_sent or active_count,
                "errors": [],
            },
            status=status.HTTP_200_OK,
        )

    sent_count = 0
    failed_count = 0
    errors = []

    for employee in employees:

        temporary_password = employee.temporary_password

        if not temporary_password:
            temporary_password = generate_employee_password()

            employee.temporary_password = temporary_password
            employee.force_password_change = True
            employee.user.set_password(temporary_password)
            employee.user.save(update_fields=["password"])

            employee.save(update_fields=[
                "temporary_password",
                "force_password_change",
            ])

        result = send_employee_invite_email(
            company=company,
            employee=employee,
            raw_password=temporary_password,
        )

        if result.get("success"):
            employee.invite_email_sent = True
            employee.invite_email_sent_at = timezone.now()

            employee.save(update_fields=[
                "invite_email_sent",
                "invite_email_sent_at",
            ])

            sent_count += 1

        else:
            failed_count += 1
            errors.append({
                "employee": employee.user.email,
                "error": result.get("error", "Failed to send invite email."),
            })

    create_audit_log(
        company=company,
        action="EMPLOYEE_INVITES_SENT",
        action_by=profile,
        message="Employee invite emails sent.",
        metadata={
            "sent": sent_count,
            "failed": failed_count,
            "skipped_already_sent": skipped_already_sent,
        }
    )

    return Response({
        "success": True,
        "message": (
            f"Invites sent to {sent_count} employee(s)."
            if sent_count
            else "No invites were sent."
        ),
        "sent": sent_count,
        "failed": failed_count,
        "skipped_already_sent": skipped_already_sent,
        "errors": errors,
    })


from .models import Currency, CompanyFinanceSettings
from .serializers import CompanyFinanceSettingsSerializer

@api_view(["GET", "PUT"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def company_finance_settings(request):

    profile = request.user.profile
    company = profile.company

    default_currency = Currency.objects.filter(
        code="INR",
        is_active=True,
    ).first()

    finance_settings, created = CompanyFinanceSettings.objects.get_or_create(
        company=company,
        defaults={
            "base_currency": default_currency,
        },
    )

    if request.method == "GET":

        serializer = CompanyFinanceSettingsSerializer(
            finance_settings
        )

        return Response(
            {
                "success": True,
                "settings": serializer.data,
            }
        )

    serializer = CompanyFinanceSettingsSerializer(
        finance_settings,
        data=request.data,
        partial=True,
    )

    serializer.is_valid(
        raise_exception=True
    )

    # Store previous values
    previous_currency_id = finance_settings.base_currency_id
    previous_auto_conversion = finance_settings.auto_currency_conversion
    previous_exchange_rate_source = (
        finance_settings.exchange_rate_source
    )

    serializer.save()

    finance_settings.refresh_from_db()

    # Check whether receipts need to be recalculated
    currency_related_changed = (
        finance_settings.base_currency_id != previous_currency_id
        or finance_settings.auto_currency_conversion
        != previous_auto_conversion
        or finance_settings.exchange_rate_source
        != previous_exchange_rate_source
    )

    resynced_receipts = 0

    if currency_related_changed:
        from expenses.services import (
            resync_draft_receipts_to_company_currency,
        )

        resynced_receipts = (
            resync_draft_receipts_to_company_currency(
                company
            )
        )

    create_audit_log(
        company=company,
        action="POLICY_UPDATED",
        action_by=profile,
        message="Company finance settings updated.",
        metadata={
            "base_currency": serializer.data.get(
                "base_currency_code"
            ),
            "auto_currency_conversion": serializer.data.get(
                "auto_currency_conversion"
            ),
            "exchange_rate_source": serializer.data.get(
                "exchange_rate_source"
            ),
            "exchange_rate_provider": serializer.data.get(
                "exchange_rate_provider"
            ),
            "timezone": serializer.data.get(
                "timezone"
            ),
            "date_format": serializer.data.get(
                "date_format"
            ),
            "draft_receipts_resynced": resynced_receipts,
        },
    )

    message = "Company finance settings updated successfully."

    if resynced_receipts:
        message = (
            f"Company finance settings updated successfully. "
            f"Updated currency conversion on "
            f"{resynced_receipts} draft receipt(s)."
        )

    return Response(
        {
            "success": True,
            "message": message,
            "settings": serializer.data,
            "draft_receipts_resynced": resynced_receipts,
        }
    )

from .models import Currency
from .serializers import CurrencySerializer
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def currency_list(request):

    search = request.GET.get("search")
    is_active = request.GET.get("is_active", "true")
    page = request.GET.get("page", 1)
    page_size = int(request.GET.get("page_size", 20))

    currencies = Currency.objects.all()

    if is_active:
        currencies = currencies.filter(
            is_active=is_active.lower() == "true"
        )

    if search:
        currencies = currencies.filter(
            Q(code__icontains=search)
            |
            Q(name__icontains=search)
            |
            Q(country__icontains=search)
        )

    currencies = currencies.order_by("name")

    paginator = Paginator(currencies, page_size)
    page_obj = paginator.get_page(page)

    serializer = CurrencySerializer(
        page_obj,
        many=True
    )

    return Response({
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "page_size": page_size,
        "filters": {
            "search": search,
            "is_active": is_active,
        },
        "results": serializer.data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def currency_detail(request, code):

    currency = Currency.objects.filter(
        code=code.upper()
    ).first()

    if not currency:
        return Response(
            {"error": "Currency not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = CurrencySerializer(currency)

    return Response({
        "success": True,
        "currency": serializer.data,
    })

from .policy_utils import get_effective_policy_rules
@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def preview_role_policy(request):

    company = request.user.profile.company

    company_role_id = request.GET.get(
        "company_role_id"
    )

    if not company_role_id:

        return Response(
            {
                "error": "company_role_id is required."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:

        company_role = CompanyRole.objects.get(
            id=company_role_id,
            company=company,
            is_active=True,
        )

    except CompanyRole.DoesNotExist:

        return Response(
            {
                "error": "Company role not found."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    rules = get_effective_policy_rules(
        company,
        company_role,
    )

    return Response(
        {
            "company_role": {
                "id": str(company_role.id),
                "name": company_role.name,
            },
            "total_rules": len(rules),
            "rules": rules,
        }
    )

from .policy_utils import (
    get_effective_policy_rules,
    simulate_policy,
)
@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def simulate_policy_rule(request):

    company = request.user.profile.company

    company_role_id = request.data.get(
        "company_role_id"
    )

    category = request.data.get(
        "category"
    )

    amount = request.data.get(
        "amount"
    )

    if not company_role_id:
        return Response(
            {
                "error": "company_role_id is required."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not category:
        return Response(
            {
                "error": "category is required."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if amount is None:
        return Response(
            {
                "error": "amount is required."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:

        amount = Decimal(str(amount))

    except Exception:

        return Response(
            {
                "error": "Invalid amount."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:

        company_role = CompanyRole.objects.get(
            id=company_role_id,
            company=company,
            is_active=True,
        )

    except CompanyRole.DoesNotExist:

        return Response(
            {
                "error": "Company role not found."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    result = simulate_policy(
        company=company,
        company_role=company_role,
        category=category,
        amount=amount,
    )

    return Response(
        {
            "company_role": company_role.name,
            **result,
        }
    )

from .models import (
    PolicyDocumentImport,
)

from .policy_document_tasks import (
    enqueue_policy_document_processing,
)
from .policy_document_importer import (
    import_policy_document_preview,
)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_policy_document(request):

    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {
                "success": False,
                "error": "Only company admin can upload policy documents.",
                "error_code": "ACCESS_DENIED",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    uploaded_file = request.FILES.get("document")

    if not uploaded_file:
        return Response(
            {
                "success": False,
                "error": "Policy document is required.",
                "error_code": "DOCUMENT_REQUIRED",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    import_record = PolicyDocumentImport.objects.create(
        company=profile.company,
        uploaded_by=profile,
        document=uploaded_file,
        original_filename=uploaded_file.name,
        status=PolicyDocumentImport.STATUS_PROCESSING,
    )

    enqueue_policy_document_processing(str(import_record.id))

    return Response(
        {
            "success": True,
            "message": (
                "Policy document uploaded. "
                "Extraction and validation started in the background."
            ),
            "import_id": str(import_record.id),
            "status": import_record.status,
            "preview": {},
        },
        status=status.HTTP_202_ACCEPTED,
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_policy_document_import(request, import_id):

    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {
                "error": "Only company admin can import policies."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    try:

        import_record = PolicyDocumentImport.objects.get(
            id=import_id,
            company=profile.company,
        )

    except PolicyDocumentImport.DoesNotExist:

        return Response(
            {
                "error": "Import record not found."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    overwrite_existing = request.data.get(
        "overwrite_existing",
        False,
    )

    allow_review_required = request.data.get(
        "allow_review_required",
        False,
    )

    result = import_policy_document_preview(
        import_record=import_record,
        action_by=profile,
        overwrite_existing=overwrite_existing,
        allow_review_required=allow_review_required,
    )

    if not result["success"]:

        return Response(
            result,
            status=status.HTTP_400_BAD_REQUEST
        )

    return Response(result)


    from decimal import Decimal, InvalidOperation

from django.db import transaction

from tenants.models import (
    CompanyRole,
    Currency,
    PolicyDocumentImport,
)
from decimal import Decimal, InvalidOperation

from tenants.policy_document_service import (
    VALID_CATEGORIES,
    VALID_LIMIT_PERIODS,
    VALID_TRAVEL_SCOPES,
)
def _parse_boolean(value, default=False):
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "1", "yes", "y"}:
            return True

        if normalized in {"false", "0", "no", "n"}:
            return False

    return bool(value)


def _parse_policy_decimal(value):
    if value in [None, "", "null"]:
        return None

    try:
        amount = Decimal(
            str(value)
            .replace(",", "")
            .strip()
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return None

    if amount < 0:
        return None

    return amount


def _get_employee_role(company):
    return CompanyRole.objects.filter(
        company=company,
        name__iexact="Employee",
        is_active=True,
    ).first()


def _resolve_preview_role(company, rule):
    resolved_role_id = rule.get("resolved_role_id")

    if resolved_role_id:
        role = CompanyRole.objects.filter(
            id=resolved_role_id,
            company=company,
            is_active=True,
        ).first()

        if role:
            return role, None

    role_name = rule.get("role")

    if not role_name:
        employee_role = _get_employee_role(company)

        if not employee_role:
            return None, (
                "No active Employee role exists for "
                "the default policy fallback."
            )

        return employee_role, None

    role = CompanyRole.objects.filter(
        company=company,
        name__iexact=str(role_name).strip(),
        is_active=True,
    ).first()

    if role:
        return role, None

    resolved_role_name = rule.get("resolved_role_name")

    if resolved_role_name:
        role = CompanyRole.objects.filter(
            company=company,
            name__iexact=str(
                resolved_role_name
            ).strip(),
            is_active=True,
        ).first()

        if role:
            return role, None

    return None, (
        f"Role '{role_name}' does not exist as an "
        "active company role."
    )


def _resolve_preview_currency(company, preview, rule):
    currency_code = (
        rule.get("currency")
        or preview.get("policy_currency")
    )

    if currency_code:
        currency = Currency.objects.filter(
            code__iexact=str(currency_code).strip(),
            is_active=True,
        ).first()

        if currency:
            return currency, None

    finance_settings = getattr(
        company,
        "finance_settings",
        None,
    )

    if (
        finance_settings
        and finance_settings.base_currency
        and finance_settings.base_currency.is_active
    ):
        return (
            finance_settings.base_currency,
            "Company base currency was used.",
        )

    return None, "Currency could not be resolved."


def _build_preview_rule_key(rule):
    conditions = tuple(
        sorted(
            str(condition).strip().casefold()
            for condition in rule.get(
                "conditions",
                []
            )
            if condition
        )
    )

    return (
        rule.get("resolved_role_id")
        or "__DEFAULT_EMPLOYEE__",
        rule.get("category"),
        rule.get("currency"),
        rule.get("limit_period"),
        rule.get("domestic_or_international"),
        conditions,
    )
def validate_policy_document_preview(
    *,
    preview,
    company,
):
    rules = preview.get("rules", [])

    warnings = []
    errors = []
    conflicts = []

    validated_rules = []

    grouped_rules = {}

    for index, rule in enumerate(rules):
        rule = dict(rule)

        rule_index = rule.get(
            "rule_index",
            index,
        )

        review_reasons = []

        category = str(
            rule.get("category")
            or "miscellaneous"
        ).strip().lower()

        if category not in VALID_CATEGORIES:
            warnings.append({
                "code": "UNKNOWN_CATEGORY",
                "rule_index": rule_index,
                "message": (
                    f"Category '{category}' is not supported. "
                    "It was mapped to miscellaneous."
                ),
            })

            category = "miscellaneous"
            review_reasons.append(
                "Unsupported category was mapped to miscellaneous."
            )

        rule["category"] = category

        role, role_error = _resolve_preview_role(
            company,
            rule,
        )

        if role_error:
            errors.append({
                "code": "ROLE_NOT_FOUND",
                "rule_index": rule_index,
                "message": role_error,
            })

            rule["resolved_role_id"] = None
            rule["resolved_role_name"] = (
                rule.get("role")
            )
            rule["role_matched"] = False

            review_reasons.append(role_error)

        else:
            rule["resolved_role_id"] = str(role.id)
            rule["resolved_role_name"] = role.name
            rule["role_matched"] = True

        currency, currency_warning = (
            _resolve_preview_currency(
                company,
                preview,
                rule,
            )
        )

        if not currency:
            errors.append({
                "code": "CURRENCY_NOT_FOUND",
                "rule_index": rule_index,
                "message": currency_warning,
            })

            rule["currency"] = None
            review_reasons.append(
                "Currency could not be resolved."
            )

        else:
            rule["currency"] = currency.code

            if currency_warning:
                warnings.append({
                    "code": "BASE_CURRENCY_FALLBACK",
                    "rule_index": rule_index,
                    "message": currency_warning,
                })

        is_allowed = _parse_boolean(
            rule.get("is_allowed"),
            default=True,
        )

        is_unlimited = _parse_boolean(
            rule.get("is_unlimited"),
            default=False,
        )

        rule["is_allowed"] = is_allowed
        rule["is_unlimited"] = is_unlimited

        amount = _parse_policy_decimal(
            rule.get("max_amount")
        )

        if not is_allowed:
            amount = Decimal("0.00")
            is_unlimited = False

            rule["is_unlimited"] = False

        elif is_unlimited:
            amount = None

        elif amount is None:
            errors.append({
                "code": "INVALID_AMOUNT",
                "rule_index": rule_index,
                "message": (
                    "max_amount is required when the rule "
                    "is allowed and is not unlimited."
                ),
            })

            review_reasons.append(
                "Maximum amount is missing or invalid."
            )

        rule["max_amount"] = (
            format(amount, "f")
            if amount is not None
            else None
        )

        limit_period = str(
            rule.get("limit_period")
            or "NOT_SPECIFIED"
        ).strip().upper()

        if limit_period not in VALID_LIMIT_PERIODS:
            warnings.append({
                "code": "INVALID_LIMIT_PERIOD",
                "rule_index": rule_index,
                "message": (
                    f"Unsupported limit period "
                    f"'{limit_period}' was changed "
                    "to NOT_SPECIFIED."
                ),
            })

            limit_period = "NOT_SPECIFIED"

        rule["limit_period"] = limit_period

        travel_scope = str(
            rule.get("domestic_or_international")
            or "NOT_SPECIFIED"
        ).strip().upper()

        if travel_scope not in VALID_TRAVEL_SCOPES:
            warnings.append({
                "code": "INVALID_TRAVEL_SCOPE",
                "rule_index": rule_index,
                "message": (
                    f"Unsupported travel scope "
                    f"'{travel_scope}' was changed "
                    "to NOT_SPECIFIED."
                ),
            })

            travel_scope = "NOT_SPECIFIED"

        rule[
            "domestic_or_international"
        ] = travel_scope

        description = str(
            rule.get("description")
            or ""
        ).strip()

        if not description:
            errors.append({
                "code": "DESCRIPTION_REQUIRED",
                "rule_index": rule_index,
                "message": "Description is required.",
            })

            review_reasons.append(
                "Description is missing."
            )

        rule["description"] = description

        reason = str(
            rule.get("reason")
            or (
                "The document defines this as the "
                "applicable reimbursement policy."
            )
        ).strip()

        rule["reason"] = reason

        confidence = rule.get("confidence", 0)

        try:
            confidence = float(confidence)
        except (
            TypeError,
            ValueError,
        ):
            confidence = 0.0

        confidence = min(
            max(confidence, 0.0),
            1.0,
        )

        rule["confidence"] = confidence

        translation_confidence = rule.get(
            "translation_confidence",
            0,
        )

        try:
            translation_confidence = float(
                translation_confidence
            )
        except (
            TypeError,
            ValueError,
        ):
            translation_confidence = 0.0

        translation_confidence = min(
            max(translation_confidence, 0.0),
            1.0,
        )

        rule[
            "translation_confidence"
        ] = translation_confidence

        if confidence < 0.75:
            review_reasons.append(
                "Extraction confidence is below 0.75."
            )

        if translation_confidence < 0.75:
            review_reasons.append(
                "Translation confidence is below 0.75."
            )

        rule["rule_index"] = rule_index
        rule["duplicate_rule"] = False
        rule["review_required"] = bool(
            review_reasons
        )
        rule["review_reason"] = (
            " | ".join(
                dict.fromkeys(review_reasons)
            )
            if review_reasons
            else None
        )

        validated_rules.append(rule)

        grouped_rules.setdefault(
            _build_preview_rule_key(rule),
            [],
        ).append(rule)

    for _, grouped in grouped_rules.items():
        if len(grouped) < 2:
            continue

        values = {
            (
                rule.get("max_amount"),
                rule.get("is_unlimited"),
                rule.get("is_allowed"),
            )
            for rule in grouped
        }

        if len(values) == 1:
            for duplicate in grouped[1:]:
                duplicate["duplicate_rule"] = True
                duplicate["review_required"] = True

                duplicate["review_reason"] = (
                    (
                        f"{duplicate.get('review_reason')} | "
                        "Probable duplicate rule."
                    )
                    if duplicate.get("review_reason")
                    else "Probable duplicate rule."
                )

                warnings.append({
                    "code": "DUPLICATE_RULE",
                    "rule_index": duplicate[
                        "rule_index"
                    ],
                    "message": (
                        "A probable duplicate policy "
                        "rule was found."
                    ),
                })

        else:
            conflict = {
                "role": (
                    grouped[0].get(
                        "resolved_role_name"
                    )
                    or grouped[0].get("role")
                ),
                "category": grouped[0].get(
                    "category"
                ),
                "values": [
                    (
                        "Unlimited"
                        if rule.get(
                            "is_unlimited"
                        )
                        else (
                            "Prohibited"
                            if not rule.get(
                                "is_allowed"
                            )
                            else (
                                f"{rule.get('max_amount')} "
                                f"{rule.get('currency') or ''}"
                            ).strip()
                        )
                    )
                    for rule in grouped
                ],
                "rule_indexes": [
                    rule["rule_index"]
                    for rule in grouped
                ],
                "message": (
                    "Conflicting values were found "
                    "for the same policy rule."
                ),
                "source_texts": [
                    rule.get("source_text")
                    for rule in grouped
                    if rule.get("source_text")
                ],
            }

            conflicts.append(conflict)

            for rule in grouped:
                rule["review_required"] = True
                rule["review_reason"] = (
                    (
                        f"{rule.get('review_reason')} | "
                        "Conflicting values require review."
                    )
                    if rule.get("review_reason")
                    else (
                        "Conflicting values require review."
                    )
                )

    validated_preview = dict(preview)

    validated_preview["rules"] = validated_rules
    validated_preview["rules_found"] = len(
        validated_rules
    )
    validated_preview[
        "rules_requiring_review"
    ] = sum(
        1
        for rule in validated_rules
        if rule.get("review_required")
    )

    validated_preview["warnings"] = warnings
    validated_preview["warning_count"] = len(
        warnings
    )

    validated_preview["conflicts"] = conflicts
    validated_preview["conflict_count"] = len(
        conflicts
    )

    validated_preview["validation_errors"] = errors
    validated_preview[
        "validation_error_count"
    ] = len(errors)

    validated_preview["is_valid_for_import"] = (
        len(errors) == 0
        and len(conflicts) == 0
    )

    return validated_preview

@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def get_policy_document_preview(
    request,
    import_id,
):
    company = request.user.profile.company

    try:
        import_record = (
            PolicyDocumentImport.objects
            .select_related(
                "company",
                "uploaded_by",
                "uploaded_by__user",
            )
            .get(
                id=import_id,
                company=company,
            )
        )

    except PolicyDocumentImport.DoesNotExist:
        return Response(
            {
                "error": (
                    "Policy document import "
                    "record not found."
                )
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "import": {
                "id": str(import_record.id),
                "filename": (
                    import_record.original_filename
                ),
                "status": import_record.status,
                "uploaded_by": (
                    import_record.uploaded_by.user.email
                    if import_record.uploaded_by
                    else None
                ),
                "error_message": (
                    import_record.error_message
                ),
                "created_at": (
                    import_record.created_at
                ),
                "updated_at": (
                    import_record.updated_at
                ),
            },
            "preview": (
                import_record.extracted_json
                or {}
            ),
            "warnings": (
                import_record.warnings
                or []
            ),
            "conflicts": (
                import_record.conflicts
                or []
            ),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["PATCH"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
@transaction.atomic
def update_policy_document_preview(
    request,
    import_id,
):
    profile = request.user.profile
    company = profile.company

    try:
        import_record = (
            PolicyDocumentImport.objects
            .select_for_update()
            .get(
                id=import_id,
                company=company,
            )
        )

    except PolicyDocumentImport.DoesNotExist:
        return Response(
            {
                "error": (
                    "Policy document import "
                    "record not found."
                )
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if (
        import_record.status
        == PolicyDocumentImport.STATUS_IMPORTED
    ):
        return Response(
            {
                "error": (
                    "An imported policy preview "
                    "cannot be edited."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    preview = dict(
        import_record.extracted_json or {}
    )

    allowed_top_level_fields = {
        "policy_name",
        "policy_version",
        "effective_date",
        "expiry_date",
        "policy_currency",
        "document_summary",
        "document_summary_original_language",
        "document_level_conditions",
        "document_level_conditions_original_language",
    }

    for field_name in allowed_top_level_fields:
        if field_name in request.data:
            preview[field_name] = (
                request.data.get(field_name)
            )

    if "rules" in request.data:
        rules = request.data.get("rules")

        if not isinstance(rules, list):
            return Response(
                {
                    "error": (
                        "rules must be an array."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        preview["rules"] = rules

    validated_preview = (
        validate_policy_document_preview(
            preview=preview,
            company=company,
        )
    )

    import_record.extracted_json = (
        validated_preview
    )
    import_record.warnings = (
        validated_preview.get(
            "warnings",
            [],
        )
    )
    import_record.conflicts = (
        validated_preview.get(
            "conflicts",
            [],
        )
    )
    import_record.status = (
        PolicyDocumentImport
        .STATUS_REVIEW_REQUIRED
    )
    import_record.error_message = None

    import_record.save(update_fields=[
        "extracted_json",
        "warnings",
        "conflicts",
        "status",
        "error_message",
        "updated_at",
    ])

    create_audit_log(
        company=company,
        action="AI_POLICY_PREVIEW_UPDATED",
        action_by=profile,
        message=(
            "AI policy document preview updated."
        ),
        metadata={
            "import_id": str(import_record.id),
            "filename": (
                import_record.original_filename
            ),
            "rules_found": (
                validated_preview.get(
                    "rules_found",
                    0,
                )
            ),
            "review_required": (
                validated_preview.get(
                    "rules_requiring_review",
                    0,
                )
            ),
            "validation_errors": (
                validated_preview.get(
                    "validation_error_count",
                    0,
                )
            ),
            "conflicts": (
                validated_preview.get(
                    "conflict_count",
                    0,
                )
            ),
        },
    )

    return Response(
        {
            "message": (
                "Policy preview updated "
                "and revalidated successfully."
            ),
            "import_id": str(import_record.id),
            "status": import_record.status,
            "preview": validated_preview,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def revalidate_policy_document_preview(
    request,
    import_id,
):
    profile = request.user.profile
    company = profile.company

    try:
        import_record = (
            PolicyDocumentImport.objects
            .get(
                id=import_id,
                company=company,
            )
        )

    except PolicyDocumentImport.DoesNotExist:
        return Response(
            {
                "error": (
                    "Policy document import "
                    "record not found."
                )
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if (
        import_record.status
        == PolicyDocumentImport.STATUS_IMPORTED
    ):
        return Response(
            {
                "error": (
                    "An imported policy document "
                    "cannot be revalidated."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    preview = (
        import_record.extracted_json
        or {}
    )

    validated_preview = (
        validate_policy_document_preview(
            preview=preview,
            company=company,
        )
    )

    import_record.extracted_json = (
        validated_preview
    )
    import_record.warnings = (
        validated_preview.get(
            "warnings",
            [],
        )
    )
    import_record.conflicts = (
        validated_preview.get(
            "conflicts",
            [],
        )
    )
    import_record.status = (
        PolicyDocumentImport
        .STATUS_REVIEW_REQUIRED
    )
    import_record.error_message = None

    import_record.save(update_fields=[
        "extracted_json",
        "warnings",
        "conflicts",
        "status",
        "error_message",
        "updated_at",
    ])

    return Response(
        {
            "message": (
                "Policy preview revalidated."
            ),
            "import_id": str(import_record.id),
            "status": import_record.status,
            "is_valid_for_import": (
                validated_preview.get(
                    "is_valid_for_import",
                    False,
                )
            ),
            "validation_error_count": (
                validated_preview.get(
                    "validation_error_count",
                    0,
                )
            ),
            "warning_count": (
                validated_preview.get(
                    "warning_count",
                    0,
                )
            ),
            "conflict_count": (
                validated_preview.get(
                    "conflict_count",
                    0,
                )
            ),
            "preview": validated_preview,
        },
        status=status.HTTP_200_OK,
    )

from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import (
    CompanyPolicy,
    PolicyVersion,
)

from .serializers import (
    PolicyVersionSerializer,
)

from .policy_version_service import (
    create_policy_version,
    activate_policy_version,
    archive_policy_version,
    duplicate_policy_version,
    rollback_policy_version,
    delete_draft_policy_version,
)

@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def create_policy_version_api(request):

    profile = request.user.profile
    company = profile.company

    policy, _ = CompanyPolicy.objects.get_or_create(
        company=company
    )

    title = request.data.get("title")
    description = request.data.get("description")

    copy_active_rules = request.data.get(
        "copy_active_rules",
        True,
    )

    if isinstance(copy_active_rules, str):
        copy_active_rules = (
            copy_active_rules.strip().lower()
            in ["true", "1", "yes"]
        )

    result = create_policy_version(
        policy=policy,
        action_by=profile,
        title=title,
        description=description,
        imported_from_document=None,
        copy_active_rules=copy_active_rules,
    )

    if not result.get("success"):
        return Response(
            result,
            status=status.HTTP_400_BAD_REQUEST,
        )

    version = PolicyVersion.objects.get(
        id=result["version"]["id"]
    )

    return Response(
        {
            "message": (
                "Policy version created successfully."
            ),
            "copied_rules": result.get(
                "copied_rules",
                0,
            ),
            "copied_from": result.get(
                "copied_from"
            ),
            "version": PolicyVersionSerializer(
                version
            ).data,
        },
        status=status.HTTP_201_CREATED,
    )

@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def list_policy_versions(request):

    profile = request.user.profile
    company = profile.company

    policy, _ = CompanyPolicy.objects.get_or_create(
        company=company
    )

    status_filter = request.GET.get("status")
    is_active_filter = request.GET.get("is_active")

    versions = (
        PolicyVersion.objects
        .filter(
            policy=policy
        )
        .select_related(
            "created_by",
            "created_by__user",
            "activated_by",
            "activated_by__user",
            "imported_from_document",
        )
        .prefetch_related(
            "rules"
        )
        .order_by(
            "-version_number"
        )
    )

    if status_filter:
        status_filter = status_filter.strip().upper()

        valid_statuses = {
            PolicyVersion.STATUS_DRAFT,
            PolicyVersion.STATUS_ACTIVE,
            PolicyVersion.STATUS_ARCHIVED,
        }

        if status_filter not in valid_statuses:
            return Response(
                {
                    "error": (
                        "Invalid status filter. "
                        "Use DRAFT, ACTIVE, or ARCHIVED."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        versions = versions.filter(
            status=status_filter
        )

    if is_active_filter is not None:
        active_value = (
            str(is_active_filter)
            .strip()
            .lower()
        )

        if active_value in ["true", "1", "yes"]:
            versions = versions.filter(
                is_active=True
            )

        elif active_value in [
            "false",
            "0",
            "no",
        ]:
            versions = versions.filter(
                is_active=False
            )

        else:
            return Response(
                {
                    "error": (
                        "is_active must be true or false."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    serializer = PolicyVersionSerializer(
        versions,
        many=True,
    )

    active_version = versions.filter(
        is_active=True
    ).first()

    return Response(
        {
            "count": versions.count(),
            "active_version": (
                PolicyVersionSerializer(
                    active_version
                ).data
                if active_version
                else None
            ),
            "results": serializer.data,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def get_policy_version(
    request,
    version_id,
):

    profile = request.user.profile

    try:
        version = (
            PolicyVersion.objects
            .select_related(
                "policy",
                "policy__company",
                "created_by",
                "created_by__user",
                "activated_by",
                "activated_by__user",
                "imported_from_document",
            )
            .prefetch_related(
                "rules",
                "rules__company_role",
            )
            .get(
                id=version_id,
                policy__company=profile.company,
            )
        )

    except PolicyVersion.DoesNotExist:
        return Response(
            {
                "error": "Policy version not found."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    rules = version.rules.select_related(
        "company_role"
    ).order_by(
        "company_role__name",
        "category_name",
    )

    rules_data = []

    for rule in rules:
        rules_data.append({
            "id": str(rule.id),
            "company_role": {
                "id": str(
                    rule.company_role.id
                ),
                "name": (
                    rule.company_role.name
                ),
            },
            "category_name": (
                rule.category_name
            ),
            "max_amount": (
                str(rule.max_amount)
                if rule.max_amount is not None
                else None
            ),
            "currency": rule.currency,
            "is_unlimited": (
                rule.is_unlimited
            ),
            "category_description": (
                rule.category_description
            ),
            "policy_reason": (
                rule.policy_reason
            ),
            "source_text": rule.source_text,
            "ai_confidence": (
                str(rule.ai_confidence)
                if rule.ai_confidence is not None
                else None
            ),
            "is_ai_generated": (
                rule.is_ai_generated
            ),
            "is_active": rule.is_active,
        })

    return Response(
        {
            "version": (
                PolicyVersionSerializer(
                    version
                ).data
            ),
            "rules": rules_data,
            "total_rules": len(
                rules_data
            ),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["PATCH"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def activate_policy_version_api(
    request,
    version_id,
):

    profile = request.user.profile

    try:
        version = PolicyVersion.objects.select_related(
            "policy",
            "policy__company",
        ).get(
            id=version_id,
            policy__company=profile.company,
        )

    except PolicyVersion.DoesNotExist:
        return Response(
            {
                "error": "Policy version not found."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    result = activate_policy_version(
        version=version,
        action_by=profile,
    )

    if not result.get("success"):
        return Response(
            result,
            status=status.HTTP_400_BAD_REQUEST,
        )

    version.refresh_from_db()

    return Response(
        {
            "message": result["message"],
            "previous_active_version": result.get(
                "previous_active_version"
            ),
            "version": PolicyVersionSerializer(
                version
            ).data,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["PATCH"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def archive_policy_version_api(
    request,
    version_id,
):

    profile = request.user.profile

    try:
        version = PolicyVersion.objects.select_related(
            "policy",
            "policy__company",
        ).get(
            id=version_id,
            policy__company=profile.company,
        )

    except PolicyVersion.DoesNotExist:
        return Response(
            {
                "error": "Policy version not found."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    result = archive_policy_version(
        version=version,
        action_by=profile,
    )

    if not result.get("success"):
        return Response(
            result,
            status=status.HTTP_400_BAD_REQUEST,
        )

    version.refresh_from_db()

    return Response(
        {
            "message": result["message"],
            "version": PolicyVersionSerializer(
                version
            ).data,
        },
        status=status.HTTP_200_OK,
    )

        

@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def duplicate_policy_version_api(
    request,
    version_id,
):

    profile = request.user.profile

    try:
        source_version = (
            PolicyVersion.objects
            .select_related(
                "policy",
                "policy__company",
            )
            .get(
                id=version_id,
                policy__company=profile.company,
            )
        )

    except PolicyVersion.DoesNotExist:
        return Response(
            {
                "error": "Policy version not found."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    result = duplicate_policy_version(
        source_version=source_version,
        action_by=profile,
        title=request.data.get("title"),
        description=request.data.get(
            "description"
        ),
    )

    if not result.get("success"):
        return Response(
            result,
            status=status.HTTP_400_BAD_REQUEST,
        )

    new_version = PolicyVersion.objects.get(
        id=result["version"]["id"]
    )

    return Response(
        {
            "message": result["message"],
            "copied_rules": result.get(
                "copied_rules",
                0,
            ),
            "source_version": result.get(
                "source_version"
            ),
            "version": PolicyVersionSerializer(
                new_version
            ).data,
        },
        status=status.HTTP_201_CREATED,
    )

@api_view(["POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def rollback_policy_version_api(
    request,
    version_id,
):

    profile = request.user.profile

    try:
        source_version = (
            PolicyVersion.objects
            .select_related(
                "policy",
                "policy__company",
            )
            .get(
                id=version_id,
                policy__company=profile.company,
            )
        )

    except PolicyVersion.DoesNotExist:
        return Response(
            {
                "error": "Policy version not found."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    result = rollback_policy_version(
        source_version=source_version,
        action_by=profile,
        title=request.data.get("title"),
        description=request.data.get(
            "description"
        ),
    )

    if not result.get("success"):
        return Response(
            result,
            status=status.HTTP_400_BAD_REQUEST,
        )

    new_version = PolicyVersion.objects.get(
        id=result["version"]["id"]
    )

    return Response(
        {
            "message": result["message"],
            "copied_rules": result.get(
                "copied_rules",
                0,
            ),
            "source_version": result.get(
                "source_version"
            ),
            "previous_active_version": (
                result.get(
                    "previous_active_version"
                )
            ),
            "version": PolicyVersionSerializer(
                new_version
            ).data,
        },
        status=status.HTTP_201_CREATED,
    )

@api_view(["DELETE"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def delete_draft_policy_version_api(
    request,
    version_id,
):

    profile = request.user.profile

    try:
        version = PolicyVersion.objects.select_related(
            "policy",
            "policy__company",
        ).get(
            id=version_id,
            policy__company=profile.company,
        )

    except PolicyVersion.DoesNotExist:
        return Response(
            {
                "error": "Policy version not found."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    result = delete_draft_policy_version(
        version=version,
        action_by=profile,
    )

    if not result.get("success"):
        return Response(
            result,
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        result,
        status=status.HTTP_200_OK,
    )
from .policy_difference import (
    compare_policy_versions,
)

@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def compare_policy_versions_api(request):

    profile = request.user.profile
    company = profile.company

    old_version_id = request.GET.get(
        "old_version_id"
    )

    new_version_id = request.GET.get(
        "new_version_id"
    )

    include_unchanged_raw = request.GET.get(
        "include_unchanged",
        "false",
    )

    include_ai_summary_raw = request.GET.get(
        "include_ai_summary",
        "true",
    )

    refresh_raw = request.GET.get(
        "refresh",
        "false",
    )

    include_unchanged = (
        str(include_unchanged_raw)
        .strip()
        .lower()
        in {"true", "1", "yes"}
    )

    include_ai_summary = (
        str(include_ai_summary_raw)
        .strip()
        .lower()
        in {"true", "1", "yes"}
    )

    refresh = (
        str(refresh_raw)
        .strip()
        .lower()
        in {"true", "1", "yes"}
    )

    if not old_version_id:
        return Response(
            {
                "error": (
                    "old_version_id is required."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not new_version_id:
        return Response(
            {
                "error": (
                    "new_version_id is required."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        old_version = (
            PolicyVersion.objects
            .select_related(
                "policy",
                "policy__company",
            )
            .prefetch_related(
                "rules",
                "rules__company_role",
            )
            .get(
                id=old_version_id,
                policy__company=company,
            )
        )

    except (
        PolicyVersion.DoesNotExist,
        ValueError,
    ):
        return Response(
            {
                "error": (
                    "Old policy version not found."
                )
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        new_version = (
            PolicyVersion.objects
            .select_related(
                "policy",
                "policy__company",
            )
            .prefetch_related(
                "rules",
                "rules__company_role",
            )
            .get(
                id=new_version_id,
                policy__company=company,
            )
        )

    except (
        PolicyVersion.DoesNotExist,
        ValueError,
    ):
        return Response(
            {
                "error": (
                    "New policy version not found."
                )
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if (
        old_version.policy_id
        != new_version.policy_id
    ):
        return Response(
            {
                "error": (
                    "Selected versions belong to "
                    "different policies."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if old_version.id == new_version.id:
        return Response(
            {
                "error": (
                    "Select two different policy versions."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    language_settings = (
        get_company_output_language(
            company
        )
    )

    output_language_name = (
        language_settings.get("name")
        or "English"
    )

    output_language_code = (
        language_settings.get("code")
        or "en"
    )

    # --------------------------------------------------
    # Return cached comparison unless refresh is requested
    # --------------------------------------------------

    cached_comparison = (
        PolicyVersionComparison.objects
        .filter(
            policy=old_version.policy,
            old_version=old_version,
            new_version=new_version,
            include_unchanged=include_unchanged,
            output_language_code=(
                output_language_code
            ),
        )
        .first()
    )

    cached_has_required_ai_summary = (
        cached_comparison
        and (
            not include_ai_summary
            or cached_comparison.ai_summary_generated
        )
    )

    if (
        cached_comparison
        and cached_has_required_ai_summary
        and not refresh
    ):
        return Response(
            {
                "success": True,
                "cached": True,
                "comparison_id": str(
                    cached_comparison.id
                ),
                "comparison": (
                    cached_comparison.comparison_data
                ),
                "ai_summary_enabled": (
                    include_ai_summary
                ),
                "ai_summary": (
                    cached_comparison.ai_summary
                    if include_ai_summary
                    else None
                ),
                "generated_by": (
                    cached_comparison.generated_by
                    if include_ai_summary
                    else None
                ),
                "output_language": {
                    "name": (
                        cached_comparison.output_language
                    ),
                    "code": (
                        cached_comparison
                        .output_language_code
                    ),
                },
                "last_generated_at": (
                    cached_comparison
                    .updated_at
                    .isoformat()
                ),
            },
            status=status.HTTP_200_OK,
        )

    # --------------------------------------------------
    # Deterministic comparison
    # --------------------------------------------------

    comparison_result = compare_policy_versions(
        old_version=old_version,
        new_version=new_version,
        include_unchanged=include_unchanged,
    )

    if not comparison_result.get("success"):
        return Response(
            comparison_result,
            status=status.HTTP_400_BAD_REQUEST,
        )

    ai_summary = {}
    ai_summary_generated = False
    generated_by = None
    ai_model = None
    ai_message = None

    # --------------------------------------------------
    # Optional Gemini explanation
    # --------------------------------------------------

    if include_ai_summary:

        ai_result = (
            generate_ai_difference_summary(
                comparison_result=(
                    comparison_result
                ),
                company=company,
            )
        )

        ai_summary = (
            ai_result.get("ai_summary")
            or {}
        )

        ai_message = ai_result.get(
            "message"
        )

        ai_summary_generated = bool(
            ai_summary
        )

        generated_by = ai_summary.get(
            "generated_by"
        )

        ai_model = ai_summary.get(
            "ai_model"
        )

    # --------------------------------------------------
    # Create or update cached comparison
    # --------------------------------------------------

    comparison_record, created = (
        PolicyVersionComparison.objects
        .update_or_create(
            policy=old_version.policy,
            old_version=old_version,
            new_version=new_version,
            include_unchanged=include_unchanged,
            output_language_code=(
                output_language_code
            ),
            defaults={
                "comparison_data": (
                    comparison_result
                ),
                "ai_summary": ai_summary,
                "ai_summary_generated": (
                    ai_summary_generated
                ),
                "generated_by": generated_by,
                "ai_model": ai_model,
                "output_language": (
                    output_language_name
                ),
                "created_by": profile,
            },
        )
    )

    # --------------------------------------------------
    # Audit log
    # --------------------------------------------------

    comparison_summary = (
        comparison_result.get(
            "summary",
            {},
        )
    )

    create_audit_log(
        company=company,
        action="POLICY_VERSIONS_COMPARED",
        action_by=profile,
        message=(
            f"Policy version "
            f"{old_version.version_number} was compared "
            f"with version "
            f"{new_version.version_number}."
        ),
        metadata={
            "comparison_id": str(
                comparison_record.id
            ),
            "comparison_record_created": (
                created
            ),
            "policy_id": str(
                old_version.policy_id
            ),
            "old_version_id": str(
                old_version.id
            ),
            "old_version_number": (
                old_version.version_number
            ),
            "new_version_id": str(
                new_version.id
            ),
            "new_version_number": (
                new_version.version_number
            ),
            "include_unchanged": (
                include_unchanged
            ),
            "include_ai_summary": (
                include_ai_summary
            ),
            "refresh_requested": refresh,
            "total_changes": (
                comparison_summary.get(
                    "total_changes",
                    0,
                )
            ),
            "added_rules": (
                comparison_summary.get(
                    "added_rules",
                    0,
                )
            ),
            "removed_rules": (
                comparison_summary.get(
                    "removed_rules",
                    0,
                )
            ),
            "modified_rules": (
                comparison_summary.get(
                    "modified_rules",
                    0,
                )
            ),
            "changed_roles": (
                comparison_summary.get(
                    "changed_roles",
                    [],
                )
            ),
            "changed_categories": (
                comparison_summary.get(
                    "changed_categories",
                    [],
                )
            ),
            "ai_summary_generated": (
                ai_summary_generated
            ),
            "generated_by": generated_by,
            "ai_model": ai_model,
            "output_language": (
                output_language_name
            ),
            "output_language_code": (
                output_language_code
            ),
        },
    )

    return Response(
        {
            "success": True,
            "cached": False,
            "comparison_id": str(
                comparison_record.id
            ),
            "comparison": comparison_result,
            "ai_summary_enabled": (
                include_ai_summary
            ),
            "ai_summary_message": (
                ai_message
            ),
            "ai_summary": (
                ai_summary
                if include_ai_summary
                else None
            ),
            "generated_by": (
                generated_by
                if include_ai_summary
                else None
            ),
            "output_language": {
                "name": output_language_name,
                "code": output_language_code,
            },
        },
        status=status.HTTP_200_OK,
    )

from .models import CompanyPreferences
from .serializers import CompanyPreferencesSerializer

@api_view(["GET", "PATCH"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def company_language_preferences(request):
    profile = request.user.profile
    company = profile.company

    preferences, _ = CompanyPreferences.objects.get_or_create(
        company=company,
        defaults={
            "output_language_code": "en",
            "output_language_name": "English",
            "preserve_original_text": True,
        }
    )

    if request.method == "GET":
        return Response(
            CompanyPreferencesSerializer(
                preferences
            ).data,
            status=status.HTTP_200_OK,
        )

    serializer = CompanyPreferencesSerializer(
        preferences,
        data=request.data,
        partial=True,
    )

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    preferences = serializer.save()

    create_audit_log(
        company=company,
        action="COMPANY_LANGUAGE_UPDATED",
        action_by=profile,
        message=(
            "Company AI output language preferences updated."
        ),
        metadata={
            "language_code": (
                preferences.output_language_code
            ),
            "language_name": (
                preferences.output_language_name
            ),
            "preserve_original_text": (
                preferences.preserve_original_text
            ),
        },
    )

    return Response(
        {
            "message": (
                "Company language preferences updated successfully."
            ),
            "preferences": CompanyPreferencesSerializer(
                preferences
            ).data,
        },
        status=status.HTTP_200_OK,
    )

from django.shortcuts import get_object_or_404

from .models import CompanyExchangeRate
from .serializers import CompanyExchangeRateSerializer


def _resync_drafts_if_custom_rates(company):
    finance_settings = getattr(company, "finance_settings", None)
    if not finance_settings or finance_settings.exchange_rate_source != "CUSTOM":
        return 0

    from expenses.services import resync_draft_receipts_to_company_currency

    return resync_draft_receipts_to_company_currency(company)


@api_view(["GET", "POST"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def company_exchange_rates(request):

    company = request.user.profile.company

    if request.method == "GET":

        rates = (
            CompanyExchangeRate.objects.filter(
                company=company,
            )
            .select_related(
                "from_currency",
                "to_currency",
            )
            .order_by(
                "from_currency__code",
                "to_currency__code",
            )
        )

        serializer = CompanyExchangeRateSerializer(
            rates,
            many=True,
        )

        return Response(
            {
                "success": True,
                "exchange_rates": serializer.data,
            }
        )

    serializer = CompanyExchangeRateSerializer(
        data=request.data,
        context={"request": request},
    )

    serializer.is_valid(raise_exception=True)
    serializer.save(company=company)

    resynced_receipts = _resync_drafts_if_custom_rates(company)

    return Response(
        {
            "success": True,
            "message": "Exchange rate created successfully.",
            "exchange_rate": serializer.data,
            "draft_receipts_resynced": resynced_receipts,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["PUT"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def update_company_exchange_rate(request, rate_id):

    company = request.user.profile.company

    rate = get_object_or_404(
        CompanyExchangeRate,
        id=rate_id,
        company=company,
    )

    serializer = CompanyExchangeRateSerializer(
        rate,
        data=request.data,
        partial=True,
        context={"request": request},
    )

    serializer.is_valid(raise_exception=True)
    serializer.save()

    resynced_receipts = _resync_drafts_if_custom_rates(company)

    return Response(
        {
            "success": True,
            "message": "Exchange rate updated successfully.",
            "exchange_rate": serializer.data,
            "draft_receipts_resynced": resynced_receipts,
        }
    )


@api_view(["DELETE"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def delete_company_exchange_rate(request, rate_id):

    company = request.user.profile.company

    rate = get_object_or_404(
        CompanyExchangeRate,
        id=rate_id,
        company=company,
    )

    rate.delete()

    resynced_receipts = _resync_drafts_if_custom_rates(company)

    return Response(
        {
            "success": True,
            "message": "Exchange rate deleted successfully.",
            "draft_receipts_resynced": resynced_receipts,
        },
        status=status.HTTP_200_OK,
    )