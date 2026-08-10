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


def normalize_bill_line_items(bill: dict) -> list[dict]:
    """
    Keep receipt line items in receipt sequence:
    1) charges / products
    2) taxes / fees of tax type
    Never persist grand-total rows or zero-amount placeholders.
    Also promote bill.tip into a Tip line item when present.
    """
    if not isinstance(bill, dict):
        return []

    raw_items = []
    for item in bill.get("line_items") or []:
        if isinstance(item, dict):
            raw_items.append(dict(item))

    for tax in bill.get("taxes") or []:
        if not isinstance(tax, dict):
            continue
        tax_amount = tax.get("amount", tax.get("total_price"))
        raw_items.append(
            {
                "name": tax.get("name") or "Tax",
                "category": bill.get("type") or "miscellaneous",
                "subcategory": tax.get("name") or "Tax",
                "quantity": 1,
                "unit_price": tax_amount,
                "total_price": tax_amount,
                "is_reimbursable": True,
                "reason": "",
            }
        )

    # Tip often lives on bill.tip (handwritten gratuity) instead of line_items.
    tip_amount = _line_item_amount({"total_price": bill.get("tip")})
    if tip_amount > Decimal("0.00"):
        already_has_tip = any(
            "tip" in _line_item_label(item) or "gratuity" in _line_item_label(item)
            for item in raw_items
        )
        if not already_has_tip:
            raw_items.append(
                {
                    "name": "Tip / Gratuity",
                    "category": bill.get("type") or "miscellaneous",
                    "subcategory": "Tip",
                    "quantity": 1,
                    "unit_price": float(tip_amount),
                    "total_price": float(tip_amount),
                    "is_reimbursable": True,
                    "reason": "",
                }
            )

    charges: list[dict] = []
    taxes: list[dict] = []

    for item in raw_items:
        amount = _line_item_amount(item)
        if amount == Decimal("0.00"):
            continue
        if _is_total_line_item(item):
            continue
        item["total_price"] = float(amount)
        if _is_tax_line_item(item):
            taxes.append(item)
        else:
            charges.append(item)

    ordered = charges + taxes
    bill["line_items"] = ordered
    return ordered


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

    prompt = f"""
You are ZepEx Receipt Intelligence, an expert multilingual expense
receipt, invoice, travel-document and financial-document analyst.

The uploaded document may be written in any language.

You must:

1. Detect and understand the original language.
2. Extract financial information accurately.
3. Return only one valid JSON object.
4. Return all human-readable explanations in:
   {output_language_name} ({output_language_code})
5. Preserve original-language text when requested.
6. Never invent unreadable or missing information.

============================================================
LANGUAGE RULES
============================================================

Configured company output language:

- Name: {output_language_name}
- Code: {output_language_code}
- Preserve original text: {str(preserve_original_text).lower()}

The following fields must be written in the configured company language:

- additional_info
- line_items.name
- taxes.name
- extraction_notes
- document_summary

Do not translate or modify:

- vendor or legal merchant name
- invoice number
- tax registration number
- PNR
- flight number
- train number
- seat number
- numeric amounts
- currency codes
- dates
- payment reference numbers

The following backend fields must remain normalized:

- type: supported English category key
- currency: three-letter ISO currency code
- amount: number
- bill_date: YYYY-MM-DD
- confidence values: number between 0 and 1

============================================================
SUPPORTED CATEGORY KEYS
============================================================

Return type as exactly one of:

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

meal, restaurant, lunch, dinner, breakfast -> food
lodging, accommodation, room stay -> hotel
airfare, boarding pass, airline ticket -> flight_ticket
railway ticket, rail fare -> train_ticket
petrol, diesel, gasoline -> fuel
mobile, internet, broadband -> telecom
medicine, pharmacy, consultation -> medical
stationery, printer paper, office items -> office_supplies

============================================================
FOOD RECEIPT DESCRIPTION RULES
============================================================

For a food or restaurant receipt, additional_info must contain numbered
points for every readable food item and its price.

Use this structure in {output_language_name}:

1. Item name — quantity × unit price — item total
2. Item name — quantity × unit price — item total
3. Item name — item total
4. Subtotal — amount
5. Tax — amount
6. Tip — amount
7. Discount — amount
8. Total — amount

Rules:

- Include every clearly readable food item.
- Include quantity when available.
- Include unit price when available.
- Include item total when available.
- Include subtotal, taxes, service charge, tip and discount separately.
- End with the final payable total.
- Do not invent an item or price.
- If an item price is unreadable, use an empty string for that price.
- Keep the list concise but complete.

Example formatting:

1. Veg Burger — 2 × INR 120.00 — INR 240.00
2. French Fries — INR 90.00
3. Soft Drink — INR 60.00
4. Subtotal — INR 390.00
5. GST — INR 19.50
6. Total — INR 409.50

Translate labels such as Subtotal, Tax, Tip, Discount and Total into
{output_language_name}, but keep currency codes and numbers unchanged.

============================================================
LINE ITEM CLASSIFICATION
============================================================

Every extracted line item must include:

- name
- category
- subcategory
- quantity
- unit_price
- total_price

Rules:

Category must represent the reimbursement category.

Examples:

Restaurant meal
→ category = food

Hotel room
→ category = hotel

Diesel
→ category = fuel

Parking Fee
→ category = parking

Courier Charge
→ category = courier

Medicine
→ category = medical

Internet Recharge
→ category = telecom

Printer Paper
→ category = office_supplies

Flight Ticket
→ category = flight_ticket

Train Ticket
→ category = train_ticket

Car Rental
→ category = car_rental

Training Fee
→ category = training

Remote Office Equipment
→ category = wfh

Moving Expense
→ category = relocation

Anything else
→ miscellaneous

Subcategory should be as specific as possible.

Examples:

Veg Meal
Non Veg Meal
Dessert
Coffee
Tea
Soft Drink
Breakfast
Lunch
Dinner
Stationery
Fuel
Medicine
Parking Fee
Room Charge
Laundry
Mini Bar
Internet
Taxi
Printer Ink
Laptop Accessories
Office Furniture

Never leave subcategory empty when it can reasonably be determined.

Do not invent items that do not exist on the receipt.

============================================================
OTHER RECEIPT DESCRIPTION RULES
============================================================

For hotel, flight, train, fuel, medical, office supplies, telecom,
parking, courier, training, car rental or other receipts:

- Return 5 to 6 concise numbered points in additional_info.
- Include the most useful small details visible in the document.
- Do not force six points when fewer details are actually readable.
- Never invent missing information.
- End with the final payable total.

Examples of useful details:

HOTEL:
- room type
- guest name
- check-in
- check-out
- number of nights
- room charge
- taxes
- total

FLIGHT:
- airline
- flight number
- route
- passenger
- travel date
- departure time
- arrival time
- class
- seat
- PNR
- total fare

TRAIN:
- train number and name
- route
- passenger
- travel date
- class
- coach
- seat
- PNR
- total fare

FUEL:
- fuel type
- quantity
- price per litre
- station
- vehicle number
- payment method
- total

MEDICAL:
- medicine or service names
- quantities
- consultation
- pharmacy or hospital
- taxes
- total

OFFICE SUPPLIES:
- each purchased item
- quantity
- unit price
- item total
- taxes
- final total

PARKING:
- location
- entry time
- exit time
- duration
- vehicle number
- total fee

============================================================
AMOUNT RULES
============================================================

- amount must be the final payable or grand total for that bill.
- Do not use subtotal when a grand total is available.
- Do not use tax amount as the bill amount.
- Do not use balance, cash tendered or change returned as the amount.
- Preserve decimal values accurately.
- If the final total is unreadable, return null.

============================================================
CURRENCY RULES
============================================================

- Return a three-letter currency code such as INR, USD, EUR, GBP,
  AED, JPY, CAD, AUD or SGD.
- Determine currency using code, currency name, symbol and country.
- A dollar symbol may be ambiguous; use document context.
- Do not perform currency conversion.
- If the currency cannot be determined, return an empty string.

============================================================
DATE RULES
============================================================

- bill_date must be YYYY-MM-DD.
- Prefer invoice date, transaction date or purchase date.
- For a flight or train ticket, use the document issue date as bill_date
  when available; keep the travel date inside additional_info.
- Return null when the date cannot be determined.

============================================================
VENDOR RULES
============================================================

- vendor must contain only the merchant, business, hotel, airline,
  railway, hospital, pharmacy or service-provider name.
- Do not include address, phone number, tax number or extra sentences.
- Preserve the vendor's official original name.
- Return an empty string if vendor is unreadable.

============================================================
ORIGINAL LANGUAGE RULES
============================================================

If preserve_original_text is true:

- original_text must preserve the most relevant readable receipt content
  in its original language.
- Do not translate original_text.
- source_language must contain the detected language name.
- source_language_code should use a language code such as en, hi, es,
  fr, ar, ja or zh.

If preserve_original_text is false:

- original_text may be null.

translated_original_text must contain a concise translation of the
important original receipt text in {output_language_name}.

============================================================
MULTIPLE RECEIPTS
============================================================

The uploaded PDF or image may contain more than one independent receipt.

- Create one object inside bills for each independent receipt.
- Do not split one restaurant receipt into separate bills for every food
  item.
- Food items belong inside line_items.
- Each bill amount must represent that receipt's final total.

============================================================
FRAUD ANALYSIS
============================================================

Analyse whether the receipt appears suspicious.

Check:

image editing

cropping

duplicate receipt

unusual formatting

missing total

manual handwriting over receipt

missing merchant

missing tax

Return:

fraud_analysis

Do not accuse.

Only estimate confidence.

Return:

suspicious

duplicate_probability

edited_probability

reasons


============================================================
RECEIPT QUALITY ANALYSIS
============================================================

Evaluate the uploaded receipt.

Return:

receipt_quality

score:
0.0 to 1.0

status:

EXCELLENT
GOOD
FAIR
POOR

issues:

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

Never invent issues.

Only report visible issues.

============================================================
DOCUMENT METADATA
============================================================

Detect

QR

Barcode

Signature

Stamp

Handwriting

Receipt type

Invoice

Restaurant

Hotel

Medical

Parking

etc.

Extract payment information.

Cash

Card

UPI

Google Pay

Apple Pay

Bank Transfer

Credit Card

Debit Card

If unavailable

return empty strings.




Return

GST

VAT

CGST

SGST

IGST

Sales Tax

Service Tax

etc.



Give reviewer notes.

Examples

Date inferred.

Vendor partially readable.

Tax unreadable.

Currency inferred.

Amount clearly visible.

============================================================
DOCUMENT LINKING RULES
============================================================

Many expense reports contain multiple documents that belong to the same journey.

Examples:

• Flight Ticket + Airline Invoice
• Railway Ticket + GST Invoice
• Hotel Booking + Hotel Invoice
• Taxi Booking + Taxi Receipt
• Fuel Receipt + Toll Receipt

Extract any reference numbers visible in the document.

Return

document_reference

Fields:

reference_type

Possible values:

ticket
invoice
hotel_invoice
hotel_booking
flight_ticket
train_ticket
taxi_receipt
fuel_receipt
parking_receipt
miscellaneous

reference_number

The unique number printed on THIS document.

Examples:

Ticket Number
Invoice Number
Booking ID
PNR
Receipt Number

linked_reference_number

If this document clearly references another document, return that number.

Otherwise return an empty string.

Never invent numbers.

If no reference exists return empty strings.

============================================================
FOOD SUBCATEGORY RULES
============================================================

If bill type = food, classify every food item into a subcategory.

Allowed subcategories include:

Vegetarian
Non Vegetarian
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
Seafood
Fruit
Unknown

Examples:

Paneer Butter Masala -> Vegetarian
Dal Tadka -> Vegetarian
Chicken Curry -> Non Vegetarian
Fish Fry -> Seafood
Beer -> Beer
Kingfisher Premium -> Beer
Red Wine -> Wine
Whiskey -> Whiskey
Vodka -> Vodka
Cappuccino -> Coffee
Latte -> Coffee
Cold Coffee -> Coffee
Tea -> Tea
Orange Juice -> Juice
Coca Cola -> Soft Drink
Pepsi -> Soft Drink
Chocolate Cake -> Dessert
Brownie -> Dessert
Croissant -> Bakery
Pizza -> Pizza
Burger -> Burger
French Fries -> Snacks

Return one subcategory for every line item.

Never leave it empty unless unreadable.

============================================================
ITEM CLASSIFICATION RULES
============================================================

Every extracted line item must be classified.

Return for every line item:

- category
- subcategory
- is_reimbursable
- reason

Category should describe the business expense type.

Examples:

Food
Travel
Fuel
Medical
Accommodation
Office Supplies
Entertainment
Telecom
Parking
Training
Courier
Miscellaneous

Subcategory should describe the actual purchased item.

Examples:

Paneer Butter Masala → Main Course
Butter Naan → Bread
Coffee → Coffee
Tea → Tea
Beer → Alcohol
Wine → Alcohol
Whiskey → Alcohol
Vodka → Alcohol
Burger → Fast Food
Pizza → Fast Food
Sandwich → Snacks
Ice Cream → Dessert
Taxi → Taxi
Flight Ticket → Flight
Hotel Room → Room Charge
Petrol → Petrol
Diesel → Diesel
Medicine → Medicine
Printer Paper → Stationery

Determine whether the individual item is reimbursable.

IMPORTANT:
- ALWAYS include the item in line_items even if it may not be reimbursable.
- Never omit food, drinks, alcohol, tips, service charges, or taxes from line_items.
- Company policy validation decides final reimbursement — extraction must mirror the receipt.

Return:

"is_reimbursable": true

or

"is_reimbursable": false

Default to true for restaurant / hotel / travel purchases, including alcohol,
unless the receipt clearly marks the item as personal.

Examples of false (soft hint only — still include the line item):

Cigarettes → false
Personal shopping → false
Gift item → false

Examples of true:

Business meal → true
Alcohol on a restaurant bill → true
Taxi → true
Flight → true
Hotel → true
Fuel → true
Service charge → true
Tax → true
Tip / gratuity → true

If the item is not reimbursable, populate "reason".

Examples:

"Personal expense"
"Gift item"

Otherwise return an empty string.

============================================================
DOCUMENT REFERENCE DETECTION
============================================================

Some documents belong to another receipt.

Detect and extract document references whenever possible.

Examples:

Flight Ticket
Reference Number = AI302

Boarding Pass
Linked Reference Number = AI302

Hotel Booking
Reference = BK23991

Hotel Invoice
Linked Reference = BK23991

Train Ticket
Reference = PNR123456

Travel Invoice
Linked Reference = PNR123456

Credit Note
Linked Reference = Original Invoice Number

Invoice
Reference = Invoice Number

Return:

"document_reference": {{
    "reference_type": "",
    "reference_number": "",
    "linked_reference_number": ""
}}

Never invent values.

Leave empty strings if no reference exists.

============================================================
ITEM CATEGORY RULES
============================================================

For every line item determine its own reimbursement category.

Return BOTH category and subcategory.

Examples

Paneer Butter Masala

category:
food

subcategory:
Main Course

----------------------------

Butter Naan

category:
food

subcategory:
Bread

----------------------------

Coffee

category:
beverages

subcategory:
Coffee

----------------------------

Green Tea

category:
beverages

subcategory:
Tea

----------------------------

Beer

category:
alcohol

subcategory:
Beer

----------------------------

Whiskey

category:
alcohol

subcategory:
Whiskey

----------------------------

Petrol

category:
fuel

subcategory:
Petrol

----------------------------

Diesel

category:
fuel

subcategory:
Diesel

----------------------------

Parking Ticket

category:
parking

subcategory:
Parking Fee

----------------------------

Laptop Bag

category:
office_supplies

subcategory:
Accessories

----------------------------

Medicine

category:
medical

subcategory:
Prescription Medicine

Rules

- Every line item MUST have its own category.
- Categories should describe the reimbursement policy category.
- Do not inherit the bill category.
- Do not leave category empty.


============================================================
LINE ITEM EXTRACTION AND NORMALIZATION
============================================================

Every visible monetary component printed on the receipt must be returned
as an individual line item.

Do NOT merge taxes, service charges, fees or discounts into another item.

Always extract separately whenever visible:

- Product
- Food Item
- Drink
- Parking Fee
- Toll
- Fuel
- Room Charge
- Laundry
- Mini Bar
- Internet
- Taxi Fare
- Service Charge
- Delivery Fee
- Convenience Fee
- GST
- CGST
- SGST
- IGST
- VAT
- Sales Tax
- Tip
- Discount

Each line item must contain:

- name
- category
- subcategory
- quantity
- unit_price
- total_price
- is_reimbursable
- reason

Subcategory should use the exact visible charge whenever possible.

Examples

Parking Fee
→ subcategory = Parking Fee

Sales Tax
→ subcategory = Sales Tax

GST
→ subcategory = GST

CGST
→ subcategory = CGST

SGST
→ subcategory = SGST

IGST
→ subcategory = IGST

VAT
→ subcategory = VAT

Service Charge
→ subcategory = Service Charge

Room Charge
→ subcategory = Room Charge

Laundry
→ subcategory = Laundry

Mini Bar
→ subcategory = Mini Bar

Beer
→ subcategory = Beer

Wine
→ subcategory = Wine

Coffee
→ subcategory = Coffee

Tea
→ subcategory = Tea

Burger
→ subcategory = Burger

Pizza
→ subcategory = Pizza

French Fries
→ subcategory = Snacks

Never use generic names like:

- Tax
- Fee
- Other
- Item
- Miscellaneous

when a more specific name is visible on the receipt.

Examples

Parking Receipt

Parking Fee ............ 42.00
Sales Tax ............... 2.73

Return

Parking Fee
Sales Tax

Restaurant Receipt

Burger
French Fries
Service Charge
GST

Return four separate line items.

Hotel Receipt

Room Charge
Laundry
Mini Bar
VAT

Return each as a separate line item.

The sum of all line_items.total_price should approximately equal the bill grand total whenever possible.

CRITICAL ORDERING RULES
- Keep line_items in the same top-to-bottom order as the printed receipt.
- Extract every purchased product/drink first, then fees/service charges, then taxes, then tip if printed.
- Never omit menu items, drinks, or alcohol just because they might be non-reimbursable.
- Never include Grand Total / Amount Due / Total as a line_item.
- Put the payable total only in bill.amount and bill.grand_total.
- Prefer bill.amount / bill.grand_total that includes tip when a tip is present.
- Always put tip/gratuity in line_items (and also bill.tip) when handwritten or printed.
- Extract handwritten tip/gratuity as its own line item when present.
- Do not create extra bills for metadata such as entry time or payment method.
- Put that metadata only in additional_info.
- If the image contains multiple separate checks/receipts, return one bill object per check.

============================================================
AI RECOMMENDATION
============================================================

Based on the extracted receipt, determine whether the expense appears
suitable for reimbursement.

Consider:

- Receipt quality
- Fraud indicators
- Missing information
- Policy-sensitive items
- Duplicate likelihood
- Linked documents
- Merchant type
- Amount consistency
- OCR confidence

Return one of:

APPROVE
REVIEW
REJECT

Rules

APPROVE

- Receipt is clear
- Information is readable
- No obvious fraud
- Receipt looks genuine

REVIEW

- Missing fields
- Low OCR confidence
- Linked receipt missing
- Duplicate possibility
- Poor quality
- Cropped receipt
- Handwritten corrections
- Suspicious formatting

REJECT

- Fake receipt
- Edited receipt
- Required document missing
- Receipt unusable
- Fraud probability is high

Also provide a short explanation.

============================================================
REQUIRED SUPPORTING DOCUMENTS
============================================================

Determine whether the uploaded receipt requires one or more
supporting documents.

Examples

Flight
- Boarding Pass
- Airline Invoice

Hotel
- Hotel Invoice
- GST Invoice (if applicable)

Train
- Railway Ticket

Fuel
- Fuel Receipt

Taxi
- Trip Receipt

Medical
- Doctor Prescription (if applicable)

Conference
- Registration Invoice

Parking
- Parking Receipt

Restaurant
- Restaurant Receipt

Return

required_documents

uploaded_documents

missing_documents

is_complete

If a supporting document is missing,
add it to missing_documents.

Do not invent documents.

Only infer them when reasonably required.

============================================================
RECEIPT FINGERPRINT
============================================================

Create a fingerprint that uniquely identifies the receipt.

Extract:

merchant
document_number
bill_date
amount
currency

Rules:

- merchant must be normalized.
- Remove Pvt Ltd, Pvt. Ltd., Limited, Inc., LLC if they are not important.
- document_number should use invoice number, ticket number, booking number or receipt number.
- amount must be the final payable amount.
- bill_date must be YYYY-MM-DD.
- currency must be ISO code.

Never invent values.

This fingerprint will be used for duplicate detection.

============================================================
LINE ITEM EXTRACTION RULES
============================================================

Every monetary component printed on the receipt must become one line item.

Extract:

- Purchased products
- Food items
- Drinks
- Parking fee
- Fuel
- Room charge
- Service charge
- Delivery fee
- Convenience fee
- Sales tax
- GST
- VAT
- CGST
- SGST
- IGST
- Tips (if printed)
- Discounts (negative amount)

Do NOT merge these together.

Each must have:

name
category
subcategory
quantity
unit_price
total_price
is_reimbursable
reason

Examples

Parking receipt

Parking Fee ............ 42.00
Sales Tax .............. 2.73

Return

[
{{
"name":"Parking Fee",
"category":"parking",
"subcategory":"Parking Fee",
"total_price":42.00
}},
{{
"name":"Sales Tax",
"category":"parking",
"subcategory":"Sales Tax",
"total_price":2.73
}}
]

Restaurant

Burger........120
Fries.........90
GST...........19.5

Return

Burger
Fries
GST

Hotel

Room Charge
Mini Bar
Laundry
Service Charge
VAT

Return every charge separately.

Never merge tax into another item.

Never omit taxes or fees if they are individually printed.

The sum of all line_items.total_price should approximately equal the bill grand total.

CRITICAL ORDERING RULES
- Keep line_items in the same top-to-bottom order as the printed receipt.
- Extract every purchased product/drink first, then fees/service charges, then taxes, then tip if printed.
- Never omit menu items, drinks, or alcohol just because they might be non-reimbursable.
- Never include Grand Total / Amount Due / Total as a line_item.
- Put the payable total only in bill.amount and bill.grand_total.
- Prefer bill.amount / bill.grand_total that includes tip when a tip is present.
- Always put tip/gratuity in line_items (and also bill.tip) when handwritten or printed.
- Extract handwritten tip/gratuity as its own line item when present.
- Do not create extra bills for metadata such as entry time or payment method.
- Put that metadata only in additional_info.
- If the image contains multiple separate checks/receipts, return one bill object per check.
============================================================
OUTPUT JSON
============================================================

Return exactly this JSON structure:

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
      "vendor":"",
      "merchant_type":"",
      "merchant_country":"",
      "merchant_city":"",
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

      "line_items":[
{{
    "name":"",
    "category":"",
    "subcategory":"",
    "quantity":null,
    "unit_price":null,
    "total_price":null
}}
]

      "taxes":[
        {{
          "type": "GST",
          "percentage": 18,
          "amount": 120
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

Return JSON only.

Do not use Markdown.

Do not wrap the JSON in code fences.

Do not return any explanation outside the JSON.
"""

    try:
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
                    f"Gemini request failed with HTTP {response.status_code}.",
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

        # JSON mode normally returns plain JSON. The fallback handles
        # models that still wrap the result in a code block.
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

        try:
            parsed_data = json.loads(
                cleaned_text
            )
            print("\n================ GEMINI JSON ================\n")
            print(json.dumps(parsed_data, indent=4))
            print("\n=============================================\n")
            overall_confidence = Decimal(
                str(
                    parsed_data.get(
                        "ocr_confidence",
                        0,
                    )
                )
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
            print("\n================ GEMINI JSON ================\n")
            print(json.dumps(parsed_data, indent=4))
            print("\n=============================================\n")

        bills = parsed_data.get(
            "bills",
            []
        )

        if not isinstance(bills, list) or not bills:
            raise Exception(
                "Receipt image is not readable. "
                "Please upload a clearer receipt."
            )

        # -------------------------------------------------------
        # Ensure every bill has at least one line item
        # -------------------------------------------------------

        for bill in bills:
            if not isinstance(bill, dict):
                continue

            print("\n================ BILL FROM GEMINI ================")
            print(json.dumps(bill, indent=4))
            print("==================================================")

            line_items = bill.get("line_items")

            print("Original line_items:", line_items)

            if not line_items:
                print("No line items found. Creating fallback line item...")

                amount = bill.get("grand_total")

                if amount is None:
                    amount = bill.get("amount")

                category = bill.get("type", "miscellaneous")
                vendor = bill.get("vendor", "")

                line_name = str(category).replace("_", " ").title()

                if vendor:
                    line_name = f"{vendor} - {line_name}"

                bill["line_items"] = [
                    {
                        "name": line_name,
                        "category": category,
                        "subcategory": str(category).replace("_", " ").title(),
                        "quantity": 1,
                        "unit_price": amount,
                        "total_price": amount,
                        "is_reimbursable": True,
                        "reason": ""
                    }
                ]

                print("Fallback created:")
                print(json.dumps(bill["line_items"], indent=4))

            else:
                print(f"Gemini extracted {len(line_items)} line item(s):")
                print(json.dumps(line_items, indent=4))

            normalize_bill_line_items(bill)
            print("Normalized line_items:")
            print(json.dumps(bill["line_items"], indent=4))
        # ====================================================
        # Validate and save extracted data
        # ====================================================

        normalized_bills = []
        total_amount = Decimal("0.00")
        created_items = []

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

        for bill_index, bill in enumerate(bills):
            if not isinstance(bill, dict):
                continue

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
                amount = Decimal("0.00")

            if amount < Decimal("0.00"):
                amount = Decimal("0.00")

            category = str(
                bill.get("type")
                or "miscellaneous"
            ).strip().lower()

            if category not in allowed_categories:
                category = "miscellaneous"

            currency = str(
                bill.get("currency")
                or ""
            ).strip().upper()

            if len(currency) != 3:
                currency = ""

            raw_bill_date = bill.get(
                "bill_date"
            )

            bill_date = None

            if raw_bill_date:
                try:
                    bill_date = datetime.strptime(
                        str(raw_bill_date).strip(),
                        "%Y-%m-%d",
                    ).date()
                except (
                    TypeError,
                    ValueError,
                ):
                    bill_date = None

            vendor = str(
                bill.get("vendor")
                or ""
            ).strip()[:255]

            additional_info = str(
                bill.get("additional_info")
                or ""
            ).strip()

            if not additional_info:
                additional_info = str(
                    bill.get("translated_original_text")
                    or bill.get("extraction_notes")
                    or ""
                ).strip()

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
                "amount": str(amount),
                "currency": currency,
                "bill_date": (
                    bill_date.isoformat()
                    if bill_date
                    else None
                ),
                "vendor": vendor,
                "additional_info": additional_info,
            }

            normalized_bills.append(normalized_bill)

