from .models import CompanyRole
from .role_schema import company_role_flag

DEFAULT_COMPANY_ROLE_TEMPLATES = [
    {
        "name": "Employee",
        "can_upload_receipt": True,
        "can_submit_expense": True,
        "can_approve_expense": False,
        "can_mark_paid": False,
    },
    {
        "name": "Manager",
        "can_upload_receipt": False,
        "can_submit_expense": False,
        "can_approve_expense": True,
        "can_mark_paid": False,
    },
    {
        "name": "Accounts",
        "can_upload_receipt": False,
        "can_submit_expense": False,
        "can_approve_expense": False,
        "can_mark_paid": True,
    },
]

SYSTEM_ROLE_TO_DEFAULT_ROLE_NAME = {
    "EMPLOYEE": "Employee",
    "MANAGER": "Manager",
    "ACCOUNTS": "Accounts",
}


def permissions_for_profile(profile):
    empty = {
        "can_upload_receipt": False,
        "can_submit_expense": False,
        "can_approve_expense": False,
        "can_mark_paid": False,
        "can_manage_company": False,
        "can_manage_roles": False,
        "can_manage_employees": False,
        "can_manage_departments": False,
        "can_manage_users": False,
        "can_manage_policy": False,
        "can_manage_workflow": False,
        "can_view_company_reports": False,
        "can_view_all_reports": False,
        "can_view_audit_logs": False,
        "can_manage_integrations": False,
        "can_view_integrations": False,
    }

    if not profile:
        return empty

    if profile.role == "COMPANY_ADMIN":
        return {key: True for key in empty}

    role = profile.company_role
    if not role:
        return empty

    return {
        "can_upload_receipt": role.can_upload_receipt,
        "can_submit_expense": role.can_submit_expense,
        "can_approve_expense": role.can_approve_expense,
        "can_mark_paid": role.can_mark_paid,
        "can_manage_company": company_role_flag(role, "can_manage_company"),
        "can_manage_roles": company_role_flag(role, "can_manage_roles"),
        "can_manage_employees": company_role_flag(role, "can_manage_employees"),
        "can_manage_departments": company_role_flag(role, "can_manage_departments"),
        "can_manage_users": company_role_flag(role, "can_manage_employees"),
        "can_manage_policy": company_role_flag(role, "can_manage_policy"),
        "can_manage_workflow": company_role_flag(role, "can_manage_workflow"),
        "can_view_company_reports": company_role_flag(role, "can_view_company_reports"),
        "can_view_all_reports": company_role_flag(role, "can_view_company_reports"),
        "can_view_audit_logs": False,
        "can_manage_integrations": company_role_flag(role, "can_manage_integrations"),
        "can_view_integrations": company_role_flag(role, "can_view_integrations"),
    }


def ensure_default_company_roles(company):
    for template in DEFAULT_COMPANY_ROLE_TEMPLATES:
        CompanyRole.objects.get_or_create(
            company=company,
            name=template["name"],
            defaults={
                "can_upload_receipt": template["can_upload_receipt"],
                "can_submit_expense": template["can_submit_expense"],
                "can_approve_expense": template["can_approve_expense"],
                "can_mark_paid": template["can_mark_paid"],
                "is_active": True,
            },
        )


def resolve_company_role(company, system_role, company_role_id=None):
    if company_role_id:
        return CompanyRole.objects.filter(
            id=company_role_id,
            company=company,
            is_active=True,
        ).first()

    ensure_default_company_roles(company)

    default_name = SYSTEM_ROLE_TO_DEFAULT_ROLE_NAME.get(system_role)
    if not default_name:
        return None

    return CompanyRole.objects.filter(
        company=company,
        name__iexact=default_name,
        is_active=True,
    ).first()


def assign_missing_company_roles(company):
    from .models import UserProfile

    ensure_default_company_roles(company)
    updated = 0

    profiles = UserProfile.objects.filter(
        company=company,
        company_role__isnull=True,
        role__in=SYSTEM_ROLE_TO_DEFAULT_ROLE_NAME.keys(),
    )

    for profile in profiles:
        role = resolve_company_role(company, profile.role)
        if role:
            profile.company_role = role
            profile.save(update_fields=["company_role"])
            updated += 1

    return updated
