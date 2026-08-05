from tenants.models import CompanyPolicy
from tenants.policy_utils import get_policy_rule_for_employee

from .models import ExpenseReceipt, ExpenseAuditTrail
from .audit_services import create_audit_log
from .gemini_policy_validator import (
    validate_receipt_against_policy,
)


def validate_receipt_policy(receipt: ExpenseReceipt):

    try:
        CompanyPolicy.objects.get(
            company=receipt.company
        )

    except CompanyPolicy.DoesNotExist:

        receipt.status = ExpenseReceipt.STATUS_POLICY_VIOLATION
        receipt.policy_violation_reason = "No company policy configured."
        receipt.has_any_violation = True

        receipt.save(update_fields=[
            "status",
            "policy_violation_reason",
            "has_any_violation",
        ])

        return {
            "success": False,
            "has_violations": True,
            "violations": [
                "No company policy configured."
            ],
            "next_status": receipt.status,
        }

    violations = []

    receipt.has_amount_violation = False
    receipt.has_any_violation = False
    receipt.policy_violation_reason = None

    company_currency = (
        receipt.company_currency
        or receipt.original_currency
    )

    line_items_count = receipt.line_items.count()

    # Cache Gemini response so each category is evaluated only once
    ai_results = {}

    for item in receipt.line_items.all():

        item.is_violating = False
        item.violation_reason = None

        rule = get_policy_rule_for_employee(
            employee=receipt.employee,
            category_name=item.category,
        )

        # =====================================================
        # No Policy Found
        # =====================================================

        if not rule:

            role_name = (
                receipt.employee.company_role.name
                if receipt.employee.company_role
                else "Employee"
            )

            reason = (
                f"{item.category}: No policy configured for "
                f"'{role_name}'. Employee default policy was also not found."
            )

            item.is_violating = True
            item.violation_reason = reason

            receipt.has_amount_violation = True
            violations.append(reason)

            item.save(update_fields=[
                "is_violating",
                "violation_reason",
            ])

            continue

        # =====================================================
        # AI Policy Validation (ONE Gemini call per category)
        # =====================================================

        cache_key = rule.category.name

        if cache_key not in ai_results:

            ai_results[cache_key] = validate_receipt_against_policy(
                receipt=receipt,
                rule=rule,
            )

        item_result = ai_results[cache_key].get(
            item.description,
            {
                "allowed": True,
                "reason": "",
            },
        )

        if not item_result.get("allowed", True):

            reason = item_result.get(
                "reason",
                "This expense item is not allowed by company policy.",
            )

            item.is_violating = True
            item.violation_reason = reason

            receipt.has_amount_violation = True
            violations.append(reason)

            item.save(update_fields=[
                "is_violating",
                "violation_reason",
            ])

            continue

        # =====================================================
        # Currency Conversion
        # =====================================================

        if (
            line_items_count > 1
            and receipt.original_amount
        ):

            converted_item_amount = (
                item.amount / receipt.original_amount
            ) * receipt.company_amount

        else:

            converted_item_amount = receipt.company_amount

        # =====================================================
        # Unlimited Policy
        # =====================================================

        if rule.is_unlimited:

            item.save(update_fields=[
                "is_violating",
                "violation_reason",
            ])

            continue

        # =====================================================
        # Invalid Policy
        # =====================================================

        if rule.max_amount is None:

            reason = (
                f"{item.category}: Policy is invalid because "
                "no maximum amount is configured."
            )

            item.is_violating = True
            item.violation_reason = reason

            receipt.has_amount_violation = True
            violations.append(reason)

            item.save(update_fields=[
                "is_violating",
                "violation_reason",
            ])

            continue

        # =====================================================
        # Amount Validation
        # =====================================================

        if converted_item_amount > rule.max_amount:

            reason = (
                f"{item.category}: "
                f"{converted_item_amount:.2f} "
                f"{company_currency} exceeds the allowed limit of "
                f"{rule.max_amount} {rule.currency}. "
                f"Reason: "
                f"{rule.policy_reason or 'No policy reason provided.'} "
                f"Original Amount: "
                f"{item.amount} {receipt.original_currency}."
            )

            item.is_violating = True
            item.violation_reason = reason

            receipt.has_amount_violation = True
            violations.append(reason)

        item.save(update_fields=[
            "is_violating",
            "violation_reason",
        ])

    # =====================================================
    # Final Receipt Status
    # =====================================================

    if violations:

        receipt.status = ExpenseReceipt.STATUS_POLICY_VIOLATION
        receipt.policy_violation_reason = " | ".join(violations)
        receipt.has_any_violation = True

    else:

        receipt.status = ExpenseReceipt.STATUS_VALID
        receipt.policy_violation_reason = None
        receipt.has_any_violation = False

    receipt.save(update_fields=[
        "status",
        "policy_violation_reason",
        "has_amount_violation",
        "has_any_violation",
    ])
    create_audit_log(
    receipt=receipt,
    action=ExpenseAuditTrail.ACTION_POLICY_VALIDATED,
    remarks=(
        "Policy validation failed."
        if violations
        else "Policy validation passed."
    ),
    metadata={
        "violations": violations,
        "line_items_checked": receipt.line_items.count(),
        "status": (
            "FAILED"
            if violations
            else "PASSED"
        ),
    },
)

    return {
        "success": True,
        "has_violations": bool(violations),
        "violations": violations,
        "next_status": receipt.status,
        "policy_currency": company_currency,
    }