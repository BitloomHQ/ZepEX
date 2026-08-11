import base64
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

from tenants.models import CompanyPolicy, PolicyCategoryRule
from .models import (
    ExpenseLineItem,
    ExpenseReceipt,
    ExpenseReport,
    DuplicateReceiptLog,
    ExpenseAttachment,
)
import hashlib

from .policy_services import validate_receipt_policy
from .receipt_linker import link_receipt
from .duplicate_checker import find_duplicate_receipt
from tenants.language_utils import get_company_output_language
from django.db import transaction
from decimal import InvalidOperation
from .audit_services import create_audit_log
from .models import ExpenseAuditTrail

OLD_BILL_LIMIT_DAYS = 90
AI_CONFIDENCE_THRESHOLD = Decimal("0.75")


def _link_receipt_file_attachment(line_item, receipt) -> None:
    """
    Point a line-item attachment at the receipt file without re-uploading.

    Re-assigning receipt.receipt_file to another FileField re-saves the object
    (and can fail or duplicate blobs on S3-compatible storage).
    """
    if not receipt.receipt_file:
        return

    attachment = ExpenseAttachment(
        line_item=line_item,
        receipt=receipt,
        attachment_type="receipt",
    )
    attachment.file.name = receipt.receipt_file.name
    attachment.save()


_TAX_NAME_MARKERS = (
    "tax",
    "gst",
    "cgst",
    "sgst",
    "igst",
    "vat",
    "hst",
    "pst",
    "sales t",
)

_TOTAL_NAME_MARKERS = (
    "grand total",
    "amount due",
    "balance due",
    "amount payable",
    "total due",
    "total amount",
    "net payable",
)


