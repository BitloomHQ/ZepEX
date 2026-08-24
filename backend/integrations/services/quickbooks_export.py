import logging
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from audit_logs.utils import create_integration_audit_log
from expenses.models import (
    ExpenseReport,
    ExpenseLineItem,
)

from integrations.models import (
    CompanyIntegration,
    QuickBooksCategoryMapping,
    QuickBooksExportRecord,
)

from .quickbooks import (
    QuickBooksClient,
)

from .quickbooks_auth import (
    get_valid_quickbooks_access_token,
)


logger = logging.getLogger(__name__)


# ==========================================================
# EXCEPTIONS
# ==========================================================


class QuickBooksExportError(Exception):
    """
    Raised when a ZepEx expense report cannot
    be exported to QuickBooks.
    """


# ==========================================================
# HELPERS
# ==========================================================


def normalize_category(value):
    """
    Normalize ZepEx expense category.

    Examples:

        Hotel -> hotel
        Flight Ticket -> flight_ticket
        FLIGHT_TICKET -> flight_ticket
    """

    return (
        str(value or "")
        .strip()
        .lower()
        .replace(" ", "_")
    )


def _money(value):
    """
    Convert value safely into a 2-decimal Decimal.
    """

    return Decimal(
        str(value or 0)
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


# ==========================================================
# EXPORTABLE LINE ITEMS
# ==========================================================


def get_exportable_line_items(report):
    """
    Return approved/exportable line items.

    Approval-stage removed lines are excluded.
    """

    return (
        ExpenseLineItem.objects
        .filter(
            receipt__report=report,
            is_removed=False,
        )
        .select_related(
            "receipt",
        )
        .order_by(
            "receipt__invoice_date",
            "created_at",
        )
    )


# ==========================================================
# CATEGORY MAPPINGS
# ==========================================================


def get_category_mapping_dictionary(
    integration,
):
    """
    Build:

        {
            "hotel": mapping,
            "food": mapping,
            ...
        }
    """

    mappings = (
        QuickBooksCategoryMapping.objects
        .filter(
            integration=integration,
            is_active=True,
        )
    )

    return {
        normalize_category(
            mapping.zepex_category
        ): mapping
        for mapping in mappings
    }


# ==========================================================
# LINE ITEM COMPANY AMOUNT
# ==========================================================


def get_line_item_company_amount(item):
    """
    Return the amount that should be posted
    into the company's accounting system.

    Preferred:
        ExpenseLineItem.company_amount

    Backward compatibility:
        item.amount converted using receipt.exchange_rate

    If original currency == company currency:
        item.amount can be used directly.
    """

    # ------------------------------------------------------
    # New architecture:
    # use explicit company reimbursement amount
    # ------------------------------------------------------

    if item.company_amount is not None:

        amount = _money(
            item.company_amount
        )

        return amount

    receipt = item.receipt

    # ------------------------------------------------------
    # Existing / legacy line item
    # ------------------------------------------------------

    original_currency = (
        item.original_currency
        or receipt.original_currency
        or receipt.currency
        or ""
    ).strip().upper()

    company_currency = (
        item.company_currency
        or receipt.company_currency
        or receipt.currency
        or ""
    ).strip().upper()

    amount = _money(
        item.original_amount
        if item.original_amount is not None
        else item.amount
    )

    # ------------------------------------------------------
    # Same currency — no conversion needed
    # ------------------------------------------------------

    if (
        not original_currency
        or not company_currency
        or original_currency == company_currency
    ):

        return amount

    # ------------------------------------------------------
    # Different currencies — exchange rate required
    # ------------------------------------------------------

    exchange_rate = (
        item.exchange_rate
        or receipt.exchange_rate
    )

    if not exchange_rate:

        raise QuickBooksExportError(
            (
                "Currency conversion information "
                "is missing for expense line item "
                f"{item.id}. "
                f"{original_currency} -> "
                f"{company_currency}."
            )
        )

    converted_amount = (
        amount
        * Decimal(
            str(exchange_rate)
        )
    )

    return converted_amount.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


# ==========================================================
# DETERMINE REPORT EXPORT CURRENCY
# ==========================================================


def get_report_company_currency(report):
    """
    Determine the reimbursement/accounting currency
    for the complete report.

    A single QuickBooks export must not silently mix
    multiple company reimbursement currencies.
    """

    company_currencies = set()

    # ------------------------------------------------------
    # Receipt company currencies
    # ------------------------------------------------------

    receipt_currencies = (
        report.receipts
        .exclude(
            company_currency__isnull=True,
        )
        .exclude(
            company_currency="",
        )
        .values_list(
            "company_currency",
            flat=True,
        )
    )

    for currency in receipt_currencies:

        currency = (
            str(currency or "")
            .strip()
            .upper()
        )

        if currency:
            company_currencies.add(
                currency
            )

    # ------------------------------------------------------
    # Also inspect line-item currencies
    # ------------------------------------------------------

    line_item_currencies = (
        ExpenseLineItem.objects
        .filter(
            receipt__report=report,
            is_removed=False,
        )
        .exclude(
            company_currency__isnull=True,
        )
        .exclude(
            company_currency="",
        )
        .values_list(
            "company_currency",
            flat=True,
        )
    )

    for currency in line_item_currencies:

        currency = (
            str(currency or "")
            .strip()
            .upper()
        )

        if currency:
            company_currencies.add(
                currency
            )

    # ------------------------------------------------------
    # Multiple currencies should not be exported together
    # ------------------------------------------------------

    if len(company_currencies) > 1:

        raise QuickBooksExportError(
            (
                "Expense report contains multiple "
                "company reimbursement currencies: "
                f"{', '.join(sorted(company_currencies))}."
            )
        )

    if company_currencies:

        return next(
            iter(company_currencies)
        )

    # ------------------------------------------------------
    # Legacy fallback
    # ------------------------------------------------------

    fallback_currency = (
        report.receipts
        .exclude(
            currency__isnull=True,
        )
        .exclude(
            currency="",
        )
        .values_list(
            "currency",
            flat=True,
        )
        .first()
    )

    if fallback_currency:

        return (
            str(fallback_currency)
            .strip()
            .upper()
        )

    return None


# ==========================================================
# BUILD QUICKBOOKS PURCHASE LINES
# ==========================================================


def build_quickbooks_purchase_lines(
    *,
    line_items,
    mappings,
):
    """
    Convert ZepEx line items into QuickBooks
    AccountBasedExpenseLineDetail lines.

    IMPORTANT:
    Uses company reimbursement amount rather than
    original foreign-currency amount.
    """

    quickbooks_lines = []

    missing_categories = set()

    total = Decimal("0.00")

    for item in line_items:

        category = normalize_category(
            item.category
        )

        # --------------------------------------------------
        # Find QuickBooks account mapping
        # --------------------------------------------------

        mapping = mappings.get(
            category
        )

        if not mapping:

            missing_categories.add(
                category or "uncategorized"
            )

            continue

        # --------------------------------------------------
        # Company reimbursement amount
        # --------------------------------------------------

        amount = (
            get_line_item_company_amount(
                item
            )
        )

        if amount <= 0:
            continue

        receipt = item.receipt

        # --------------------------------------------------
        # Build description
        # --------------------------------------------------

        description_parts = []

        if item.description:

            description_parts.append(
                str(item.description)
                .strip()
            )

        vendor = (
            item.vendor
            or receipt.vendor_name
        )

        if vendor:

            description_parts.append(
                f"Vendor: {vendor}"
            )

        if item.bill_date:

            description_parts.append(
                (
                    "Bill date: "
                    f"{item.bill_date.isoformat()}"
                )
            )

        elif receipt.invoice_date:

            description_parts.append(
                (
                    "Invoice date: "
                    f"{receipt.invoice_date.isoformat()}"
                )
            )

        if receipt.reference_number:

            description_parts.append(
                (
                    "Ref: "
                    f"{receipt.reference_number}"
                )
            )

        description = " | ".join(
            description_parts
        )

        # --------------------------------------------------
        # QuickBooks line
        # --------------------------------------------------

        quickbooks_lines.append(
            {
                "Amount": float(
                    amount
                ),

                "DetailType": (
                    "AccountBasedExpenseLineDetail"
                ),

                "Description": (
                    description[:4000]
                    if description
                    else (
                        "ZepEx reimbursement - "
                        f"{category}"
                    )
                ),

                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {
                        "value": str(
                            mapping
                            .quickbooks_account_id
                        ),
                        "name": (
                            mapping
                            .quickbooks_account_name
                        ),
                    }
                },
            }
        )

        total += amount

    # ------------------------------------------------------
    # Missing account mappings
    # ------------------------------------------------------

    if missing_categories:

        categories = ", ".join(
            sorted(
                missing_categories
            )
        )

        raise QuickBooksExportError(
            (
                "QuickBooks account mapping "
                "is missing for: "
                f"{categories}."
            )
        )

    if not quickbooks_lines:

        raise QuickBooksExportError(
            (
                "This report has no exportable "
                "expense line items."
            )
        )

    total = total.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return (
        quickbooks_lines,
        total,
    )


