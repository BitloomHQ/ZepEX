from .models import (
    CompanyPolicy,
    CompanyRole,
    PolicyCategoryRule,
    PolicyVersion,
)


def get_active_policy_version(policy):
    if not policy:
        return None
    return PolicyVersion.objects.filter(
        policy=policy,
        status=PolicyVersion.STATUS_ACTIVE,
        is_active=True,
    ).first()


def filter_admin_policy_rules(policy, queryset=None):
    """
    Admin list/create/import should target the active policy version.
    If no active version exists yet, use legacy rules (policy_version=NULL).
    """
    qs = (
        queryset
        if queryset is not None
        else PolicyCategoryRule.objects.filter(policy=policy)
    )
    active_version = get_active_policy_version(policy)
    if active_version:
        return qs.filter(policy_version=active_version), active_version
    return qs.filter(policy_version__isnull=True), None


def get_policy_rule_for_employee(
    employee,
    category_name,
):
    policy = CompanyPolicy.objects.filter(
        company=employee.company,
    ).first()

    if not policy:
        return None

    category_name = str(
        category_name or ""
    ).strip().lower()

    active_version = get_active_policy_version(policy)

    if not active_version:
        # Fall back to legacy unversioned rules when no version is active yet.
        base_filters = {
            "policy": policy,
            "policy_version__isnull": True,
            "category_name__iexact": category_name,
            "is_active": True,
        }
    else:
        base_filters = {
            "policy": policy,
            "policy_version": active_version,
            "category_name__iexact": category_name,
            "is_active": True,
        }

    # First priority: role-specific override.
    if employee.company_role_id:
        role_rule = PolicyCategoryRule.objects.filter(
            **base_filters,
            scope=PolicyCategoryRule.SCOPE_ROLE,
            company_role=employee.company_role,
        ).first()

        if role_rule:
            return role_rule

    # Second priority: rule applying to all employees.
    return PolicyCategoryRule.objects.filter(
        **base_filters,
        scope=PolicyCategoryRule.SCOPE_ALL,
        company_role__isnull=True,
    ).first()

from .models import (
    CompanyRole,
    PolicyCategoryRule,
)


def get_effective_policy_rules(company, company_role):
    """
    Returns effective policy rules for a role.

    If a rule is not found for the requested role,
    the Employee role rule is used.
    """

    employee_role = CompanyRole.objects.filter(
        company=company,
        name__iexact="Employee",
        is_active=True,
    ).first()

    policy = CompanyPolicy.objects.filter(company=company).first()
    active_version = get_active_policy_version(policy) if policy else None

    def _rules_for_role(role):
        qs = PolicyCategoryRule.objects.filter(
            policy__company=company,
            company_role=role,
            is_active=True,
        )
        if active_version:
            return qs.filter(policy_version=active_version)
        return qs.filter(policy_version__isnull=True)

    employee_rules = {}

    if employee_role:

        for rule in _rules_for_role(employee_role):

            employee_rules[
                rule.category_name.lower()
            ] = {
                "id": str(rule.id),
                "category": rule.category_name,
                "limit": (
                    "Unlimited"
                    if rule.is_unlimited
                    else str(rule.max_amount)
                ),
                "description": rule.category_description,
                "source_role": employee_role.name,
                "inherited": False,
            }

    role_rules = _rules_for_role(company_role)

    effective = employee_rules.copy()

    for rule in role_rules:

        effective[
            rule.category_name.lower()
        ] = {
            "id": str(rule.id),
            "category": rule.category_name,
            "limit": (
                "Unlimited"
                if rule.is_unlimited
                else str(rule.max_amount)
            ),
            "description": rule.category_description,
            "source_role": company_role.name,
            "inherited": False,
        }

    if company_role != employee_role:

        for category, data in effective.items():

            if data["source_role"] == employee_role.name:
                data["inherited"] = True

    return sorted(
        effective.values(),
        key=lambda x: x["category"]
    )

from decimal import Decimal


def simulate_policy(
    *,
    company,
    company_role,
    category,
    amount,
):
    """
    Simulates whether a receipt would violate policy.
    """

    rules = get_effective_policy_rules(
        company,
        company_role,
    )

    category = category.strip().lower()

    selected_rule = None

    for rule in rules:

        if rule["category"].lower() == category:
            selected_rule = rule
            break

    if selected_rule is None:

        return {
            "allowed": False,
            "reason": "No policy rule found.",
        }

    limit = Decimal(selected_rule["limit"])

    return {
        "allowed": Decimal(amount) <= limit,
        "entered_amount": str(amount),
        "limit": str(limit),
        "category": category,
        "source_role": selected_rule["source_role"],
        "inherited": selected_rule["inherited"],
        "violation": Decimal(amount) > limit,
    }