# Add the extracted bill amount
            total_amount += amount

        if not normalized_bills:
            raise Exception(
                "No valid bill information was extracted."
            )

        if total_amount <= Decimal("0.00"):
            raise Exception(
                "The final payable amount could not be read. "
                "Please upload a clearer receipt."
            )

        # ============================================================
        # All database changes happen atomically
        # ============================================================

        with transaction.atomic():

            # Remove old line items if AI is re-run
            ExpenseLineItem.objects.filter(
                receipt=receipt
            ).delete()

            first_bill = normalized_bills[0]

            # --------------------------------------------------------
            # Save document reference
            # --------------------------------------------------------

            document_reference = first_bill.get(
                "document_reference",
                {},
            )

            receipt.reference_number = document_reference.get(
                "reference_number",
                "",
            )

            receipt.reference_type = document_reference.get(
                "reference_type",
                "",
            )

            receipt.linked_reference_number = document_reference.get(
                "linked_reference_number",
                "",
            )
            fingerprint = first_bill.get(
                "receipt_fingerprint",
                {},
            )

            receipt.receipt_fingerprint = fingerprint

            fingerprint_string = "|".join([
                str(fingerprint.get("merchant", "")).strip().upper(),
                str(fingerprint.get("document_number", "")).strip().upper(),
                str(fingerprint.get("bill_date", "")).strip(),
                str(fingerprint.get("amount", "")).strip(),
                str(fingerprint.get("currency", "")).strip().upper(),
            ])

            receipt.fingerprint_hash = hashlib.sha256(
                fingerprint_string.encode("utf-8")
            ).hexdigest()  

            # --------------------------------------------------------
            # Receipt basic information
            # --------------------------------------------------------

            extracted_currency = (
                first_bill.get("currency")
                or "INR"
            ).upper()

            try:
                finance_settings = receipt.company.finance_settings
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

            receipt.vendor_name = first_bill.get(
                "vendor",
                "",
            )

            receipt.original_amount = total_amount
            receipt.original_currency = extracted_currency
            receipt.currency = extracted_currency

            first_bill_date = first_bill.get("bill_date")

            if first_bill_date:
                try:
                    receipt.invoice_date = datetime.strptime(
                        first_bill_date,
                        "%Y-%m-%d",
                    ).date()
                except (TypeError, ValueError):
                    receipt.invoice_date = timezone.now().date()
            elif not receipt.invoice_date:
                receipt.invoice_date = timezone.now().date()

            # --------------------------------------------------------
            # Currency Conversion
            # --------------------------------------------------------

            conversion_result = None

            auto_conversion_enabled = bool(
                finance_settings
                and finance_settings.auto_currency_conversion
            )

            if auto_conversion_enabled:

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
                    receipt.exchange_rate_provider = conversion_result["exchange_rate_provider"]

                    finance_settings.last_exchange_sync = timezone.now()

                    finance_settings.save(
                        update_fields=["last_exchange_sync"]
                    )

                else:

                    receipt.company_amount = receipt.original_amount
                    receipt.company_currency = receipt.original_currency
                    receipt.exchange_rate = None
                    receipt.exchange_rate_date = None
                    receipt.exchange_rate_provider = None

            else:

                receipt.company_amount = receipt.original_amount
                receipt.company_currency = receipt.original_currency
                receipt.exchange_rate = Decimal("1")
                receipt.exchange_rate_date = timezone.now()
                receipt.exchange_rate_provider = "Conversion Disabled"

            receipt.total_amount = receipt.company_amount

            receipt.status = ExpenseReceipt.STATUS_AI_PROCESSED
            receipt.ai_status = ExpenseReceipt.AI_COMPLETED
            receipt.ai_error_message = None
            receipt.ai_extracted_data = parsed_data
            document_validation = parsed_data.get(
                "document_validation",
                {},
            )

            receipt.document_validation = document_validation
            ai_recommendation = parsed_data.get(
                "ai_recommendation",
                {},
            )

            receipt.ai_decision = ai_recommendation.get(
                "decision",
                "",
            )

            receipt.ai_decision_reason = ai_recommendation.get(
                "reason",
                "",
            )

            receipt.ai_decision_confidence = ai_recommendation.get(
                "confidence",
                0,
            )

            receipt.original_language = parsed_data.get(
                "document_language"
            )

            receipt.original_language_code = parsed_data.get(
                "document_language_code"
            )

            receipt.output_language = output_language_name
            receipt.output_language_code = output_language_code
            receipt.ai_extracted_data = parsed_data
            receipt.ai_confidence = overall_confidence

            receipt.save()
            create_audit_log(
    receipt=receipt,
    action=ExpenseAuditTrail.ACTION_AI_COMPLETED,
    remarks="AI successfully extracted receipt data.",
    metadata={
        "vendor": receipt.vendor_name,
        "amount": str(receipt.original_amount),
        "currency": receipt.original_currency,
    },
)

            # --------------------------------------------------------
            # Link ticket / invoice references
            # --------------------------------------------------------

            link_receipt(receipt)

            # --------------------------------------------------------
            # Create line items before duplicate/policy short-circuits.
            # Otherwise AI_COMPLETED receipts end up with zero lines, and
            # sync_receipt_totals_for_report later wipes the claim amount.
            # --------------------------------------------------------

            for bill in normalized_bills:

                amount = Decimal(
                    bill["amount"]
                )
                approved_bill_total = Decimal("0.00")

                bill_date = (
                    datetime.strptime(
                        bill["bill_date"],
                        "%Y-%m-%d",
                    ).date()
                    if bill.get("bill_date")
                    else None
                )

                line_items = normalize_bill_line_items(bill)

                if line_items:
                    for item in line_items:
                        item_name = item.get(
                            "name",
                            "",
                        )

                        item_subcategory = item.get(
                            "subcategory",
                            "",
                        )

                        try:
                            item_amount = Decimal(
                                str(item.get("total_price") or 0)
                            )
                        except Exception:
                            item_amount = Decimal("0.00")

                        if item_amount <= Decimal("0.00"):
                            continue

                        # Keep every printed line item. Non-reimbursable is a soft
                        # flag for policy review — never drop extracted products.
                        is_reimbursable = bool(item.get("is_reimbursable", True))
                        print(
                            "Creating ExpenseLineItem:",
                            item_name,
                            item_amount,
                            "reimbursable=",
                            is_reimbursable,
                        )
                        expense_item = ExpenseLineItem.objects.create(
                            receipt=receipt,
                            description=item_name,
                            category=item.get(
                                "category",
                                bill.get("type", "miscellaneous"),
                            ),
                            subcategory=item_subcategory,
                            vendor=bill.get(
                                "vendor",
                                "",
                            )[:255],
                            amount=item_amount,
                            bill_date=bill_date,
                            is_violating=not is_reimbursable,
                            violation_reason=(
                                item.get("reason", "")
                                if not is_reimbursable
                                else ""
                            ),
                        )

                        created_items.append(
                            expense_item.id
                        )
                        approved_bill_total += item_amount
                        _link_receipt_file_attachment(
                            expense_item,
                            receipt,
                        )
                elif amount > Decimal("0.00"):
                    expense_item = ExpenseLineItem.objects.create(
                        receipt=receipt,
                        description=(
                            bill.get("vendor")
                            or bill.get("type")
                            or "Receipt total"
                        ),
                        category=bill.get(
                            "type",
                            "miscellaneous",
                        ),
                        subcategory="",
                        vendor=bill.get(
                            "vendor",
                            "",
                        )[:255],
                        amount=amount,
                        bill_date=bill_date,
                    )

                    created_items.append(
                        expense_item.id
                    )
                    approved_bill_total = amount
                    _link_receipt_file_attachment(
                        expense_item,
                        receipt,
                    )

                bill["approved_amount"] = str(approved_bill_total)

            # --------------------------------------------------------
            # Duplicate + policy (after lines exist so UI can show them)
            # --------------------------------------------------------

            duplicate = find_duplicate_receipt(
                receipt=receipt,
            )

            if duplicate:
                receipt.has_duplicate_violation = True
                receipt.status = ExpenseReceipt.STATUS_POLICY_VIOLATION
                receipt.policy_violation_reason = (
                    f"Duplicate receipt detected. "
                    f"Original Receipt ID: {duplicate.id}"
                )
                receipt.has_any_violation = True

                receipt.save(update_fields=[
                    "has_duplicate_violation",
                    "has_any_violation",
                    "status",
                    "policy_violation_reason",
                ])

                DuplicateReceiptLog.objects.get_or_create(
                    original_receipt=duplicate,
                    duplicate_receipt=receipt,
                    defaults={
                        "duplicate_type": DuplicateReceiptLog.DUPLICATE_SAME_EMPLOYEE,
                    },
                )
            else:
                check_policy_violations(receipt)
                receipt.refresh_from_db()

            if receipt.report:
                recalculate_report_total(
                    receipt.report
                )
                

        # ====================================================
        # Success response
        # ====================================================

        return {
            "success": True,
            "receipt_id": str(receipt.id),
            "ai_status": ExpenseReceipt.AI_COMPLETED,

            "document_language": parsed_data.get(
                "document_language"
            ),

            "document_language_code": parsed_data.get(
                "document_language_code"
            ),

            "document_summary": parsed_data.get(
                "document_summary"
            ),

            "receipt_quality": parsed_data.get(
                "receipt_quality"
            ),

            "fraud_analysis": parsed_data.get(
                "fraud_analysis"
            ),

            "document_metadata": parsed_data.get(
                "document_metadata"
            ),

            "output_language": {
                "code": output_language_code,
                "name": output_language_name,
                "preserve_original_text": preserve_original_text,
            },

            "bills": normalized_bills,

            "line_items_created": [
                str(item_id)
                for item_id in created_items
            ],

            "original_amount": str(receipt.original_amount),
            "original_currency": receipt.original_currency,

            "company_amount": str(receipt.company_amount),
            "company_currency": receipt.company_currency,

            "exchange_rate": (
                str(receipt.exchange_rate)
                if receipt.exchange_rate is not None
                else None
            ),

            "exchange_rate_date": (
                receipt.exchange_rate_date.isoformat()
                if receipt.exchange_rate_date
                else None
            ),

            "exchange_rate_provider": receipt.exchange_rate_provider,

            "currency_conversion": conversion_result,

            "has_any_violation": receipt.has_any_violation,
            "violation_reason": receipt.policy_violation_reason,
        }

    except Exception as e:
        return _apply_ai_failure(receipt, str(e))