# ==========================================================
# EXPORT REPORT
# ==========================================================


def export_report_to_quickbooks(
    *,
    report_id,
    company,
):
    """
    Export one PAID ZepEx ExpenseReport
    to QuickBooks.

    Rules:

    - report must belong to company
    - report must be PAID
    - removed line items are excluded
    - all categories must be mapped
    - company reimbursement currency is used
    - duplicate successful exports are prevented
    """

    # ======================================================
    # 1. GET REPORT
    # ======================================================

    try:

        report = (
            ExpenseReport.objects
            .select_related(
                "company",
                "employee",
                "employee__user",
                "department",
            )
            .get(
                id=report_id,
                company=company,
            )
        )

    except ExpenseReport.DoesNotExist:

        raise QuickBooksExportError(
            "Expense report not found."
        )

    # ======================================================
    # 2. REPORT MUST BE PAID
    # ======================================================

    if (
        report.status
        != ExpenseReport.STATUS_PAID
    ):

        raise QuickBooksExportError(
            (
                "Only PAID expense reports "
                "can be exported to QuickBooks."
            )
        )

    # ======================================================
    # 3. QUICKBOOKS INTEGRATION
    # ======================================================

    try:

        integration = (
            CompanyIntegration.objects
            .select_related(
                "credential"
            )
            .get(
                company=company,
                provider=(
                    CompanyIntegration
                    .PROVIDER_QUICKBOOKS
                ),
                is_connected=True,
                is_active=True,
            )
        )

    except CompanyIntegration.DoesNotExist:

        raise QuickBooksExportError(
            "QuickBooks is not connected."
        )

    # ======================================================
    # 4. DUPLICATE SUCCESS CHECK
    # ======================================================

    existing_export = (
        QuickBooksExportRecord.objects
        .filter(
            integration=integration,
            report=report,
            status=(
                QuickBooksExportRecord
                .STATUS_SUCCESS
            ),
        )
        .first()
    )

    if existing_export:

        raise QuickBooksExportError(
            (
                "This expense report has already "
                "been exported to QuickBooks. "
                "QuickBooks transaction ID: "
                f"{existing_export.quickbooks_transaction_id}"
            )
        )

    # ======================================================
    # 5. LINE ITEMS
    # ======================================================

    line_items = list(
        get_exportable_line_items(
            report
        )
    )

    if not line_items:

        raise QuickBooksExportError(
            (
                "The expense report has no "
                "exportable line items."
            )
        )

    # ======================================================
    # 6. EXPORT CURRENCY
    # ======================================================

    export_currency = (
        get_report_company_currency(
            report
        )
    )

    if not export_currency:

        raise QuickBooksExportError(
            (
                "Unable to determine company "
                "reimbursement currency."
            )
        )

    # ======================================================
    # 7. CATEGORY MAPPINGS
    # ======================================================

    mappings = (
        get_category_mapping_dictionary(
            integration
        )
    )

    if not mappings:

        raise QuickBooksExportError(
            (
                "No QuickBooks category mappings "
                "have been configured."
            )
        )

    # ======================================================
    # 8. BUILD PURCHASE LINES
    # ======================================================

    purchase_lines, export_total = (
        build_quickbooks_purchase_lines(
            line_items=line_items,
            mappings=mappings,
        )
    )

    if export_total <= 0:

        raise QuickBooksExportError(
            (
                "Export amount must be greater "
                "than zero."
            )
        )

    # ======================================================
    # 9. CREATE / GET EXPORT RECORD
    # ======================================================

    external_reference = (
        f"ZEP-RPT-{report.id}"
    )

    export_record, _ = (
        QuickBooksExportRecord.objects
        .get_or_create(
            integration=integration,
            report=report,
            defaults={
                "external_reference": (
                    external_reference
                ),
                "status": (
                    QuickBooksExportRecord
                    .STATUS_PENDING
                ),
                "exported_amount": (
                    export_total
                ),
            },
        )
    )

    if (
        export_record.status
        == QuickBooksExportRecord.STATUS_SUCCESS
    ):

        raise QuickBooksExportError(
            (
                "This report has already been "
                "exported to QuickBooks."
            )
        )

    export_record.status = (
        QuickBooksExportRecord.STATUS_PENDING
    )

    export_record.error_message = None

    export_record.exported_amount = (
        export_total
    )

    export_record.save(
        update_fields=[
            "status",
            "error_message",
            "exported_amount",
            "updated_at",
        ]
    )

    # ======================================================
    # 10. GET VALID QUICKBOOKS TOKEN
    # ======================================================

    try:

        token_result = (
            get_valid_quickbooks_access_token(
                integration=integration,
            )
        )

        access_token = (
            token_result[
                "access_token"
            ]
        )

        config = (
            token_result[
                "config"
            ]
        )

        realm_id = config.get(
            "realm_id"
        )

        if not realm_id:

            raise QuickBooksExportError(
                (
                    "QuickBooks realm ID "
                    "is missing."
                )
            )

    except Exception as exc:

        export_record.status = (
            QuickBooksExportRecord.STATUS_FAILED
        )

        export_record.error_message = str(
            exc
        )

        export_record.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )
        create_integration_audit_log(
    company=company,
    integration=integration,
    provider="QUICKBOOKS",
    action="QUICKBOOKS_EXPORT_FAILED",
    action_by=None,
    message=(
        "Expense report export to "
        "QuickBooks failed."
    ),
    metadata={
        "report_id": str(
            report.id
        ),
        "export_record_id": str(
            export_record.id
        ),
        "stage": "QUICKBOOKS_API",
        "error": str(
            exc
        ),
    },
)
        raise

    # ======================================================
    # 11. BUILD QUICKBOOKS PURCHASE
    # ======================================================

    employee_email = (
        report.employee.user.email
        or ""
    )

    memo = (
        f"ZepEx reimbursement | "
        f"{employee_email} | "
        f"{report.month:%B %Y} | "
        f"{external_reference}"
    )

    # ======================================================
    # 11A. QUICKBOOKS PAYMENT ACCOUNT
    # ======================================================

    payment_account_id = (
        integration.quickbooks_payment_account_id
        or ""
    ).strip()

    payment_account_name = (
        integration.quickbooks_payment_account_name
        or ""
    ).strip()

    payment_account_type = (
        integration.quickbooks_payment_account_type
        or ""
    ).strip()

    if not payment_account_id:
        raise QuickBooksExportError(
            (
                "QuickBooks payment account is not configured. "
                "Select a Bank or Credit Card account before "
                "exporting expense reports."
            )
        )

    if payment_account_type not in (
        "Bank",
        "Credit Card",
    ):
        raise QuickBooksExportError(
            (
                "Configured QuickBooks payment account "
                "must be a Bank or Credit Card account."
            )
        )

    # ======================================================
    # 11B. BUILD QUICKBOOKS PURCHASE
    # ======================================================

    payment_type = (
        "CreditCard"
        if payment_account_type == "Credit Card"
        else "Cash"
    )

    purchase_data = {
        "PaymentType": payment_type,

        "AccountRef": {
            "value": payment_account_id,
            "name": payment_account_name,
        },

        "Line": purchase_lines,

        "PrivateNote": memo[:4000],
    }
    # ------------------------------------------------------
    # Paid date becomes QuickBooks transaction date
    # ------------------------------------------------------

    if report.paid_at:

        purchase_data[
            "TxnDate"
        ] = (
            report.paid_at
            .date()
            .isoformat()
        )

    # ======================================================
    # 12. SEND TO QUICKBOOKS
    # ======================================================

    try:

        client = QuickBooksClient()

        response = (
            client.create_purchase(
                realm_id=realm_id,
                access_token=access_token,
                purchase_data=purchase_data,
            )
        )

        purchase = (
            response.get(
                "Purchase"
            )
            or {}
        )

        transaction_id = (
            purchase.get(
                "Id"
            )
        )

        if not transaction_id:

            raise QuickBooksExportError(
                (
                    "QuickBooks returned an "
                    "unexpected response without "
                    "a transaction ID."
                )
            )

    except Exception as exc:

        logger.exception(
            (
                "QuickBooks export failed. "
                "report=%s"
            ),
            report.id,
        )

        export_record.status = (
            QuickBooksExportRecord.STATUS_FAILED
        )

        export_record.error_message = str(
            exc
        )

        export_record.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )
        create_integration_audit_log(
        company=company,
        integration=integration,
        provider="QUICKBOOKS",
        action="QUICKBOOKS_EXPORT_FAILED",
        action_by=None,
        message=(
            "Expense report export to "
            "QuickBooks failed."
        ),
        metadata={
            "report_id": str(
                report.id
            ),
            "export_record_id": str(
                export_record.id
            ),
            "error": str(
                exc
            ),
        },
        )
        raise

    # ======================================================
    # 13. SUCCESS
    # ======================================================

    export_record.status = (
        QuickBooksExportRecord.STATUS_SUCCESS
    )

    export_record.quickbooks_transaction_id = (
        str(transaction_id)
    )

    export_record.exported_amount = (
        export_total
    )

    export_record.response_data = {
        "quickbooks_transaction_id": (
            str(transaction_id)
        ),
        "sync_token": (
            purchase.get(
                "SyncToken"
            )
        ),
        "currency": export_currency,
        "line_count": len(
            purchase_lines
        ),
        "payment_account": {
            "id": payment_account_id,
            "name": payment_account_name,
            "account_type": payment_account_type,
            "payment_type": payment_type,
        },
    }

    export_record.exported_at = (
        timezone.now()
    )

    export_record.error_message = None

    export_record.save(
        update_fields=[
            "status",
            "quickbooks_transaction_id",
            "exported_amount",
            "response_data",
            "exported_at",
            "error_message",
            "updated_at",
        ]
    )
    create_integration_audit_log(
        company=company,
        integration=integration,
        provider="QUICKBOOKS",
        action="QUICKBOOKS_EXPORT_SUCCESS",
        action_by=None,
        message=(
            "Expense report exported to "
            "QuickBooks successfully."
        ),
        metadata={
            "report_id": str(
                report.id
            ),
            "export_record_id": str(
                export_record.id
            ),
            "quickbooks_transaction_id": str(
                transaction_id
            ),
            "amount": str(
                export_total
            ),
            "currency": export_currency,
            "payment_account_id": (
                payment_account_id
            ),
            "payment_account_name": (
                payment_account_name
            ),
            "payment_account_type": (
                payment_account_type
            ),
        },
    )
    logger.info(
        (
            "QuickBooks export completed. "
            "company=%s report=%s "
            "transaction=%s amount=%s %s"
        ),
        company.id,
        report.id,
        transaction_id,
        export_total,
        export_currency,
    )

    # ======================================================
    # 14. RESPONSE
    # ======================================================

    return {
        "success": True,

        "message": (
            "Expense report exported to "
            "QuickBooks successfully."
        ),

        "report_id": str(
            report.id
        ),

        "quickbooks_transaction_id": str(
            transaction_id
        ),

        "external_reference": (
            external_reference
        ),

        "amount": str(
            export_total
        ),

        "currency": (
            export_currency
        ),

        "line_count": len(
            purchase_lines
        ),

        "export_record_id": str(
            export_record.id
        ),
    }