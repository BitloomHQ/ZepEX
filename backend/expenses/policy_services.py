from collections import defaultdict

from tenants.models import CompanyPolicy
from tenants.policy_utils import get_policy_rule_for_employee

from .models import ExpenseReceipt, ExpenseAuditTrail
from .audit_services import create_audit_log
from expenses.gemini_bulk_policy_validator import (
    validate_receipt_against_policy,
)


def validate_receipt_policy(receipt: ExpenseReceipt):

    # =====================================================
    # 1. Check Company Policy
    # =====================================================

    try:
        CompanyPolicy.objects.get(
            company=receipt.company
        )

    except CompanyPolicy.DoesNotExist:

        receipt.status = (
            ExpenseReceipt.STATUS_POLICY_VIOLATION
        )

        receipt.policy_violation_reason = (
            "No company policy configured."
        )

        receipt.has_any_violation = True

        receipt.save(
            update_fields=[
                "status",
                "policy_violation_reason",
                "has_any_violation",
            ]
        )

        return {
            "success": False,
            "has_violations": True,
            "violations": [
                "No company policy configured."
            ],
            "next_status": receipt.status,
        }

    # =====================================================
    # 2. Initial State
    # =====================================================

    violations = []

    receipt.has_amount_violation = False
    receipt.has_any_violation = False
    receipt.policy_violation_reason = None

    company_currency = (
        receipt.company_currency
        or receipt.original_currency
    )

    # =====================================================
    # 3. Load ONLY ACTIVE Line Items
    # =====================================================
    #
    # Removed line item:
    #     is_removed = True
    #
    # Deleted line item:
    #     is_deleted = True
    #
    # Both must NOT participate in policy validation.
    # =====================================================

    line_items = list(
        receipt.line_items.filter(
            is_removed=False,
            is_deleted=False,
        )
    )

    line_items_count = len(line_items)

    # =====================================================
    # 4. No Active Line Items
    # =====================================================

    if not line_items:

        receipt.has_amount_violation = False
        receipt.has_any_violation = False
        receipt.policy_violation_reason = None
        receipt.status = ExpenseReceipt.STATUS_VALID

        receipt.save(
            update_fields=[
                "status",
                "has_amount_violation",
                "has_any_violation",
                "policy_violation_reason",
            ]
        )

        return {
            "success": True,
            "has_violations": False,
            "violations": [],
            "next_status": receipt.status,
            "policy_currency": company_currency,
        }

    # =====================================================
    # 5. Resolve Policy Rule for Every Active Line Item
    # =====================================================

    grouped_rules = {}

    items_without_policy = []

    for item in line_items:

        # Reset previous validation state
        item.is_violating = False
        item.violation_reason = None

        rule = get_policy_rule_for_employee(
            employee=receipt.employee,
            category_name=item.category,
        )

        if not rule:

            items_without_policy.append(item)

            continue

        cache_key = (
            rule.category_name
            .strip()
            .lower()
        )

        if cache_key not in grouped_rules:

            grouped_rules[cache_key] = {
                "rule": rule,
                "items": [],
            }

        grouped_rules[cache_key]["items"].append(item)

    # =====================================================
    # 6. Handle Items Without Policy
    # =====================================================

    for item in items_without_policy:

        role_name = "Employee"

        if (
            receipt.employee
            and receipt.employee.company_role
        ):
            role_name = (
                receipt.employee.company_role.name
            )

        reason = (
            f"{item.category}: No policy configured for "
            f"'{role_name}'. Employee default policy was "
            "also not found."
        )

        item.is_violating = True
        item.violation_reason = reason

        receipt.has_amount_violation = True

        violations.append(reason)

        if item.__class__.objects.filter(
            pk=item.pk
        ).exists():

            item.save(
                update_fields=[
                    "is_violating",
                    "violation_reason",
                ]
            )

    # =====================================================
    # 7. AI Policy Validation
    # =====================================================

    ai_results = {}

    for category_key, group in grouped_rules.items():

        rule = group["rule"]
        items = group["items"]

        try:

            ai_results[category_key] = (
                validate_receipt_against_policy(
                    items=items,
                    rule=rule,
                )
            )

        except Exception as exc:

            reason = (
                f"{rule.category_name}: "
                f"AI policy validation failed: {str(exc)}"
            )

            for item in items:

                item.is_violating = True
                item.violation_reason = reason

                receipt.has_amount_violation = True

                violations.append(reason)

                if item.__class__.objects.filter(
                    pk=item.pk
                ).exists():

                    item.save(
                        update_fields=[
                            "is_violating",
                            "violation_reason",
                        ]
                    )

            continue

    # =====================================================
    # 8. Process AI Results + Amount Rules
    # =====================================================

    for category_key, group in grouped_rules.items():

        rule = group["rule"]
        items = group["items"]

        if category_key not in ai_results:
            continue

        category_results = ai_results[
            category_key
        ]

        for item in items:

            # -------------------------------------------------
            # Get AI result by ExpenseLineItem ID
            # -------------------------------------------------

            item_result = category_results.get(
                str(item.id),
                {
                    "allowed": True,
                    "reason": "",
                },
            )

            # =================================================
            # AI Violation
            # =================================================

            if not item_result.get(
                "allowed",
                True,
            ):

                reason = item_result.get(
                    "reason",
                    "This expense item is not allowed "
                    "by company policy.",
                )

                item.is_violating = True
                item.violation_reason = reason

                receipt.has_amount_violation = True

                violations.append(reason)

                if item.__class__.objects.filter(
                    pk=item.pk
                ).exists():

                    item.save(
                        update_fields=[
                            "is_violating",
                            "violation_reason",
                        ]
                    )

                continue

            # =================================================
            # Currency Conversion
            # =================================================

            if (
                line_items_count > 1
                and receipt.original_amount
            ):

                converted_item_amount = (
                    item.amount
                    / receipt.original_amount
                ) * receipt.company_amount

            else:

                converted_item_amount = (
                    receipt.company_amount
                )

            # =================================================
            # Unlimited Policy
            # =================================================

            if rule.is_unlimited:

                if item.__class__.objects.filter(
                    pk=item.pk
                ).exists():

                    item.save(
                        update_fields=[
                            "is_violating",
                            "violation_reason",
                        ]
                    )

                continue

            # =================================================
            # Invalid Policy
            # =================================================

            if rule.max_amount is None:

                reason = (
                    f"{item.category}: Policy is invalid "
                    "because no maximum amount is configured."
                )

                item.is_violating = True
                item.violation_reason = reason

                receipt.has_amount_violation = True

                violations.append(reason)

                if item.__class__.objects.filter(
                    pk=item.pk
                ).exists():

                    item.save(
                        update_fields=[
                            "is_violating",
                            "violation_reason",
                        ]
                    )

                continue

            # =================================================
            # Amount Validation
            # =================================================

            if converted_item_amount > rule.max_amount:

                reason = (
                    f"{item.category}: "
                    f"{converted_item_amount:.2f} "
                    f"{company_currency} exceeds the "
                    f"allowed limit of "
                    f"{rule.max_amount} "
                    f"{rule.currency}. "
                    f"Reason: "
                    f"{rule.policy_reason or 'No policy reason provided.'} "
                    f"Original Amount: "
                    f"{item.amount} "
                    f"{receipt.original_currency}."
                )

                item.is_violating = True
                item.violation_reason = reason

                receipt.has_amount_violation = True

                violations.append(reason)

            # -------------------------------------------------
            # Save Item
            # -------------------------------------------------

            if item.__class__.objects.filter(
                pk=item.pk
            ).exists():

                item.save(
                    update_fields=[
                        "is_violating",
                        "violation_reason",
                    ]
                )

    # =====================================================
    # 9. Final Receipt Status
    # =====================================================

    if violations:

        receipt.status = (
            ExpenseReceipt.STATUS_POLICY_VIOLATION
        )

        receipt.policy_violation_reason = (
            " | ".join(violations)
        )

        receipt.has_any_violation = True

    else:

        receipt.status = (
            ExpenseReceipt.STATUS_VALID
        )

        receipt.policy_violation_reason = None
        receipt.has_any_violation = False

    # =====================================================
    # 10. Save Receipt
    # =====================================================

    receipt.save(
        update_fields=[
            "status",
            "policy_violation_reason",
            "has_amount_violation",
            "has_any_violation",
        ]
    )

    # =====================================================
    # 11. Audit Log
    # =====================================================

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
            "line_items_checked": len(line_items),
            "status": (
                "FAILED"
                if violations
                else "PASSED"
            ),
        },
    )

    # =====================================================
    # 12. Result
    # =====================================================

    return {
        "success": True,
        "has_violations": bool(violations),
        "violations": violations,
        "next_status": receipt.status,
        "policy_currency": company_currency,
    }