def _line_item_amount(item) -> Decimal:
    try:
        return Decimal(str(item.get("total_price") or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _line_item_label(item) -> str:
    return f"{item.get('name') or ''} {item.get('subcategory') or ''}".strip().lower()


def _is_tax_line_item(item) -> bool:
    label = _line_item_label(item)
    return any(marker in label for marker in _TAX_NAME_MARKERS)


def _is_total_line_item(item) -> bool:
    label = _line_item_label(item)
    if "subtotal" in label:
        return False
    if label in {"total", "totals"}:
        return True
    if any(marker in label for marker in _TOTAL_NAME_MARKERS):
        return True
    # AI sometimes dumps the whole receipt summary into one "total" row.
    text = f"{item.get('name') or ''}\n{item.get('subcategory') or ''}".lower()
    return ("total —" in text or "total -" in text) and (
        "parking fee" in text or "sales tax" in text or "gst" in text
    )


def normalize_bill_line_items(bill):
    """
    Normalize Gemini-extracted line items.

    Responsibilities:
    - Ensure line_items is always a list.
    - Normalize field names and values.
    - Remove duplicate tax line items.
    - Remove exact duplicate line items.
    - Preserve legitimate non-tax line items.
    """

    if not isinstance(bill, dict):
        return []

    raw_line_items = bill.get(
        "line_items",
        []
    )

    if not isinstance(
        raw_line_items,
        list
    ):
        raw_line_items = []

    normalized_items = []

    # ====================================================
    # Tax keywords
    # ====================================================

    tax_keywords = {
        "tax",
        "taxes",
        "sales tax",
        "sales t",
        "sales",
        "vat",
        "gst",
        "cgst",
        "sgst",
        "igst",
        "service tax",
        "tax amount",
    }

    # ====================================================
    # Track duplicate items
    # ====================================================

    seen_exact_items = set()

    # Specifically track tax items.
    # This prevents:
    #
    # Sales T   2.73
    # Sales Tax 2.73
    #
    # from becoming two DB records.
    seen_tax_items = set()

    # ====================================================
    # Process every Gemini line item
    # ====================================================

    for raw_item in raw_line_items:

        if not isinstance(
            raw_item,
            dict
        ):
            continue

        # ------------------------------------------------
        # Name
        # ------------------------------------------------

        name = str(
            raw_item.get(
                "name",
                ""
            )
            or ""
        ).strip()

        # ------------------------------------------------
        # Category
        # ------------------------------------------------

        category = str(
            raw_item.get(
                "category",
                bill.get(
                    "type",
                    "miscellaneous"
                )
            )
            or "miscellaneous"
        ).strip().lower()

        # ------------------------------------------------
        # Subcategory
        # ------------------------------------------------

        subcategory = str(
            raw_item.get(
                "subcategory",
                ""
            )
            or ""
        ).strip()

        # ------------------------------------------------
        # Quantity
        # ------------------------------------------------

        try:

            quantity = Decimal(
                str(
                    raw_item.get(
                        "quantity",
                        1
                    )
                    or 1
                )
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):

            quantity = Decimal("1")

        if quantity <= Decimal("0"):
            quantity = Decimal("1")

        # ------------------------------------------------
        # Unit price
        # ------------------------------------------------

        try:

            unit_price = Decimal(
                str(
                    raw_item.get(
                        "unit_price",
                        0
                    )
                    or 0
                )
                .replace(",", "")
                .strip()
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):

            unit_price = Decimal("0.00")

        # ------------------------------------------------
        # Total price
        # ------------------------------------------------

        raw_total_price = (
            raw_item.get(
                "total_price"
            )
        )

        if raw_total_price is None:

            raw_total_price = (
                raw_item.get(
                    "amount"
                )
            )

        try:

            total_price = Decimal(
                str(
                    raw_total_price
                    if raw_total_price is not None
                    else "0"
                )
                .replace(",", "")
                .strip()
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):

            total_price = Decimal("0.00")

        # ------------------------------------------------
        # If total price is missing, calculate it
        # ------------------------------------------------

        if (
            total_price <= Decimal("0.00")
            and unit_price > Decimal("0.00")
        ):

            total_price = (
                unit_price * quantity
            )

        # ------------------------------------------------
        # Reimbursable
        # ------------------------------------------------

        is_reimbursable = bool(
            raw_item.get(
                "is_reimbursable",
                True
            )
        )

        # ------------------------------------------------
        # Reason
        # ------------------------------------------------

        reason = str(
            raw_item.get(
                "reason",
                ""
            )
            or ""
        ).strip()

        # ====================================================
        # Normalize name for comparison
        # ====================================================

        normalized_name = (
            name.lower()
            .replace("_", " ")
            .replace("-", " ")
            .replace(".", "")
            .replace(":", "")
        )

        normalized_name = " ".join(
            normalized_name.split()
        )

        normalized_subcategory = (
            subcategory.lower()
            .replace("_", " ")
            .replace("-", " ")
        )

        normalized_subcategory = " ".join(
            normalized_subcategory.split()
        )

        # ====================================================
        # Detect tax item
        # ====================================================

        is_tax_item = (
            category in {
                "tax",
                "taxes"
            }
            or normalized_subcategory in tax_keywords
            or normalized_name in tax_keywords
            or any(
                keyword in normalized_name
                for keyword in [
                    "sales tax",
                    "sales t",
                    "tax amount",
                    "service tax",
                    "vat",
                    "gst",
                    "cgst",
                    "sgst",
                    "igst",
                ]
            )
        )

        # ====================================================
        # TAX DEDUPLICATION
        # ====================================================

        if is_tax_item:

            tax_key = (
                category,
                normalized_subcategory,
                total_price
            )

            if tax_key in seen_tax_items:

                print(
                    "\n========== DUPLICATE TAX ITEM REMOVED =========="
                )

                print(
                    "Original item:",
                    raw_item
                )

                print(
                    "Duplicate key:",
                    tax_key
                )

                print(
                    "=================================================\n"
                )

                continue

            seen_tax_items.add(
                tax_key
            )

            # Standardize tax name.
            name = "Sales Tax"

            subcategory = "Sales Tax"

            category = "taxes"

            normalized_name = "sales tax"

            normalized_subcategory = "sales tax"

        # ====================================================
        # EXACT DUPLICATE DEDUPLICATION
        # ====================================================

        exact_key = (
            normalized_name,
            category,
            normalized_subcategory,
            total_price,
        )

        if exact_key in seen_exact_items:

            print(
                "\n========== DUPLICATE LINE ITEM REMOVED =========="
            )

            print(
                "Original item:",
                raw_item
            )

            print(
                "Duplicate key:",
                exact_key
            )

            print(
                "==================================================\n"
            )

            continue

        seen_exact_items.add(
            exact_key
        )

        # ====================================================
        # Build normalized item
        # ====================================================

        normalized_item = {
            "name": name,

            "category": category,

            "subcategory": subcategory,

            "quantity": float(
                quantity
            ),

            "unit_price": str(
                unit_price
            ),

            "total_price": str(
                total_price
            ),

            "is_reimbursable": (
                is_reimbursable
            ),

            "reason": reason,
        }

        normalized_items.append(
            normalized_item
        )

    # ====================================================
    # Save normalized items back to bill
    # ====================================================

    bill["line_items"] = (
        normalized_items
    )

    # ====================================================
    # Debug output
    # ====================================================

    print(
        "\n========== NORMALIZED LINE ITEMS =========="
    )

    print(
        json.dumps(
            normalized_items,
            indent=4,
            default=str,
        )
    )

    print(
        "===========================================\n"
    )

    return normalized_items


def _line_item_text_label(description=None, subcategory=None) -> str:
    return f"{description or ''} {subcategory or ''}".strip().lower()


def _text_is_tax_line(label: str) -> bool:
    return any(marker in label for marker in _TAX_NAME_MARKERS)


def _text_is_total_line(label: str) -> bool:
    if "subtotal" in label:
        return False
    if label in {"total", "totals"}:
        return True
    if any(marker in label for marker in _TOTAL_NAME_MARKERS):
        return True
    return ("total —" in label or "total -" in label) and (
        "parking fee" in label or "sales tax" in label or "gst" in label
    )


def sanitize_receipt_line_items(receipt) -> int:
    """
    Remove zero-amount and duplicate grand-total rows from older extraction bugs.

    Those junk rows inflate original/company amounts and report totals while the UI
    hides them, which makes claim totals look wrong (e.g. $89.46 vs $44.73).
    """
    items = list(receipt.line_items.all())
    if not items:
        return 0

    deleted = 0
    keep = []

    for item in items:
        amount = item.amount or Decimal("0.00")
        label = _line_item_text_label(item.description, item.subcategory)
        if amount <= Decimal("0.00") or _text_is_total_line(label):
            item.delete()
            deleted += 1
            continue
        keep.append(item)

    if len(keep) >= 2:
        for item in list(keep):
            others = sum(
                (candidate.amount or Decimal("0.00"))
                for candidate in keep
                if candidate.id != item.id
            )
            amount = item.amount or Decimal("0.00")
            if others > Decimal("0.00") and abs(amount - others) < Decimal("0.01"):
                item.delete()
                deleted += 1
                keep = [candidate for candidate in keep if candidate.id != item.id]

    return deleted


def check_policy_violations(receipt):

    violation_reasons = []

    receipt.has_duplicate_violation = False
    receipt.has_old_bill_violation = False
    receipt.has_amount_violation = False
    receipt.has_any_violation = False
    receipt.policy_violation_reason = ""

    # =====================================================
    # 1. Smart Duplicate Receipt Validation
    # =====================================================

    duplicate = find_duplicate_receipt(
        receipt=receipt,
    )

    if duplicate:

        receipt.has_duplicate_violation = True

        violation_reasons.append(
            f"Duplicate receipt detected. Original Receipt ID: {duplicate.id}"
        )

        DuplicateReceiptLog.objects.get_or_create(
            original_receipt=duplicate,
            duplicate_receipt=receipt,
            defaults={
                "duplicate_type": DuplicateReceiptLog.DUPLICATE_SAME_EMPLOYEE,
            },
        )
        create_audit_log(
    receipt=receipt,
    action=ExpenseAuditTrail.ACTION_DUPLICATE_CHECK,
    remarks=(
        "Duplicate receipt found."
        if duplicate
        else "No duplicate receipt found."
    ),
    metadata={
        "duplicate_found": bool(duplicate),
        "original_receipt_id": (
            str(duplicate.id)
            if duplicate
            else None
        ),
    },
)

    # =====================================================
    # 2. Old Bill Validation
    # =====================================================

    if receipt.invoice_date:

        limit_date = (
            timezone.now().date()
            - timedelta(days=OLD_BILL_LIMIT_DAYS)
        )

        if receipt.invoice_date < limit_date:

            receipt.has_old_bill_violation = True

            violation_reasons.append(
                f"Receipt is older than {OLD_BILL_LIMIT_DAYS} days."
            )

    # =====================================================
    # 3. Company Policy Validation
    # =====================================================

    policy_result = validate_receipt_policy(receipt)

    receipt.has_amount_violation = policy_result["has_violations"]

    if policy_result["violations"]:
        violation_reasons.extend(
            policy_result["violations"]
        )

    # =====================================================
    # Final Result
    # =====================================================

    receipt.has_any_violation = any([
        receipt.has_duplicate_violation,
        receipt.has_old_bill_violation,
        receipt.has_amount_violation,
    ])

    receipt.policy_violation_reason = "\n".join(
        violation_reasons
    )

    if receipt.has_any_violation:
        receipt.status = ExpenseReceipt.STATUS_POLICY_VIOLATION
    else:
        receipt.status = ExpenseReceipt.STATUS_VALID

    receipt.save(update_fields=[
        "has_duplicate_violation",
        "has_old_bill_violation",
        "has_amount_violation",
        "has_any_violation",
        "policy_violation_reason",
        "status",
        "updated_at",
    ])

from .currency_services import convert_currency


def _classify_ai_error(error: str):
    message = str(error)
    lowered = message.lower()

    if any(
        phrase in lowered
        for phrase in (
            "not readable",
            "blurry",
            "unclear",
            "no valid json",
            "unsupported file type",
        )
    ):
        return (
            ExpenseReceipt.AI_FAILED,
            "Receipt image is not readable. Please upload a clearer receipt.",
            False,
        )

    if any(
        phrase in lowered
        for phrase in (
            "429",
            "rate limit",
            "busy",
            "overload",
            "resource_exhausted",
            "heavy traffic",
            "temporarily unavailable",
        )
    ):
        return (
            ExpenseReceipt.AI_RETRY_REQUIRED,
            "AI service is temporarily busy. Please try again.",
            True,
        )

    return (
        ExpenseReceipt.AI_RETRY_REQUIRED,
        message,
        True,
    )


def _apply_ai_failure(receipt: ExpenseReceipt, error: str):
    ai_status, user_message, retry_allowed = _classify_ai_error(error)

    # AI failure state
    receipt.ai_status = ai_status

    # Keep the receipt status in AI Processing stage.
    # The AI status indicates whether it failed or needs a retry.
    receipt.status = ExpenseReceipt.STATUS_AI_PROCESSING

    receipt.ai_error_message = user_message

    # Increment retry count
    receipt.ai_retry_count += 1

    # Clear policy flags because AI extraction did not complete.
    receipt.policy_violation_reason = ""
    receipt.has_duplicate_violation = False
    receipt.has_old_bill_violation = False
    receipt.has_amount_violation = False
    receipt.has_any_violation = False

    receipt.save(
        update_fields=[
            "ai_status",
            "status",
            "ai_error_message",
            "ai_retry_count",
            "policy_violation_reason",
            "has_duplicate_violation",
            "has_old_bill_violation",
            "has_amount_violation",
            "has_any_violation",
            "updated_at",
        ]
    )

    if receipt.report_id:
        recalculate_report_total(receipt.report)

    return {
        "success": False,
        "retry_allowed": retry_allowed,
        "ai_status": ai_status,
        "error": user_message,
        "receipt_id": str(receipt.id),
    }


def recalculate_report_total(report):
    total = Decimal("0.00")

    for receipt in report.receipts.filter(
        ai_status=ExpenseReceipt.AI_COMPLETED
    ):
        amount = receipt.company_amount
        if amount is None:
            amount = receipt.total_amount
        total += amount or Decimal("0.00")

    report.total_amount = total
    report.save(update_fields=["total_amount", "updated_at"])


def resync_draft_receipts_to_company_currency(company):
    """
    Re-apply the company's current base currency to draft-report receipts.

    Draft expenses keep the currency used at extraction time unless we refresh
    them after finance settings change (e.g. ALL -> ARS).
    """
    from .currency_services import convert_currency

    try:
        finance_settings = company.finance_settings
    except Exception:
        return 0

    if not finance_settings or not finance_settings.base_currency_id:
        return 0

    target_currency = finance_settings.base_currency.code.upper()
    updated = 0

    draft_reports = ExpenseReport.objects.filter(
        company=company,
        status=ExpenseReport.STATUS_DRAFT,
    ).prefetch_related("receipts", "receipts__line_items")

    for report in draft_reports:
        report_changed = False

        for receipt in report.receipts.all():
            if receipt.ai_status not in (
                ExpenseReceipt.AI_COMPLETED,
                ExpenseReceipt.AI_RETRY_REQUIRED,
            ):
                continue

            if receipt.line_items.exists():
                recalculate_receipt_from_line_items(receipt)
            else:
                original_amount = (
                    receipt.original_amount or receipt.total_amount or Decimal("0.00")
                )
                original_currency = (
                    receipt.original_currency or receipt.currency or target_currency
                ).upper()

                if finance_settings.auto_currency_conversion:
                    conversion_result = convert_currency(
                        amount=original_amount,
                        from_currency=original_currency,
                        to_currency=target_currency,
                        company=receipt.company,
                    )
                    if conversion_result.get("success"):
                        receipt.company_amount = conversion_result["company_amount"]
                        receipt.company_currency = conversion_result["company_currency"]
                        receipt.exchange_rate = conversion_result["exchange_rate"]
                        receipt.exchange_rate_date = conversion_result[
                            "exchange_rate_date"
                        ]
                        receipt.exchange_rate_provider = conversion_result[
                            "exchange_rate_provider"
                        ]
                    else:
                        receipt.company_amount = original_amount
                        receipt.company_currency = original_currency
                        receipt.exchange_rate = None
                        receipt.exchange_rate_date = None
                        receipt.exchange_rate_provider = None
                else:
                    receipt.company_amount = original_amount
                    receipt.company_currency = original_currency
                    receipt.exchange_rate = Decimal("1")
                    receipt.exchange_rate_date = timezone.now()
                    receipt.exchange_rate_provider = "Conversion Disabled"

                receipt.total_amount = receipt.company_amount
                receipt.save(
                    update_fields=[
                        "company_amount",
                        "company_currency",
                        "total_amount",
                        "exchange_rate",
                        "exchange_rate_date",
                        "exchange_rate_provider",
                        "updated_at",
                    ]
                )
                check_policy_violations(receipt)

            report_changed = True
            updated += 1

        if report_changed:
            recalculate_report_total(report)

    return updated


def recalculate_receipt_from_line_items(receipt):
    from django.db.models import Sum

    from .currency_services import convert_currency

    sanitize_receipt_line_items(receipt)

    line_total = receipt.line_items.aggregate(total=Sum("amount"))["total"] or Decimal(
        "0.00"
    )

    if line_total <= Decimal("0.00"):
        receipt.original_amount = Decimal("0.00")
        receipt.company_amount = Decimal("0.00")
        receipt.total_amount = Decimal("0.00")
        receipt.has_duplicate_violation = False
        receipt.has_old_bill_violation = False
        receipt.has_amount_violation = False
        receipt.has_any_violation = False
        receipt.policy_violation_reason = ""
        receipt.status = ExpenseReceipt.STATUS_VALID
        receipt.save(
            update_fields=[
                "original_amount",
                "company_amount",
                "total_amount",
                "has_duplicate_violation",
                "has_old_bill_violation",
                "has_amount_violation",
                "has_any_violation",
                "policy_violation_reason",
                "status",
                "updated_at",
            ]
        )
    else:
        finance_settings = receipt.company.finance_settings
        company_currency = (
            finance_settings.base_currency.code
            if finance_settings and finance_settings.base_currency
            else receipt.company_currency or receipt.original_currency or "INR"
        ).upper()

        receipt.original_amount = line_total

        if finance_settings and finance_settings.auto_currency_conversion:
            conversion_result = convert_currency(
                amount=receipt.original_amount,
                from_currency=receipt.original_currency,
                to_currency=company_currency,
                company=receipt.company,
            )

            if conversion_result.get("success"):
                receipt.company_amount = conversion_result["company_amount"]
                receipt.company_currency = conversion_result["company_currency"]
                receipt.exchange_rate = conversion_result["exchange_rate"]
                receipt.exchange_rate_date = conversion_result["exchange_rate_date"]
                receipt.exchange_rate_provider = conversion_result[
                    "exchange_rate_provider"
                ]
            else:
                receipt.company_amount = receipt.original_amount
                receipt.company_currency = receipt.original_currency
                receipt.exchange_rate = None
                receipt.exchange_rate_date = None
                receipt.exchange_rate_provider = None
        else:
            receipt.company_amount = receipt.original_amount
            receipt.company_currency = receipt.original_currency or company_currency
            receipt.exchange_rate = Decimal("1")
            receipt.exchange_rate_date = timezone.now()
            receipt.exchange_rate_provider = "Conversion Disabled"

        receipt.total_amount = receipt.company_amount
        receipt.save(
            update_fields=[
                "original_amount",
                "company_amount",
                "company_currency",
                "total_amount",
                "exchange_rate",
                "exchange_rate_date",
                "exchange_rate_provider",
                "updated_at",
            ]
        )
        check_policy_violations(receipt)

    if receipt.report_id:
        recalculate_report_total(receipt.report)


def sync_receipt_totals_for_report(report):
    from django.db.models import Sum

    if report.status != ExpenseReport.STATUS_DRAFT:
        return False

    changed = False

    for receipt in report.receipts.all():
        removed = sanitize_receipt_line_items(receipt)

        line_total = receipt.line_items.aggregate(total=Sum("amount"))["total"] or Decimal(
            "0.00"
        )
        stored_total = receipt.original_amount or Decimal("0.00")
        stored_company = receipt.company_amount or Decimal("0.00")

        needs_sync = (
            removed > 0
            or (line_total > 0 and line_total != stored_total)
            or (line_total > 0 and stored_company != line_total and (
                not receipt.company_currency
                or (receipt.original_currency or "").upper()
                == (receipt.company_currency or "").upper()
            ))
        )

        if needs_sync:
            recalculate_receipt_from_line_items(receipt)
            changed = True

    if changed:
        recalculate_report_total(report)

    return changed


def extract_receipt_with_gemini(receipt: ExpenseReceipt):
    """
    Extract receipt information using Gemini.

    Behaviour:
    - Reads receipts written in any language.
    - Returns human-readable fields in the company's configured language.
    - Preserves original-language receipt text.
    - Keeps category, currency, amount and date normalized.
    - Produces item-wise food descriptions.
    - Produces 5–6 concise points for other receipt categories.
    """

    receipt.status = ExpenseReceipt.STATUS_AI_PROCESSING
    receipt.ai_status = ExpenseReceipt.AI_PROCESSING
    create_audit_log(
    receipt=receipt,
    action=ExpenseAuditTrail.ACTION_AI_STARTED,
    remarks="AI receipt extraction started.",
)
    receipt.ai_error_message = None

    receipt.save(
        update_fields=[
            "status",
            "ai_status",
            "ai_error_message",
            "updated_at",
        ]
    )

    # ========================================================
    # Company language configuration
    # ========================================================

    language_settings = get_company_output_language(
        receipt.company
    )

    output_language_code = (
        language_settings.get("code")
        or "en"
    )

    output_language_name = (
        language_settings.get("name")
        or "English"
    )

    preserve_original_text = bool(
        language_settings.get(
            "preserve_original_text",
            True,
        )
    )

    # ========================================================
    # Gemini prompt
    # ========================================================

    prompt = prompt = prompt = f"""
You are ZepEx Receipt Intelligence, an expert multilingual receipt,
invoice, expense, travel-document and financial-document extraction engine.

The uploaded document may contain one or multiple receipts, invoices,
checks, tickets, bills, parking receipts, restaurant receipts, hotel
bills, fuel receipts, medical bills, travel documents, or other
financial documents.

============================================================
PRIMARY RESPONSIBILITY
============================================================

YOUR PRIMARY RESPONSIBILITY IS COMPLETE AND ACCURATE EXTRACTION.

The receipt/document itself is the source of truth.

You MUST extract EVERY readable purchased item and EVERY separately
payable monetary charge appearing on the receipt.

Do NOT summarize away line items.

Do NOT omit readable line items.

Do NOT merge separate purchased items.

Do NOT duplicate the same payable charge.

Do NOT invent unreadable information.

Do NOT perform backend policy validation.

============================================================
CRITICAL LINE ITEM RULE
============================================================

EVERY READABLE MONETARY ROW OR SEPARATELY PAYABLE CHARGE ON THE
RECEIPT MUST BE ANALYZED INDIVIDUALLY.

If the receipt contains:

Description        Qty       Rate       Amount

ITEM A             1        149.00      149.00
ITEM B             1         95.24       95.24
ITEM C             1         61.90       61.90

then line_items MUST contain THREE separate objects.

NEVER return:

Food = 306.14

NEVER combine multiple products into one generic item.

NEVER return only the bill total.

NEVER return only the subtotal.

NEVER omit a product because it belongs to the same category as
another product.

EVERY readable purchased product MUST have its OWN line item.

EVERY separately payable monetary charge MUST have its OWN line item.

============================================================
PRICE EXTRACTION
============================================================

For EVERY readable line item extract:

- name
- category
- subcategory
- quantity
- unit_price
- total_price
- is_reimbursable
- reason

Each line item MUST have its OWN monetary value.

For every readable item, identify the price belonging specifically
to THAT item.

If the receipt contains:

Qty | Rate | Amount

use:

quantity = Qty
unit_price = Rate
total_price = Amount

Example:

BHALLA PAPRI CHAAT     1     149.00     149.00

Return:

{{
    "name": "BHALLA PAPRI CHAAT",
    "quantity": 1,
    "unit_price": 149.00,
    "total_price": 149.00
}}

If the receipt contains only:

ITEM 149.00

then:

quantity = null
unit_price = null
total_price = 149.00

If the receipt explicitly shows quantity 1:

quantity = 1

Do NOT assume quantity = 1 when it is not supported by the receipt.

NEVER assign the subtotal or grand total as the price of an item.

NEVER copy the same price into multiple line items unless the
receipt actually shows that same charge multiple times.

============================================================
COMPLETE ITEM NAME RULE
============================================================

Preserve the COMPLETE readable item name.

Do NOT truncate an item name because the final characters are close
to the price column.

Read the complete description column before assigning its price.

For example:

BHALLA PAPRI CHAAT

must be extracted as:

BHALLA PAPRI CHAAT

NOT:

BHALLA PAPRI CHAA

If part of the item name is genuinely unreadable, preserve the
readable portion.

Do not invent missing characters.

============================================================
EXAMPLE RECEIPT PRICE MAPPING
============================================================

For a receipt containing:

BHALLA PAPRI CHAAT       149.00
SWEET LASSI               95.24
MASALA CHAACH             61.90

the model MUST map:

BHALLA PAPRI CHAAT -> 149.00
SWEET LASSI -> 95.24
MASALA CHAACH -> 61.90

Do NOT combine them.

Do NOT assign the subtotal to any item.

Do NOT assign the grand total to any item.

============================================================
MULTIPLE RECEIPTS
============================================================

The uploaded image/PDF may contain multiple independent receipts.

Create ONE object inside "bills" for EACH genuinely independent
receipt/check/invoice.

For example:

Receipt 1 -> bills[0]
Receipt 2 -> bills[1]
Receipt 3 -> bills[2]

Do NOT create separate bills for:

- individual food items
- individual taxes
- individual fees
- pages belonging to the same receipt
- QR codes
- barcodes
- payment information
- receipt numbers

Multiple items on one receipt belong inside the SAME bill object's
line_items.

============================================================
DOCUMENT LANGUAGE
============================================================

Detect the original document language.

Configured company output language:

- Name: {output_language_name}
- Code: {output_language_code}
- Preserve original text:
  {str(preserve_original_text).lower()}

Return generated human-readable fields in:

{output_language_name} ({output_language_code})

The following generated fields MUST use the configured company
language:

- document_summary
- additional_info
- line_items.name
- extraction_notes
- translated_original_text
- review_notes

Do NOT translate or modify:

- vendor/legal merchant name
- invoice number
- receipt number
- ticket number
- PNR
- flight number
- train number
- seat number
- tax registration number
- payment reference
- transaction ID
- numeric amounts
- currency codes
- dates

============================================================
NO INVENTION
============================================================

NEVER invent:

- item names
- quantities
- prices
- taxes
- tax percentages
- dates
- totals
- vendor names
- invoice numbers
- payment information
- categories for unreadable text

If a value is readable, extract it.

If partially readable, preserve the readable portion.

If a value cannot be determined:

- use null for numeric fields
- use "" for string fields
- use [] for arrays

============================================================
DOCUMENT TYPE
============================================================

Return "type" as exactly one of:

food
hotel
flight_ticket
train_ticket
car_rental
fuel
gas
parking
office_supplies
medical
courier
telecom
training
relocation
wfh
miscellaneous

Examples:

restaurant / meal / lunch / dinner / breakfast
-> food

hotel / lodging / accommodation / room
-> hotel

airfare / airline ticket / boarding pass
-> flight_ticket

railway ticket / train ticket
-> train_ticket

petrol / diesel / gasoline
-> fuel

parking receipt / parking ticket
-> parking

medicine / pharmacy / medical service
-> medical

mobile / internet / broadband
-> telecom

stationery / printer paper / office supplies
-> office_supplies

taxi / car hire / rental vehicle
-> car_rental

Anything else
-> miscellaneous

============================================================
VENDOR
============================================================

vendor must contain ONLY the merchant/business/provider name.

Example:

"JW Marriott Grande Lakes"

"Mithaas Sweets & Restaurant Pvt. Ltd."

Do NOT include:

- address
- phone number
- GST number
- tax registration number
- website
- additional sentences

Preserve the official merchant name when readable.

If unreadable:

""

============================================================
DATE
============================================================

bill_date MUST use:

YYYY-MM-DD

Use the transaction/invoice/purchase date printed on the receipt.

For:

- hotel -> invoice/transaction date
- restaurant -> transaction date
- parking -> transaction date
- fuel -> transaction date
- medical -> invoice date
- flight/train -> issue date when available

Travel date belongs in additional_info.

If date cannot be reliably determined:

null

============================================================
FINAL AMOUNT
============================================================

"amount" MUST be the final payable/grand total for that receipt.

Never use:

- subtotal
- tax amount
- tip amount
- balance
- cash tendered
- change returned

when a final payable amount is available.

Example:

Subtotal = 306.14
CGST = 7.66
SGST = 7.66
Grand Total = 321.46

Then:

amount = 321.46
grand_total = 321.46
subtotal = 306.14

If the receipt explicitly says:

Amount Including GST = 321.46

then:

amount = 321.46
grand_total = 321.46

Preserve decimal values exactly.

If the final total is unreadable:

null

============================================================
CURRENCY
============================================================

Return ISO 4217 currency codes:

INR
USD
EUR
GBP
AED
JPY
CAD
AUD
SGD

Determine currency using:

- currency symbol
- currency name
- country
- document context

Do NOT perform currency conversion.

If currency cannot be determined:

""

============================================================
EVERY LINE ITEM MUST BE EXTRACTED
============================================================

EVERY actual purchased product or separately payable charge MUST
become ONE line item.

Each line item MUST contain:

- name
- category
- subcategory
- quantity
- unit_price
- total_price
- is_reimbursable
- reason

Examples of items that MUST be extracted:

- food
- drinks
- alcohol
- parking
- fuel
- toll
- hotel room
- laundry
- minibar
- internet
- taxi
- service charge
- delivery fee
- convenience fee
- booking fee
- GST
- CGST
- SGST
- IGST
- VAT
- Sales Tax
- tip
- gratuity
- discount

============================================================
LINE ITEM ORDER
============================================================

Preserve EXACT top-to-bottom order of actual payable items as they
appear on the receipt.

Example:

1. Burger
2. Fries
3. Coffee
4. Service Charge
5. CGST
6. SGST
7. Tip

Return line_items in exactly that order.

Do NOT sort alphabetically.

Do NOT reorder by category.

Do NOT reorder by price.

============================================================
LINE ITEM CATEGORIES
============================================================

Every readable line item MUST have its own category.

Do NOT simply inherit the bill category.

Allowed categories include:

food
beverages
alcohol
hotel
flight_ticket
train_ticket
car_rental
fuel
gas
parking
office_supplies
medical
courier
telecom
training
relocation
wfh
taxes
fees
gratuity
discount
toll
miscellaneous

Examples:

Restaurant meal
-> food

Paneer Butter Masala
-> food

Coffee
-> beverages

Beer
-> alcohol

Hotel room
-> hotel

Parking Fee
-> parking

Petrol
-> fuel

Medicine
-> medical

Printer Paper
-> office_supplies

Internet
-> telecom

Taxi
-> car_rental

GST
-> taxes

CGST
-> taxes

SGST
-> taxes

Sales Tax
-> taxes

Service Charge
-> fees

Tip
-> gratuity

Discount
-> discount

Never leave category empty when the line item is readable.

============================================================
SUBCATEGORY
============================================================

Every readable line item MUST have a specific subcategory.

Use the exact visible charge whenever possible.

Examples:

Parking Fee
-> category = parking
-> subcategory = Parking Fee

Sales Tax
-> category = taxes
-> subcategory = Sales Tax

GST
-> category = taxes
-> subcategory = GST

CGST
-> category = taxes
-> subcategory = CGST

SGST
-> category = taxes
-> subcategory = SGST

IGST
-> category = taxes
-> subcategory = IGST

VAT
-> category = taxes
-> subcategory = VAT

Service Charge
-> category = fees
-> subcategory = Service Charge

Delivery Fee
-> category = fees
-> subcategory = Delivery Fee

Tip
-> category = gratuity
-> subcategory = Tip

Room Charge
-> category = hotel
-> subcategory = Room Charge

Laundry
-> category = hotel
-> subcategory = Laundry

Mini Bar
-> category = hotel
-> subcategory = Mini Bar

Coffee
-> category = beverages
-> subcategory = Coffee

Tea
-> category = beverages
-> subcategory = Tea

Juice
-> category = beverages
-> subcategory = Juice

Soft Drink
-> category = beverages
-> subcategory = Soft Drink

Lassi
-> category = beverages
-> subcategory = Lassi

Buttermilk
-> category = beverages
-> subcategory = Buttermilk

Beer
-> category = alcohol
-> subcategory = Beer

Wine
-> category = alcohol
-> subcategory = Wine

Whiskey
-> category = alcohol
-> subcategory = Whiskey

Vodka
-> category = alcohol
-> subcategory = Vodka

Burger
-> category = food
-> subcategory = Burger

Pizza
-> category = food
-> subcategory = Pizza

French Fries
-> category = food
-> subcategory = Snacks

Paneer Butter Masala
-> category = food
-> subcategory = Vegetarian

Chicken Curry
-> category = food
-> subcategory = Non Vegetarian

Fish Fry
-> category = food
-> subcategory = Seafood

============================================================
FOOD AND BEVERAGE SUBCATEGORIES
============================================================

Allowed examples:

Vegetarian
Non Vegetarian
Seafood
Alcohol
Beer
Wine
Whiskey
Vodka
Rum
Cocktail
Soft Drink
Coffee
Tea
Juice
Lassi
Buttermilk
Dessert
Bakery
Fast Food
Pizza
Burger
Sandwich
Rice
Noodles
Pasta
Breakfast
Lunch
Dinner
Snacks
Ice Cream
Fruit
Main Course
Bread
Unknown

Examples:

Paneer Butter Masala
-> Vegetarian

Dal Tadka
-> Vegetarian

Chicken Curry
-> Non Vegetarian

Fish Fry
-> Seafood

Cappuccino
-> Coffee

Latte
-> Coffee

Orange Juice
-> Juice

Coca Cola
-> Soft Drink

Sweet Lassi
-> Lassi

Masala Chaach
-> Buttermilk

Chocolate Cake
-> Dessert

Croissant
-> Bakery

Pizza
-> Pizza

Burger
-> Burger

French Fries
-> Snacks

If the exact classification cannot be reliably determined,
use the most appropriate visible/contextual category.

Do NOT invent a specific subcategory unsupported by the receipt.

============================================================
IMPORTANT FOOD RECEIPT EXAMPLE
============================================================

If the receipt shows:

BHALLA PAPRI CHAAT       1     149.00     149.00
SWEET LASSI              1      95.24      95.24
MASALA CHAACH            1      61.90      61.90

you MUST return THREE separate product line items.

BHALLA PAPRI CHAAT:

category = food
subcategory = Vegetarian
quantity = 1
unit_price = 149.00
total_price = 149.00

SWEET LASSI:

category = beverages
subcategory = Lassi
quantity = 1
unit_price = 95.24
total_price = 95.24

MASALA CHAACH:

category = beverages
subcategory = Buttermilk
quantity = 1
unit_price = 61.90
total_price = 61.90

Do NOT return only:

food = 306.14

Do NOT merge:

BHALLA PAPRI CHAAT + SWEET LASSI + MASALA CHAACH

into one item.

============================================================
TAX EXTRACTION
============================================================

Taxes require special handling because receipts may show:

A. item-level tax calculations/breakdowns

and/or

B. final aggregate payable taxes.

You MUST distinguish between them.

============================================================
ITEM-LEVEL TAX BREAKDOWN
============================================================

Example:

SWEET LASSI       95.24
GST Amt            4.76

MASALA CHAACH     61.90
GST Amt            3.10

Later:

GST                7.66

If 4.76 and 3.10 are item-level GST calculations and 7.66 is the
aggregate payable GST:

DO NOT create:

GST 4.76
GST 3.10
GST 7.66

as three payable tax line items.

Create only:

GST 7.66

as the payable tax line item.

The 4.76 and 3.10 values may be preserved in tax information when
useful, but MUST NOT be double-counted.

============================================================
CRITICAL CGST AND SGST RULE
============================================================

If the receipt visibly prints multiple final tax components,
EVERY separately payable tax component MUST be extracted.

For example, if the receipt shows:

Subtotal = 306.14
CGST = 7.66
SGST = 7.66
Grand Total = 321.46

then BOTH CGST and SGST are actual payable taxes.

The output MUST contain:

CGST = 7.66

AND:

SGST = 7.66

Do NOT return only one of them.

Do NOT combine them into a single tax line.

CGST and SGST are NOT duplicates when both are separately printed
as payable tax components.

CGST and SGST MUST be represented separately in line_items.

CGST:

name = "CGST"
category = "taxes"
subcategory = "CGST"
quantity = null
unit_price = null
total_price = 7.66

SGST:

name = "SGST"
category = "taxes"
subcategory = "SGST"
quantity = null
unit_price = null
total_price = 7.66

They MUST also be represented separately in the taxes array.

Example:

"taxes": [
    {{
        "type": "CGST",
        "percentage": 2.5,
        "amount": 7.66
    }},
    {{
        "type": "SGST",
        "percentage": 2.5,
        "amount": 7.66
    }}
]

If the percentages are not visible, use:

percentage = null

Do NOT invent percentages.

============================================================
TAX DUPLICATION RULE
============================================================

NEVER duplicate the same tax component.

Before adding any tax line item, determine:

1. Is this an actual payable charge?
2. Is this only an item-level calculation/breakdown?
3. Is the same tax component already represented elsewhere?
4. Is this the final aggregate payable tax?
5. Are CGST and SGST separate tax components?

Examples of BAD extraction:

Sales Tax 2.73
Sales Tax 2.73

GOOD:

Sales Tax 2.73

Another BAD extraction:

GST 4.76
GST 3.10
GST 7.66

when 4.76 and 3.10 are item-level calculations and 7.66 is the
final aggregate payable GST.

GOOD:

GST 7.66

However:

CGST 7.66
SGST 7.66

is NOT a duplicate.

GOOD:

CGST 7.66
SGST 7.66

when both are separately printed payable taxes.

============================================================
TAXES ARRAY
============================================================

The "taxes" array should contain actual tax information.

Example:

"taxes": [
    {{
        "type": "GST",
        "percentage": 5,
        "amount": 7.66
    }}
]

If CGST and SGST are separately payable:

"taxes": [
    {{
        "type": "CGST",
        "percentage": 2.5,
        "amount": 7.66
    }},
    {{
        "type": "SGST",
        "percentage": 2.5,
        "amount": 7.66
    }}
]

Do NOT invent tax percentages.

If percentage is not visible:

percentage = null

============================================================
FEES AND SERVICE CHARGES
============================================================

If separately printed and payable, create a separate line item for:

- Service Charge
- Delivery Fee
- Convenience Fee
- Booking Fee
- Resort Fee
- Parking Fee
- Toll
- other separately payable fees

Each MUST have its own:

name
category
subcategory
quantity
unit_price
total_price
is_reimbursable
reason

Do NOT merge fees into the product price.

============================================================
TIP / GRATUITY
============================================================

If tip/gratuity is printed or handwritten:

Create a separate line item.

Example:

Tip = 20.00

Return:

name = "Tip"
category = "gratuity"
subcategory = "Tip"
total_price = 20.00

Also:

bill.tip = 20.00

Do NOT include the tip inside another item's price.

============================================================
DISCOUNT
============================================================

If a discount is printed:

Create a separate line item.

Example:

Discount = -20.00

Return:

category = discount
subcategory = Discount
total_price = -20.00

Do not hide discounts inside subtotal.

============================================================
TOTALS ARE NOT LINE ITEMS
============================================================

NEVER create line items named:

Total
Grand Total
Amount Due
Amount Including GST
Final Total
Subtotal

These belong only in:

subtotal
discount
tip
service_charge
grand_total
amount

Example:

Subtotal = 306.14
CGST = 7.66
SGST = 7.66
Grand Total = 321.46

Return:

subtotal = 306.14
grand_total = 321.46
amount = 321.46

line_items:

BHALLA PAPRI CHAAT = 149.00
SWEET LASSI = 95.24
MASALA CHAACH = 61.90
CGST = 7.66
SGST = 7.66

============================================================
TOTAL CONSISTENCY
============================================================

Whenever possible:

sum of actual payable line_items.total_price
approximately equals the final grand_total.

However:

DO NOT force mathematical equality.

DO NOT invent a missing charge.

DO NOT modify a printed amount.

DO NOT assign a difference to an arbitrary item.

If there is a legitimate rounding difference, preserve the printed
values and explain it in extraction_notes.

For example:

149.00
+ 95.24
+ 61.90
+ 7.66
+ 7.66
= 321.46

Therefore, for the example receipt:

subtotal = 306.14
CGST = 7.66
SGST = 7.66
grand_total = 321.46
amount = 321.46

============================================================
REIMBURSABILITY
============================================================

Extraction and reimbursement are separate operations.

ALWAYS include the item even if it is potentially non-reimbursable.

Default:

"is_reimbursable": true

unless the receipt clearly identifies it as personal/non-business.

Potential examples:

Cigarettes
Personal shopping
Gift item

Then:

"is_reimbursable": false

"reason": "Personal expense"

Normal business expenses:

"is_reimbursable": true

"reason": ""

The extraction model MUST NOT perform backend policy validation.

Do NOT return:

"No policy configured for Employee"

"AI policy validation failed"

"validate_receipt_against_policy"

"Over limit"

"Policy not found"

"Duplicate receipt detected"

"Old bill"

The backend policy engine handles those decisions separately.

============================================================
ADDITIONAL INFO FOR FOOD RECEIPTS
============================================================

For food receipts, additional_info MUST contain numbered points
for EVERY readable food/drink item and every actual payable tax/fee.

Example:

1. BHALLA PAPRI CHAAT — 1 × INR 149.00 — INR 149.00
2. SWEET LASSI — 1 × INR 95.24 — INR 95.24
3. MASALA CHAACH — 1 × INR 61.90 — INR 61.90
4. CGST — INR 7.66
5. SGST — INR 7.66
6. Total — INR 321.46

Do NOT omit readable items.

============================================================
OTHER DOCUMENT TYPES
============================================================

For other receipt types include useful visible details.

HOTEL:

- room type
- guest
- check-in
- check-out
- nights
- room charge
- taxes
- total

FLIGHT:

- airline
- flight number
- route
- passenger
- travel date
- departure
- arrival
- class
- seat
- PNR
- fare

TRAIN:

- train number
- train name
- route
- passenger
- travel date
- class
- coach
- seat
- PNR
- fare

FUEL:

- fuel type
- quantity
- rate
- station
- vehicle number
- payment
- total

PARKING:

- location
- entry
- exit
- duration
- vehicle
- parking fee
- tax
- total

MEDICAL:

- medicine/service
- quantity
- doctor/hospital
- tax
- total

============================================================
PAYMENT
============================================================

Extract when visible:

Cash
Credit Card
Debit Card
UPI
Google Pay
Apple Pay
Bank Transfer
Other

Extract:

method
card_last_four
transaction_id
reference_number

Do not invent missing values.

============================================================
DOCUMENT REFERENCES
============================================================

Extract references such as:

Invoice Number
Receipt Number
Ticket Number
Booking ID
PNR
Transaction ID

Return:

document_reference.reference_type
document_reference.reference_number
document_reference.linked_reference_number

Examples:

Hotel Booking:
reference_type = hotel_booking

Hotel Invoice:
reference_type = hotel_invoice

Flight:
reference_type = flight_ticket

Train:
reference_type = train_ticket

Parking:
reference_type = parking_receipt

If this document clearly references another document,
put that number into linked_reference_number.

Otherwise:

""

============================================================
RECEIPT FINGERPRINT
============================================================

Create a duplicate-detection fingerprint using:

merchant
document_number
bill_date
amount
currency

merchant in the fingerprint may be normalized.

Remove legal suffixes when appropriate:

Pvt Ltd
Pvt. Ltd.
Limited
Inc.
LLC

Do NOT change the actual vendor field.

============================================================
RECEIPT QUALITY
============================================================

Evaluate only visible evidence.

Check:

- image editing
- cropping
- unusual formatting
- missing total
- handwriting
- missing merchant
- inconsistent totals
- suspicious formatting
- duplicate appearance

Do NOT accuse the user of fraud.

Return probabilities only.

Possible status:

EXCELLENT
GOOD
FAIR
POOR

Possible issues:

blur
cropped
low resolution
shadow
reflection
folded paper
missing corners
handwritten over receipt
partial receipt
multiple receipts

Never invent an issue.

============================================================
DOCUMENT METADATA
============================================================

Detect:

QR
Barcode
Signature
Stamp
Handwriting

Also detect document type:

Restaurant
Hotel
Invoice
Medical
Parking
Flight
Train
Fuel
etc.

============================================================
SUPPORTING DOCUMENTS
============================================================

Determine whether supporting documents are reasonably required.

Examples:

Flight:
Boarding Pass / Airline Invoice

Hotel:
Hotel Invoice

Train:
Railway Ticket

Fuel:
Fuel Receipt

Taxi:
Trip Receipt

Medical:
Prescription if reasonably required

Restaurant:
Restaurant Receipt

Do not invent missing documents.

============================================================
FINAL INTERNAL EXTRACTION CHECK
============================================================

Before returning JSON, internally inspect the COMPLETE receipt
from TOP TO BOTTOM.

Perform this checklist:

1. Did I extract every readable product?
2. Did I extract every readable food item?
3. Did I extract every readable drink?
4. Did I extract every alcohol item?
5. Did I extract every parking/fuel/toll charge?
6. Did I extract every hotel charge?
7. Did I extract every medical item?
8. Did I extract every office-supply item?
9. Did I extract every telecom charge?
10. Did I extract every service charge?
11. Did I extract every fee?
12. Did I extract every actual payable tax?
13. If CGST is printed, did I extract CGST?
14. If SGST is printed, did I extract SGST?
15. If CGST and SGST are both printed, did I preserve both separately?
16. Did I extract tip/gratuity?
17. Did I extract discounts?
18. Did I accidentally extract subtotal as a line item?
19. Did I accidentally extract grand total as a line item?
20. Did I accidentally duplicate a tax?
21. Did I accidentally duplicate a fee?
22. Does every readable line item have category?
23. Does every readable line item have subcategory?
24. Does every visible quantity appear correctly?
25. Does every visible rate appear correctly?
26. Does every visible item amount appear correctly?
27. Does each line item have its own price?
28. Are line items in receipt order?
29. Does bill.amount equal the final payable amount?
30. Does grand_total equal the printed grand total?
31. Is the currency correct?
32. Is the bill date correct?
33. Is vendor only the merchant name?
34. Did I preserve the complete readable item name?
35. Did I avoid truncating product names?
36. Did I avoid treating tax breakdowns as separate payable taxes?
37. Did I distinguish CGST and SGST as separate payable components?

============================================================
CRITICAL EXAMPLE
============================================================

If the uploaded receipt visibly contains:

BHALLA PAPRI CHAAT       149.00
SWEET LASSI                95.24
MASALA CHAACH              61.90

Subtotal                    306.14

CGST                          7.66
SGST                          7.66

Amount Including GST        321.46

then the line_items MUST contain:

{{
    "name": "BHALLA PAPRI CHAAT",
    "category": "food",
    "subcategory": "Vegetarian",
    "quantity": 1,
    "unit_price": 149.00,
    "total_price": 149.00,
    "is_reimbursable": true,
    "reason": ""
}}

{{
    "name": "SWEET LASSI",
    "category": "beverages",
    "subcategory": "Lassi",
    "quantity": 1,
    "unit_price": 95.24,
    "total_price": 95.24,
    "is_reimbursable": true,
    "reason": ""
}}

{{
    "name": "MASALA CHAACH",
    "category": "beverages",
    "subcategory": "Buttermilk",
    "quantity": 1,
    "unit_price": 61.90,
    "total_price": 61.90,
    "is_reimbursable": true,
    "reason": ""
}}

{{
    "name": "CGST",
    "category": "taxes",
    "subcategory": "CGST",
    "quantity": null,
    "unit_price": null,
    "total_price": 7.66,
    "is_reimbursable": true,
    "reason": ""
}}

{{
    "name": "SGST",
    "category": "taxes",
    "subcategory": "SGST",
    "quantity": null,
    "unit_price": null,
    "total_price": 7.66,
    "is_reimbursable": true,
    "reason": ""
}}

The bill MUST contain:

"subtotal": 306.14
"grand_total": 321.46
"amount": 321.46

The taxes MUST contain:

{{
    "type": "CGST",
    "percentage": 2.5,
    "amount": 7.66
}}

and:

{{
    "type": "SGST",
    "percentage": 2.5,
    "amount": 7.66
}}

IMPORTANT:

Do NOT return only:

GST = 7.66

when the receipt actually shows:

CGST = 7.66
SGST = 7.66

Do NOT calculate:

306.14 + 7.66 = 313.80

when both CGST and SGST are payable.

The correct final total is:

306.14 + 7.66 + 7.66 = 321.46

============================================================
OUTPUT
============================================================

Return exactly ONE valid JSON object.

Return JSON only.

Do not use Markdown.

Do not use code fences.

Do not return explanations outside JSON.

Use this exact structure:

{{
    "document_language": "",
    "document_language_code": "",
    "document_summary": "",

    "bills": [
        {{
            "type": "miscellaneous",
            "amount": null,
            "currency": "",
            "bill_date": null,

            "vendor": "",
            "merchant_type": "",
            "merchant_country": "",
            "merchant_city": "",

            "document_reference": {{
                "reference_type": "",
                "reference_number": "",
                "linked_reference_number": ""
            }},

            "receipt_fingerprint": {{
                "merchant": "",
                "document_number": "",
                "bill_date": "",
                "amount": "",
                "currency": ""
            }},

            "additional_info": "",

            "line_items": [
                {{
                    "name": "",
                    "category": "",
                    "subcategory": "",
                    "quantity": null,
                    "unit_price": null,
                    "total_price": null,
                    "is_reimbursable": true,
                    "reason": ""
                }}
            ],

            "taxes": [
                {{
                    "type": "",
                    "percentage": null,
                    "amount": null
                }}
            ],

            "subtotal": null,
            "discount": null,
            "tip": null,
            "service_charge": null,
            "grand_total": null,

            "original_text": null,
            "translated_original_text": "",

            "source_language": "",
            "source_language_code": "",

            "extraction_notes": "",

            "confidence": {{
                "translation": {{
                    "source_language": "",
                    "target_language": "",
                    "confidence": 0.0
                }},
                "overall": 0.0,
                "vendor": 0.0,
                "amount": 0.0,
                "currency": 0.0,
                "bill_date": 0.0,
                "category": 0.0,
                "translation": 0.0
            }},

            "receipt_quality": {{
                "score": 0.0,
                "status": "",
                "issues": []
            }}
        }}
    ],

    "fraud_analysis": {{
        "suspicious": false,
        "duplicate_probability": 0.0,
        "edited_probability": 0.0,
        "reasons": []
    }},

    "ai_recommendation": {{
        "decision": "",
        "confidence": 0.0,
        "reason": ""
    }},

    "document_validation": {{
        "is_complete": true,
        "required_documents": [],
        "uploaded_documents": [],
        "missing_documents": []
    }},

    "document_metadata": {{
        "receipt_type": "",
        "page_count": 1,
        "contains_handwriting": false,
        "contains_signature": false,
        "contains_stamp": false,
        "contains_qr": false,
        "contains_barcode": false
    }},

    "payment": {{
        "method": "",
        "card_last_four": "",
        "transaction_id": "",
        "reference_number": ""
    }},

    "review_notes": [],

    "ocr_confidence": 0.0
}}

============================================================
FINAL RULES
============================================================

The receipt is the source of truth.

EXTRACT EVERYTHING READABLE.

Every readable purchased item gets its own line item.

Every separately payable monetary charge gets its own line item.

Every line item gets:

name
category
subcategory
quantity
unit_price
total_price
is_reimbursable
reason

Every line item gets its OWN price.

Do not merge products.

Do not merge categories.

Do not omit drinks.

Do not omit alcohol.

Do not omit fees.

Do not omit service charges.

Do not omit payable taxes.

If CGST and SGST are separately printed as payable taxes,
extract BOTH.

Do not duplicate tax breakdowns.

Do not duplicate charges.

Do not create totals as line items.

Do not invent unreadable values.

Return valid JSON only.
"""

    # ====================================================
    # Read uploaded receipt
    # ====================================================

    
    # ====================================================
    # Read uploaded receipt
    # ====================================================

    receipt.receipt_file.open("rb")

    try:
        file_bytes = receipt.receipt_file.read()
    finally:
        receipt.receipt_file.close()

    if not file_bytes:
        raise Exception(
            "The uploaded receipt file is empty."
        )

    base64_data = base64.b64encode(
        file_bytes
    ).decode("utf-8")

    file_name = receipt.receipt_file.name
    ext = file_name.rsplit(".", 1)[-1].lower()

    mime_map = {
        "pdf": "application/pdf",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }

    mime_type = mime_map.get(ext)

    if not mime_type:
        raise Exception(
            "Unsupported file type. Please upload "
            "PDF, JPG, JPEG, PNG, or WEBP."
        )

    # ====================================================
    # Gemini REST request
    # ====================================================

    request_body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64_data,
                        }
                    },
                    {
                        "text": prompt,
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }

    response = requests.post(
        (
            f"{settings.GEMINI_API_URL}/"
            f"{settings.GEMINI_RECEIPT_MODEL}"
            ":generateContent"
        ),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": settings.GEMINI_API_KEY,
        },
        data=json.dumps(request_body),
        timeout=90,
    )

    # ====================================================
    # Parse Gemini HTTP response
    # ====================================================

    try:
        response_json = response.json()
    except ValueError as exc:
        raise Exception(
            "Gemini returned a non-JSON HTTP response."
        ) from exc

    if not response.ok:
        api_error = response_json.get(
            "error",
            {},
        )

        raise Exception(
            api_error.get(
                "message",
                (
                    "Gemini request failed with "
                    f"HTTP {response.status_code}."
                ),
            )
        )

    if "error" in response_json:
        raise Exception(
            response_json["error"].get(
                "message",
                "Gemini receipt extraction failed.",
            )
        )

    candidates = response_json.get(
        "candidates",
        []
    )

    if not candidates:
        prompt_feedback = response_json.get(
            "promptFeedback",
            {}
        )

        raise Exception(
            "Gemini returned no receipt result. "
            f"Feedback: {prompt_feedback}"
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    gemini_text = "".join(
        part.get("text", "")
        for part in parts
        if part.get("text")
    ).strip()

    if not gemini_text:
        raise Exception(
            "Gemini returned an empty receipt extraction result."
        )

    # ====================================================
    # Clean Gemini JSON
    # ====================================================

    cleaned_text = gemini_text.strip()

    if cleaned_text.startswith("```"):
        cleaned_text = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned_text,
            flags=re.IGNORECASE,
        )

        cleaned_text = re.sub(
            r"\s*```$",
            "",
            cleaned_text,
        )

    # ====================================================
    # Parse JSON
    # ====================================================

    try:
        parsed_data = json.loads(
            cleaned_text
        )

    except json.JSONDecodeError:
        match = re.search(
            r"\{.*\}",
            cleaned_text,
            re.DOTALL,
        )

        if not match:
            raise Exception(
                "No valid JSON was returned by Gemini."
            )

        parsed_data = json.loads(
            match.group(0)
        )

    print(
        "\n================ GEMINI JSON ================\n"
    )

    print(
        json.dumps(
            parsed_data,
            indent=4,
            default=str,
        )
    )

    print(
        "\n=============================================\n"
    )

    # ====================================================
    # OCR confidence
    # ====================================================

    try:
        overall_confidence = Decimal(
            str(
                parsed_data.get(
                    "ocr_confidence",
                    0,
                )
            )
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        overall_confidence = Decimal("0")

    # ====================================================
    # Get bills
    # ====================================================

    bills = parsed_data.get(
        "bills",
        []
    )

    if not isinstance(
        bills,
        list,
    ) or not bills:
        raise Exception(
            "Receipt image is not readable. "
            "Please upload a clearer receipt."
        )

    # ====================================================
    # Ensure every bill has line items
    # ====================================================

    for bill in bills:

        if not isinstance(
            bill,
            dict,
        ):
            continue

        print(
            "\n================ BILL FROM GEMINI ================"
        )

        print(
            json.dumps(
                bill,
                indent=4,
                default=str,
            )
        )

        print(
            "=================================================="
        )

        line_items = bill.get(
            "line_items",
            []
        )

        print(
            "Original line_items:",
            line_items,
        )

        # ------------------------------------------------
        # Fallback line item
        # ------------------------------------------------

        if not isinstance(
            line_items,
            list,
        ) or not line_items:

            print(
                "No line items found. "
                "Creating fallback line item..."
            )

            amount = bill.get(
                "grand_total"
            )

            if amount is None:
                amount = bill.get(
                    "amount"
                )

            category = bill.get(
                "type",
                "miscellaneous",
            )

            vendor = bill.get(
                "vendor",
                "",
            )

            line_name = (
                str(category)
                .replace("_", " ")
                .title()
            )

            if vendor:
                line_name = (
                    f"{vendor} - {line_name}"
                )

            bill["line_items"] = [
                {
                    "name": line_name,
                    "category": category,
                    "subcategory": (
                        str(category)
                        .replace("_", " ")
                        .title()
                    ),
                    "quantity": 1,
                    "unit_price": amount,
                    "total_price": amount,
                    "is_reimbursable": True,
                    "reason": "",
                }
            ]

            print(
                "Fallback created:"
            )

            print(
                json.dumps(
                    bill["line_items"],
                    indent=4,
                    default=str,
                )
            )

        else:

            print(
                f"Gemini extracted "
                f"{len(line_items)} line item(s):"
            )

            print(
                json.dumps(
                    line_items,
                    indent=4,
                    default=str,
                )
            )

        # ------------------------------------------------
        # Normalize line items
        # ------------------------------------------------

        normalize_bill_line_items(
            bill
        )

        print(
            "Normalized line_items:"
        )

        print(
            json.dumps(
                bill.get(
                    "line_items",
                    []
                ),
                indent=4,
                default=str,
            )
        )

    # ====================================================
    # Initialize variables
    # ====================================================

    normalized_bills = []

    total_amount = Decimal(
        "0.00"
    )

    created_items = []

    db_line_items = []

    final_line_items = []

    conversion_result = None

    allowed_categories = {
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
        "miscellaneous",
    }

    # ====================================================
    # Normalize bills
    # ====================================================

    for bill_index, bill in enumerate(
        bills
    ):

        if not isinstance(
            bill,
            dict,
        ):
            continue

        # ------------------------------------------------
        # Amount
        # ------------------------------------------------

        raw_amount = (
            bill.get("amount")
            if bill.get("amount") is not None
            else bill.get("grand_total")
        )

        try:
            amount = Decimal(
                str(
                    raw_amount
                    if raw_amount is not None
                    else "0.00"
                )
                .replace(",", "")
                .strip()
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):
            amount = Decimal(
                "0.00"
            )

        if amount < Decimal(
            "0.00"
        ):
            amount = Decimal(
                "0.00"
            )

        # ------------------------------------------------
        # Category
        # ------------------------------------------------

        category = str(
            bill.get("type")
            or "miscellaneous"
        ).strip().lower()

        if category not in allowed_categories:
            category = "miscellaneous"

        # ------------------------------------------------
        # Currency
        # ------------------------------------------------

        currency = str(
            bill.get("currency")
            or ""
        ).strip().upper()

        if len(currency) != 3:
            currency = ""

        # ------------------------------------------------
        # Bill date
        # ------------------------------------------------

        raw_bill_date = bill.get(
            "bill_date"
        )

        bill_date = None

        if raw_bill_date:

            try:
                bill_date = datetime.strptime(
                    str(
                        raw_bill_date
                    ).strip(),
                    "%Y-%m-%d",
                ).date()

            except (
                TypeError,
                ValueError,
            ):
                bill_date = None

        # ------------------------------------------------
        # Vendor
        # ------------------------------------------------

        vendor = str(
            bill.get("vendor")
            or ""
        ).strip()[:255]

        # ------------------------------------------------
        # Additional information
        # ------------------------------------------------

        additional_info = str(
            bill.get("additional_info")
            or ""
        ).strip()

        if not additional_info:

            additional_info = str(
                bill.get(
                    "translated_original_text"
                )
                or bill.get(
                    "extraction_notes"
                )
                or ""
            ).strip()

        # ------------------------------------------------
        # Normalized bill
        # ------------------------------------------------

        normalized_bill = {
            "merchant_type": bill.get(
                "merchant_type",
                "",
            ),

            "merchant_country": bill.get(
                "merchant_country",
                "",
            ),

            "merchant_city": bill.get(
                "merchant_city",
                "",
            ),

            **bill,

            "type": category,

            "amount": str(
                amount
            ),

            "currency": currency,

            "bill_date": (
                bill_date.isoformat()
                if bill_date
                else None
            ),

            "vendor": vendor,

            "additional_info": additional_info,
        }

        normalized_bills.append(
            normalized_bill
        )

        total_amount += amount

    # ====================================================
    # Validate normalized bills
    # ====================================================

    if not normalized_bills:
        raise Exception(
            "No valid bill information was extracted."
        )

    if total_amount <= Decimal(
        "0.00"
    ):
        raise Exception(
            "The final payable amount could not be read. "
            "Please upload a clearer receipt."
        )

    # ====================================================
    # DATABASE TRANSACTION
    # ====================================================

    with transaction.atomic():

        # ------------------------------------------------
        # Remove old line items
        # ------------------------------------------------

        ExpenseLineItem.objects.filter(
            receipt=receipt
        ).delete()

        ExpenseAttachment.objects.filter(
            receipt=receipt
        ).delete()

        # ------------------------------------------------
        # First bill
        # ------------------------------------------------

        first_bill = normalized_bills[0]

        # ------------------------------------------------
        # Document reference
        # ------------------------------------------------

        document_reference = first_bill.get(
            "document_reference",
            {},
        )

        if not isinstance(
            document_reference,
            dict,
        ):
            document_reference = {}

        receipt.reference_number = (
            document_reference.get(
                "reference_number",
                "",
            )
        )

        receipt.reference_type = (
            document_reference.get(
                "reference_type",
                "",
            )
        )

        receipt.linked_reference_number = (
            document_reference.get(
                "linked_reference_number",
                "",
            )
        )

        # ------------------------------------------------
        # Fingerprint
        # ------------------------------------------------

        fingerprint = first_bill.get(
            "receipt_fingerprint",
            {},
        )

        if not isinstance(
            fingerprint,
            dict,
        ):
            fingerprint = {}

        receipt.receipt_fingerprint = (
            fingerprint
        )

        fingerprint_string = "|".join(
            [
                str(
                    fingerprint.get(
                        "merchant",
                        "",
                    )
                ).strip().upper(),

                str(
                    fingerprint.get(
                        "document_number",
                        "",
                    )
                ).strip().upper(),

                str(
                    fingerprint.get(
                        "bill_date",
                        "",
                    )
                ).strip(),

                str(
                    fingerprint.get(
                        "amount",
                        "",
                    )
                ).strip(),

                str(
                    fingerprint.get(
                        "currency",
                        "",
                    )
                ).strip().upper(),
            ]
        )

        receipt.fingerprint_hash = (
            hashlib.sha256(
                fingerprint_string.encode(
                    "utf-8"
                )
            ).hexdigest()
        )

        # ------------------------------------------------
        # Receipt basic information
        # ------------------------------------------------

        extracted_currency = (
            first_bill.get(
                "currency"
            )
            or "INR"
        ).upper()

        try:
            finance_settings = (
                receipt.company.finance_settings
            )
        except Exception:
            finance_settings = None

        company_currency = (
            finance_settings.base_currency.code
            if (
                finance_settings
                and finance_settings.base_currency
            )
            else extracted_currency
        ).upper()

        receipt.vendor_name = (
            first_bill.get(
                "vendor",
                "",
            )
        )

        receipt.original_amount = (
            total_amount
        )

        receipt.original_currency = (
            extracted_currency
        )

        receipt.currency = (
            extracted_currency
        )

        # ------------------------------------------------
        # Invoice date
        # ------------------------------------------------

        first_bill_date = first_bill.get(
            "bill_date"
        )

        if first_bill_date:

            try:
                receipt.invoice_date = (
                    datetime.strptime(
                        first_bill_date,
                        "%Y-%m-%d",
                    ).date()
                )

            except (
                TypeError,
                ValueError,
            ):
                receipt.invoice_date = (
                    timezone.now().date()
                )

        elif not receipt.invoice_date:

            receipt.invoice_date = (
                timezone.now().date()
            )

        # ------------------------------------------------
        # Currency conversion
        # ------------------------------------------------

        auto_conversion_enabled = bool(
            finance_settings
            and finance_settings.auto_currency_conversion
        )

        if auto_conversion_enabled:

            conversion_result = convert_currency(
                amount=receipt.original_amount,
                from_currency=(
                    receipt.original_currency
                ),
                to_currency=company_currency,
                company=receipt.company,
            )

            if conversion_result.get(
                "success"
            ):

                receipt.company_amount = (
                    conversion_result[
                        "company_amount"
                    ]
                )

                receipt.company_currency = (
                    conversion_result[
                        "company_currency"
                    ]
                )

                receipt.exchange_rate = (
                    conversion_result[
                        "exchange_rate"
                    ]
                )

                receipt.exchange_rate_date = (
                    conversion_result[
                        "exchange_rate_date"
                    ]
                )

                receipt.exchange_rate_provider = (
                    conversion_result[
                        "exchange_rate_provider"
                    ]
                )

                if finance_settings:

                    finance_settings.last_exchange_sync = (
                        timezone.now()
                    )

                    finance_settings.save(
                        update_fields=[
                            "last_exchange_sync"
                        ]
                    )

            else:

                receipt.company_amount = (
                    receipt.original_amount
                )

                receipt.company_currency = (
                    receipt.original_currency
                )

                receipt.exchange_rate = None
                receipt.exchange_rate_date = None
                receipt.exchange_rate_provider = None

        else:

            receipt.company_amount = (
                receipt.original_amount
            )

            receipt.company_currency = (
                receipt.original_currency
            )

            receipt.exchange_rate = Decimal(
                "1"
            )

            receipt.exchange_rate_date = (
                timezone.now()
            )

            receipt.exchange_rate_provider = (
                "Conversion Disabled"
            )

        receipt.total_amount = (
            receipt.company_amount
        )

        # ------------------------------------------------
        # AI information
        # ------------------------------------------------

        receipt.status = (
            ExpenseReceipt.STATUS_AI_PROCESSED
        )

        receipt.ai_status = (
            ExpenseReceipt.AI_COMPLETED
        )

        receipt.ai_error_message = None

        receipt.ai_extracted_data = (
            parsed_data
        )

        document_validation = (
            parsed_data.get(
                "document_validation",
                {},
            )
        )

        if not isinstance(
            document_validation,
            dict,
        ):
            document_validation = {}

        receipt.document_validation = (
            document_validation
        )

        ai_recommendation = (
            parsed_data.get(
                "ai_recommendation",
                {},
            )
        )

        if not isinstance(
            ai_recommendation,
            dict,
        ):
            ai_recommendation = {}

        receipt.ai_decision = (
            ai_recommendation.get(
                "decision",
                "",
            )
        )

        receipt.ai_decision_reason = (
            ai_recommendation.get(
                "reason",
                "",
            )
        )

        receipt.ai_decision_confidence = (
            ai_recommendation.get(
                "confidence",
                0,
            )
        )

        receipt.original_language = (
            parsed_data.get(
                "document_language"
            )
        )

        receipt.original_language_code = (
            parsed_data.get(
                "document_language_code"
            )
        )

        receipt.output_language = (
            output_language_name
        )

        receipt.output_language_code = (
            output_language_code
        )

        receipt.ai_confidence = (
            overall_confidence
        )

        receipt.save()

        # ------------------------------------------------
        # Audit log
        # ------------------------------------------------

        create_audit_log(
            receipt=receipt,
            action=(
                ExpenseAuditTrail.ACTION_AI_COMPLETED
            ),
            remarks=(
                "AI successfully extracted "
                "receipt data."
            ),
            metadata={
                "vendor": receipt.vendor_name,
                "amount": str(
                    receipt.original_amount
                ),
                "currency": (
                    receipt.original_currency
                ),
            },
        )

        # ------------------------------------------------
        # Link invoice/ticket
        # ------------------------------------------------

        link_receipt(
            receipt
        )

        # =================================================
        # CREATE EXPENSE LINE ITEMS
        # =================================================

        for bill_index, bill in enumerate(
            normalized_bills
        ):

            try:
                amount = Decimal(
                    str(
                        bill.get(
                            "amount",
                            "0.00",
                        )
                    )
                )
            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                amount = Decimal(
                    "0.00"
                )

            approved_bill_total = (
                Decimal("0.00")
            )

            # ------------------------------------------------
            # Bill date
            # ------------------------------------------------

            bill_date = None

            if bill.get(
                "bill_date"
            ):

                try:
                    bill_date = (
                        datetime.strptime(
                            bill["bill_date"],
                            "%Y-%m-%d",
                        ).date()
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    bill_date = None

            # ------------------------------------------------
            # Normalize line items
            # ------------------------------------------------

            line_items = (
                normalize_bill_line_items(
                    bill
                )
            )

            print(
                "\n=================================================="
            )

            print(
                f"BILL {bill_index + 1} "
                "LINE ITEMS BEFORE DB CREATION"
            )

            print(
                json.dumps(
                    line_items,
                    indent=4,
                    default=str,
                )
            )

            print(
                "==================================================\n"
            )

            # ------------------------------------------------
            # Create extracted line items
            # ------------------------------------------------

            if line_items:

                for item_index, item in enumerate(
                    line_items
                ):

                    item_name = str(
                        item.get(
                            "name",
                            "",
                        )
                    ).strip()

                    if not item_name:

                        item_name = (
                            bill.get(
                                "vendor"
                            )
                            or bill.get(
                                "type"
                            )
                            or "Expense"
                        )

                    item_subcategory = str(
                        item.get(
                            "subcategory",
                            "",
                        )
                        or ""
                    ).strip()

                    try:

                        item_amount = Decimal(
                            str(
                                item.get(
                                    "total_price"
                                )
                                or item.get(
                                    "amount"
                                )
                                or "0"
                            )
                        )

                    except (
                        InvalidOperation,
                        TypeError,
                        ValueError,
                    ):

                        item_amount = (
                            Decimal("0.00")
                        )

                    if item_amount <= Decimal(
                        "0.00"
                    ):

                        print(
                            "Skipping zero amount "
                            "line item:",
                            item_name,
                        )

                        continue

                    is_reimbursable = bool(
                        item.get(
                            "is_reimbursable",
                            True,
                        )
                    )

                    item_reason = str(
                        item.get(
                            "reason",
                            "",
                        )
                        or ""
                    ).strip()

                    item_category = str(
                        item.get(
                            "category",
                            bill.get(
                                "type",
                                "miscellaneous",
                            ),
                        )
                        or "miscellaneous"
                    ).strip().lower()

                    item_vendor = str(
                        bill.get(
                            "vendor",
                            "",
                        )
                        or ""
                    ).strip()[:255]

                    print(
                        "\n========== CREATING DB LINE ITEM =========="
                    )

                    print(
                        "Receipt ID:",
                        receipt.id,
                    )

                    print(
                        "Item:",
                        item_name,
                    )

                    print(
                        "Category:",
                        item_category,
                    )

                    print(
                        "Subcategory:",
                        item_subcategory,
                    )

                    print(
                        "Amount:",
                        item_amount,
                    )

                    print(
                        "Reimbursable:",
                        is_reimbursable,
                    )

                    # -----------------------------------------
                    # ACTUAL DATABASE CREATE
                    # -----------------------------------------

                    expense_item = (
                        ExpenseLineItem.objects.create(
                            receipt=receipt,
                            description=item_name,
                            category=item_category,
                            subcategory=(
                                item_subcategory
                            ),
                            vendor=item_vendor,
                            amount=item_amount,
                            bill_date=bill_date,
                            is_violating=(
                                not is_reimbursable
                            ),
                            violation_reason=(
                                item_reason
                                if not is_reimbursable
                                else ""
                            ),
                        )
                    )

                    print(
                        "========== DB LINE ITEM CREATED =========="
                    )

                    print(
                        "ID:",
                        expense_item.id,
                    )

                    print(
                        "Receipt:",
                        expense_item.receipt_id,
                    )

                    print(
                        "Description:",
                        expense_item.description,
                    )

                    print(
                        "Category:",
                        expense_item.category,
                    )

                    print(
                        "Subcategory:",
                        expense_item.subcategory,
                    )

                    print(
                        "Amount:",
                        expense_item.amount,
                    )

                    print(
                        "=========================================="
                    )

                    created_items.append(
                        expense_item.id
                    )

                    approved_bill_total += (
                        item_amount
                    )

                    ExpenseAttachment.objects.create(
                        line_item=expense_item,
                        receipt=receipt,
                        file=receipt.receipt_file,
                        attachment_type="receipt",
                    )

            # ------------------------------------------------
            # Fallback line item
            # ------------------------------------------------

            elif amount > Decimal(
                "0.00"
            ):

                fallback_name = (
                    bill.get(
                        "vendor"
                    )
                    or bill.get(
                        "type"
                    )
                    or "Receipt total"
                )

                expense_item = (
                    ExpenseLineItem.objects.create(
                        receipt=receipt,
                        description=str(
                            fallback_name
                        ),
                        category=bill.get(
                            "type",
                            "miscellaneous",
                        ),
                        subcategory="",
                        vendor=str(
                            bill.get(
                                "vendor",
                                "",
                            )
                            or ""
                        )[:255],
                        amount=amount,
                        bill_date=bill_date,
                        is_violating=False,
                        violation_reason="",
                    )
                )

                print(
                    "========== FALLBACK DB LINE ITEM CREATED =========="
                )

                print(
                    "ID:",
                    expense_item.id,
                )

                print(
                    "Receipt:",
                    expense_item.receipt_id,
                )

                print(
                    "Description:",
                    expense_item.description,
                )

                print(
                    "Amount:",
                    expense_item.amount,
                )

                print(
                    "===================================================="
                )

                created_items.append(
                    expense_item.id
                )

                approved_bill_total = (
                    amount
                )

                ExpenseAttachment.objects.create(
                    line_item=expense_item,
                    receipt=receipt,
                    file=receipt.receipt_file,
                    attachment_type="receipt",
                )

            bill["approved_amount"] = str(
                approved_bill_total
            )

        # =================================================
        # VERIFY LINE ITEMS INSIDE TRANSACTION
        # =================================================

        db_line_items = list(
            ExpenseLineItem.objects.filter(
                receipt=receipt
            ).values(
                "id",
                "description",
                "category",
                "subcategory",
                "vendor",
                "amount",
                "bill_date",
                "is_violating",
                "violation_reason",
            )
        )

        print(
            "\n========== LINE ITEMS BEFORE COMMIT =========="
        )

        print(
            json.dumps(
                db_line_items,
                indent=4,
                default=str,
            )
        )

        print(
            "LINE ITEM COUNT:",
            len(db_line_items),
        )

        print(
            "==============================================\n"
        )

        if not db_line_items:

            raise Exception(
                "Gemini extracted receipt data, "
                "but no ExpenseLineItem records were created."
            )

        # ------------------------------------------------
        # Recalculate report
        # ------------------------------------------------

        if receipt.report:

            recalculate_report_total(
                receipt.report
            )

    # ====================================================
    # TRANSACTION HAS COMMITTED HERE
    # ====================================================

    print(
        "\n========== TRANSACTION COMMITTED =========="
    )

    print(
        "Receipt ID:",
        receipt.id,
    )

    print(
        "============================================\n"
    )

    # ====================================================
    # POLICY VALIDATION
    # ====================================================

    try:

        check_policy_violations(
            receipt
        )

    except Exception as policy_error:

        print(
            "\n========== POLICY VALIDATION ERROR =========="
        )

        print(
            str(policy_error)
        )

        print(
            "Line items were already committed."
        )

        print(
            "=============================================\n"
        )

        receipt.refresh_from_db()

        receipt.ai_error_message = (
            "Policy validation warning: "
            f"{str(policy_error)}"
        )

        receipt.save(
            update_fields=[
                "ai_error_message",
                "updated_at",
            ]
        )

    # ====================================================
    # Refresh receipt
    # ====================================================

    receipt.refresh_from_db()

    # ====================================================
    # FINAL DATABASE VERIFICATION
    # ====================================================

    final_line_items = list(
        ExpenseLineItem.objects.filter(
            receipt=receipt
        ).values(
            "id",
            "description",
            "category",
            "subcategory",
            "vendor",
            "amount",
            "bill_date",
            "is_violating",
            "violation_reason",
        )
    )

    print(
        "\n=================================================="
    )

    print(
        "FINAL COMMITTED LINE ITEMS"
    )

    print(
        json.dumps(
            final_line_items,
            indent=4,
            default=str,
        )
    )

    print(
        "FINAL COUNT:",
        len(final_line_items),
    )

    print(
        "==================================================\n"
    )

    if not final_line_items:

        raise Exception(
            "Receipt processing completed, "
            "but no ExpenseLineItem records exist "
            "after transaction commit."
        )

    # ====================================================
    # Success response
    # ====================================================

    return {
        "success": True,

        "receipt_id": str(
            receipt.id
        ),

        "ai_status": (
            ExpenseReceipt.AI_COMPLETED
        ),

        "document_language": (
            parsed_data.get(
                "document_language"
            )
        ),

        "document_language_code": (
            parsed_data.get(
                "document_language_code"
            )
        ),

        "document_summary": (
            parsed_data.get(
                "document_summary"
            )
        ),

        "receipt_quality": (
            parsed_data.get(
                "receipt_quality"
            )
        ),

        "fraud_analysis": (
            parsed_data.get(
                "fraud_analysis"
            )
        ),

        "document_metadata": (
            parsed_data.get(
                "document_metadata"
            )
        ),

        "output_language": {
            "code": output_language_code,
            "name": output_language_name,
            "preserve_original_text": (
                preserve_original_text
            ),
        },

        "bills": normalized_bills,

        "line_items_created": [
            str(
                item["id"]
            )
            for item in final_line_items
        ],

        "line_items": final_line_items,

        "original_amount": str(
            receipt.original_amount
        ),

        "original_currency": (
            receipt.original_currency
        ),

        "company_amount": str(
            receipt.company_amount
        ),

        "company_currency": (
            receipt.company_currency
        ),

        "exchange_rate": (
            str(
                receipt.exchange_rate
            )
            if receipt.exchange_rate is not None
            else None
        ),

        "exchange_rate_date": (
            receipt.exchange_rate_date.isoformat()
            if receipt.exchange_rate_date
            else None
        ),

        "exchange_rate_provider": (
            receipt.exchange_rate_provider
        ),

        "currency_conversion": (
            conversion_result
        ),

        "has_any_violation": (
            receipt.has_any_violation
        ),

        "violation_reason": (
            receipt.policy_violation_reason
        ),
    }


# NOTE: Global exception handling should be implemented at the caller level.
# The previous top-level 'except' block was removed because it caused
# a syntax error when left unmatched. Exceptions should be caught inside
# functions or by the task/worker that invokes this processing routine.