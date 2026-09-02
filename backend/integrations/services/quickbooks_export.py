import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
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
    QuickBooksNotFoundError,
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
                            mapping.quickbooks_account_id
                        ),
                        "name": (
                            mapping.quickbooks_account_name
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
# CLAIM EXPORT RECORD
# ==========================================================


def claim_quickbooks_export(
    *,
    integration,
    report,
    external_reference,
    export_total,
):
    """
    Atomically claim a QuickBooks export.

    The database lock is held only while changing the
    export record to PROCESSING.

    The lock is released BEFORE the external QuickBooks
    API request is made.

    This prevents two Celery workers from intentionally
    processing the same report at the same time.
    """

    with transaction.atomic():

        # --------------------------------------------------
        # Create the record if this is the first attempt.
        #
        # The database UniqueConstraint on:
        #
        #     integration + report
        #
        # guarantees only one export record per report
        # for this QuickBooks integration.
        # --------------------------------------------------

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

        # --------------------------------------------------
        # Lock the export row.
        # --------------------------------------------------

        export_record = (
            QuickBooksExportRecord.objects
            .select_for_update()
            .get(
                id=export_record.id
            )
        )

        # --------------------------------------------------
        # Already exported successfully.
        # --------------------------------------------------

        if (
            export_record.status
            == QuickBooksExportRecord.STATUS_SUCCESS
        ):

            transaction_id = (
                export_record.quickbooks_transaction_id
                or ""
            )

            message = (
                "This expense report has already "
                "been exported to QuickBooks."
            )

            if transaction_id:
                message += (
                    " QuickBooks transaction ID: "
                    f"{transaction_id}"
                )

            raise QuickBooksExportError(
                message
            )

        # --------------------------------------------------
        # Another worker is already exporting it.
        # --------------------------------------------------

        if (
            export_record.status
            == QuickBooksExportRecord.STATUS_PROCESSING
        ):

            raise QuickBooksExportError(
                (
                    "This expense report is already "
                    "being exported to QuickBooks."
                )
            )

        # --------------------------------------------------
        # PENDING / FAILED -> PROCESSING
        #
        # FAILED records are allowed to be claimed again
        # when an explicit retry or new Celery attempt runs.
        # --------------------------------------------------

        export_record.status = (
            QuickBooksExportRecord.STATUS_PROCESSING
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

        return export_record


# ==========================================================
# MARK EXPORT FAILED
# ==========================================================


def mark_quickbooks_export_failed(
    *,
    export_record,
    error,
):
    """
    Safely mark an export attempt as FAILED.
    """

    export_record.status = (
        QuickBooksExportRecord.STATUS_FAILED
    )

    export_record.error_message = str(
        error
    )

    export_record.save(
        update_fields=[
            "status",
            "error_message",
            "updated_at",
        ]
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
    - currency is explicitly sent to QuickBooks
    - duplicate successful exports are prevented
    - concurrent exports are prevented using PROCESSING
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
    # 4. LINE ITEMS
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
    # 5. EXPORT CURRENCY
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

    # Normalize currency before sending to QuickBooks.
    export_currency = (
        str(export_currency)
        .strip()
        .upper()
    )

    if not export_currency:

        raise QuickBooksExportError(
            "Export currency is invalid."
        )

    # ======================================================
    # 6. CATEGORY MAPPINGS
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
    # 7. BUILD PURCHASE LINES
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
    # 8. EXTERNAL REFERENCE
    # ======================================================

    external_reference = (
        f"ZEP-RPT-{report.id}"
    )

    # ======================================================
    # 9. CLAIM EXPORT RECORD
    # ======================================================
    #
    # IMPORTANT:
    #
    # claim_quickbooks_export() protects against:
    #
    # - duplicate successful exports
    # - concurrent exports
    #
    # The database lock is released before the external
    # QuickBooks API call is made.
    # ======================================================

    export_record = (
        claim_quickbooks_export(
            integration=integration,
            report=report,
            external_reference=external_reference,
            export_total=export_total,
        )
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

        mark_quickbooks_export_failed(
            export_record=export_record,
            error=exc,
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
                "stage": "AUTHENTICATION",
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

        error = QuickBooksExportError(
            (
                "QuickBooks payment account is not configured. "
                "Select a Bank or Credit Card account before "
                "exporting expense reports."
            )
        )

        mark_quickbooks_export_failed(
            export_record=export_record,
            error=error,
        )

        raise error

    if payment_account_type not in (
        "Bank",
        "Credit Card",
    ):

        error = QuickBooksExportError(
            (
                "Configured QuickBooks payment account "
                "must be a Bank or Credit Card account."
            )
        )

        mark_quickbooks_export_failed(
            export_record=export_record,
            error=error,
        )

        raise error

    # ======================================================
    # 11B. PAYMENT TYPE
    # ======================================================

    payment_type = (
        "CreditCard"
        if payment_account_type == "Credit Card"
        else "Cash"
    )

    # ======================================================
    # 11C. BUILD QUICKBOOKS PURCHASE PAYLOAD
    # ======================================================
    #
    # IMPORTANT:
    #
    # CurrencyRef is explicitly included.
    #
    # Previously ZepEx knew the report was INR but did not
    # send INR in the Purchase payload. QuickBooks therefore
    # created the Purchase using its default/home currency.
    #
    # Example:
    #
    # "CurrencyRef": {
    #     "value": "INR"
    # }
    #
    # ======================================================

    purchase_data = {

        "PaymentType": (
            payment_type
        ),

        "AccountRef": {
            "value": (
                payment_account_id
            ),
            "name": (
                payment_account_name
            ),
        },

        "CurrencyRef": {
            "value": (
                export_currency
            ),
        },

        "Line": (
            purchase_lines
        ),

        "PrivateNote": (
            memo[:4000]
        ),
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

        # ==================================================
        # DEBUG: LOG EXACT PAYLOAD SENT TO QUICKBOOKS
        # ==================================================
        #
        # Temporary diagnostic logging.
        #
        # This confirms whether CurrencyRef=INR is actually
        # present in the final payload immediately before
        # the QuickBooks API request.
        # ==================================================

        logger.info(
            (
                "QuickBooks Purchase payload before export. "
                "company=%s report=%s realm_id=%s "
                "requested_currency=%s payment_account=%s "
                "payload=%s"
            ),
            company.id,
            report.id,
            realm_id,
            export_currency,
            payment_account_id,
            purchase_data,
        )

        response = (
            client.create_purchase(
                realm_id=realm_id,
                access_token=access_token,
                purchase_data=purchase_data,
            )
        )

        # ==================================================
        # DEBUG: LOG QUICKBOOKS RESPONSE
        # ==================================================

        logger.info(
            (
                "QuickBooks Purchase raw response. "
                "company=%s report=%s response=%s"
            ),
            company.id,
            report.id,
            response,
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

        mark_quickbooks_export_failed(
            export_record=export_record,
            error=exc,
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
                "stage": (
                    "QUICKBOOKS_API"
                ),
                "requested_currency": (
                    export_currency
                ),
                "error": str(
                    exc
                ),
            },
        )

        raise

    # ======================================================
    # 13. READ ACTUAL QUICKBOOKS RESPONSE
    # ======================================================
    #
    # Do not assume QuickBooks used the requested currency.
    # Store what QuickBooks actually returned as well.
    # ======================================================

    quickbooks_currency_ref = (
        purchase.get(
            "CurrencyRef"
        )
        or {}
    )

    quickbooks_currency = (
            str(
                quickbooks_currency_ref.get(
                    "value"
                )
                or ""
            )
            .strip()
            .upper()
        )

    quickbooks_exchange_rate = (
        purchase.get(
            "ExchangeRate"
        )
    )

    quickbooks_home_total_amount = (
        purchase.get(
            "HomeTotalAmt"
        )
    )

    quickbooks_sync_token = (
        purchase.get(
            "SyncToken"
        )
    )

    quickbooks_txn_date = (
        purchase.get(
            "TxnDate"
        )
    )

    quickbooks_account_ref = (
        purchase.get(
            "AccountRef"
        )
        or {}
    )

    # ======================================================
    # 14. SUCCESS
    # ======================================================

    export_record.status = (
        QuickBooksExportRecord
        .STATUS_SUCCESS
    )

    export_record.quickbooks_transaction_id = (
        str(
            transaction_id
        )
    )

    export_record.exported_amount = (
        export_total
    )

    # ======================================================
    # STORE BOTH REQUESTED AND ACTUAL QUICKBOOKS VALUES
    # ======================================================

    export_record.response_data = {

        "quickbooks_transaction_id": (
            str(
                transaction_id
            )
        ),

        "sync_token": (
            quickbooks_sync_token
        ),

        # --------------------------------------------------
        # ZepEx requested currency
        # --------------------------------------------------

        "currency": (
            export_currency
        ),

        "requested_currency": (
            export_currency
        ),

        # --------------------------------------------------
        # Actual QuickBooks currency
        # --------------------------------------------------

        "quickbooks_currency": (
            quickbooks_currency
            or None
        ),

        "currency_ref": (
            quickbooks_currency_ref
            if quickbooks_currency_ref
            else None
        ),

        "exchange_rate": (
            quickbooks_exchange_rate
        ),

        "home_total_amount": (
            quickbooks_home_total_amount
        ),

        "txn_date": (
            quickbooks_txn_date
        ),

        "line_count": len(
            purchase_lines
        ),

        "payment_account": {
            "id": (
                payment_account_id
            ),
            "name": (
                payment_account_name
            ),
            "account_type": (
                payment_account_type
            ),
            "payment_type": (
                payment_type
            ),
        },

        "quickbooks_account_ref": (
            quickbooks_account_ref
            if quickbooks_account_ref
            else None
        ),
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

    # ======================================================
    # 15. SUCCESS AUDIT LOG
    # ======================================================

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

            # What ZepEx requested
            "requested_currency": (
                export_currency
            ),

            # What QuickBooks returned
            "quickbooks_currency": (
                quickbooks_currency
                or None
            ),

            "exchange_rate": (
                quickbooks_exchange_rate
            ),

            "home_total_amount": (
                quickbooks_home_total_amount
            ),

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

    # ======================================================
    # 16. LOG SUCCESS
    # ======================================================

    logger.info(
        (
            "QuickBooks export completed. "
            "company=%s report=%s "
            "transaction=%s amount=%s "
            "requested_currency=%s "
            "quickbooks_currency=%s"
        ),
        company.id,
        report.id,
        transaction_id,
        export_total,
        export_currency,
        (
            quickbooks_currency
            or "UNKNOWN"
        ),
    )

    # ======================================================
    # 17. RESPONSE
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

        # ZepEx requested currency
        "currency": (
            export_currency
        ),

        "requested_currency": (
            export_currency
        ),

        # Actual QuickBooks currency
        "quickbooks_currency": (
            quickbooks_currency
            or None
        ),

        "currency_ref": (
            quickbooks_currency_ref
            if quickbooks_currency_ref
            else None
        ),

        "exchange_rate": (
            quickbooks_exchange_rate
        ),

        "home_total_amount": (
            quickbooks_home_total_amount
        ),

        "line_count": len(
            purchase_lines
        ),

        "payment_account": {
            "id": (
                payment_account_id
            ),
            "name": (
                payment_account_name
            ),
            "account_type": (
                payment_account_type
            ),
            "payment_type": (
                payment_type
            ),
        },

        "export_record_id": str(
            export_record.id
        ),
    }

def reconcile_quickbooks_export(
    *,
    report_id,
    company,
):
    """
    Verify a successful ZepEx QuickBooks export against
    the actual Purchase transaction stored in QuickBooks.

    Reconciliation checks:

    - export record exists
    - export completed successfully
    - QuickBooks transaction ID exists
    - Purchase still exists in QuickBooks
    - transaction ID matches
    - exported amount matches QuickBooks TotalAmt
    - currency matches when QuickBooks returns CurrencyRef
    - payment account matches
    """

    # ==========================================================
    # 1. GET REPORT
    # ==========================================================

    try:
        report = (
            ExpenseReport.objects
            .select_related("company")
            .get(
                id=report_id,
                company=company,
            )
        )

    except ExpenseReport.DoesNotExist:
        raise QuickBooksExportError(
            "Expense report not found."
        )

    # ==========================================================
    # 2. GET QUICKBOOKS INTEGRATION
    # ==========================================================

    try:
        integration = (
            CompanyIntegration.objects
            .select_related("credential")
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

    # ==========================================================
    # 3. GET EXPORT RECORD
    # ==========================================================

    try:
        export_record = (
            QuickBooksExportRecord.objects
            .get(
                integration=integration,
                report=report,
            )
        )

    except QuickBooksExportRecord.DoesNotExist:
        raise QuickBooksExportError(
            "This report has not been exported to QuickBooks."
        )

    # ==========================================================
    # 4. EXPORT MUST BE SUCCESSFUL
    # ==========================================================

    if (
        export_record.status
        != QuickBooksExportRecord.STATUS_SUCCESS
    ):
        raise QuickBooksExportError(
            (
                "Only successfully exported reports "
                "can be reconciled."
            )
        )

    transaction_id = (
        export_record.quickbooks_transaction_id
        or ""
    ).strip()

    if not transaction_id:
        raise QuickBooksExportError(
            (
                "QuickBooks transaction ID is missing "
                "from the export record."
            )
        )

    # ==========================================================
    # 5. GET VALID QUICKBOOKS TOKEN
    # ==========================================================

    try:
        token_result = (
            get_valid_quickbooks_access_token(
                integration=integration,
            )
        )

        access_token = token_result["access_token"]
        config = token_result["config"]

        realm_id = config.get("realm_id")

        if not realm_id:
            raise QuickBooksExportError(
                "QuickBooks realm ID is missing."
            )

    except Exception as exc:

        export_record.reconciliation_status = (
            QuickBooksExportRecord
            .RECONCILIATION_ERROR
        )

        export_record.reconciliation_error = str(exc)
        export_record.reconciled_at = timezone.now()

        export_record.save(
            update_fields=[
                "reconciliation_status",
                "reconciliation_error",
                "reconciled_at",
                "updated_at",
            ]
        )

        raise

    # ==========================================================
    # 6. FETCH PURCHASE FROM QUICKBOOKS
    # ==========================================================

    try:
        client = QuickBooksClient()

        response = client.get_purchase(
            realm_id=realm_id,
            access_token=access_token,
            purchase_id=transaction_id,
        )

        purchase = (
            response.get("Purchase")
            or {}
        )

        if not purchase:
            raise QuickBooksExportError(
                (
                    "QuickBooks did not return "
                    "the Purchase transaction."
                )
            )

    except QuickBooksNotFoundError as exc:

        export_record.reconciliation_status = (
            QuickBooksExportRecord
            .RECONCILIATION_MISSING
        )

        export_record.reconciliation_error = (
            "QuickBooks transaction was not found."
        )

        export_record.reconciled_at = timezone.now()

        export_record.reconciliation_data = {
            "expected": {
                "transaction_id": transaction_id,
                "amount": str(
                    _money(export_record.exported_amount)
                ),
                "currency": (
                    str(
                        (
                            export_record.response_data
                            if isinstance(
                                export_record.response_data,
                                dict,
                            )
                            else {}
                        ).get("currency")
                        or ""
                    )
                    .strip()
                    .upper()
                ),
                "payment_account_id": (
                    str(
                        (
                            (
                                export_record.response_data
                                if isinstance(
                                    export_record.response_data,
                                    dict,
                                )
                                else {}
                            ).get("payment_account")
                            or {}
                        ).get("id")
                        or ""
                    )
                    .strip()
                ),
            },
            "quickbooks": None,
            "mismatches": [
                {
                    "field": "transaction",
                    "expected": transaction_id,
                    "actual": None,
                    "reason": (
                        "QuickBooks transaction was not found."
                    ),
                }
            ],
        }

        export_record.save(
            update_fields=[
                "reconciliation_status",
                "reconciliation_error",
                "reconciliation_data",
                "reconciled_at",
                "updated_at",
            ]
        )

        create_integration_audit_log(
            company=company,
            integration=integration,
            provider="QUICKBOOKS",
            action="QUICKBOOKS_RECONCILIATION_MISSING",
            action_by=None,
            message=(
                "QuickBooks transaction is missing "
                "during reconciliation."
            ),
            metadata={
                "report_id": str(report.id),
                "export_record_id": str(
                    export_record.id
                ),
                "quickbooks_transaction_id": (
                    transaction_id
                ),
                "reconciliation_status": (
                    QuickBooksExportRecord
                    .RECONCILIATION_MISSING
                ),
                "error": str(exc),
            },
        )

        return {
            "success": False,
            "report_id": str(report.id),
            "export_record_id": str(
                export_record.id
            ),
            "quickbooks_transaction_id": (
                transaction_id
            ),
            "reconciliation_status": (
                QuickBooksExportRecord
                .RECONCILIATION_MISSING
            ),
            "mismatches": (
                export_record
                .reconciliation_data
                .get("mismatches", [])
            ),
            "quickbooks_purchase": None,
            "error": (
                "QuickBooks transaction was not found."
            ),
            "reconciled_at": (
                export_record
                .reconciled_at
                .isoformat()
            ),
        }

    except Exception as exc:

        export_record.reconciliation_status = (
            QuickBooksExportRecord
            .RECONCILIATION_ERROR
        )

        export_record.reconciliation_error = str(exc)
        export_record.reconciled_at = timezone.now()

        export_record.save(
            update_fields=[
                "reconciliation_status",
                "reconciliation_error",
                "reconciled_at",
                "updated_at",
            ]
        )

        create_integration_audit_log(
            company=company,
            integration=integration,
            provider="QUICKBOOKS",
            action="QUICKBOOKS_RECONCILIATION_ERROR",
            action_by=None,
            message=(
                "QuickBooks transaction reconciliation failed."
            ),
            metadata={
                "report_id": str(report.id),
                "export_record_id": str(export_record.id),
                "quickbooks_transaction_id": transaction_id,
                "error": str(exc),
            },
        )

        raise

    # ==========================================================
    # 7. EXPECTED ZEPEx VALUES
    # ==========================================================

    expected_amount = _money(
        export_record.exported_amount
    )

    response_data = (
        export_record.response_data
        if isinstance(
            export_record.response_data,
            dict,
        )
        else {}
    )

    expected_currency = (
        str(
            response_data.get("currency")
            or ""
        )
        .strip()
        .upper()
    )

    payment_account = (
        response_data.get("payment_account")
        or {}
    )

    expected_payment_account_id = (
        str(
            payment_account.get("id")
            or ""
        )
        .strip()
    )

    # ==========================================================
    # 8. ACTUAL QUICKBOOKS VALUES
    # ==========================================================

    actual_transaction_id = (
        str(
            purchase.get("Id")
            or ""
        )
        .strip()
    )

    actual_amount = _money(
        purchase.get("TotalAmt")
    )

    currency_ref = (
        purchase.get("CurrencyRef")
        or {}
    )

    actual_currency = (
        str(
            currency_ref.get("value")
            or ""
        )
        .strip()
        .upper()
    )

    account_ref = (
        purchase.get("AccountRef")
        or {}
    )

    actual_payment_account_id = (
        str(
            account_ref.get("value")
            or ""
        )
        .strip()
    )

    # ==========================================================
    # ADDITIONAL QUICKBOOKS VALUES
    # ==========================================================

    exchange_rate = purchase.get(
        "ExchangeRate"
    )

    home_total_amount = purchase.get(
        "HomeTotalAmt"
    )

    txn_date = purchase.get(
        "TxnDate"
    )

    sync_token = purchase.get(
        "SyncToken"
    )

    private_note = purchase.get(
        "PrivateNote"
    )

    quickbooks_lines = (
        purchase.get("Line")
        or []
    )

    # ==========================================================
    # 9. COMPARE
    # ==========================================================

    mismatches = []

    if actual_transaction_id != transaction_id:

        mismatches.append(
            {
                "field": "transaction_id",
                "expected": transaction_id,
                "actual": actual_transaction_id,
            }
        )

    if actual_amount != expected_amount:

        mismatches.append(
            {
                "field": "amount",
                "expected": str(expected_amount),
                "actual": str(actual_amount),
            }
        )

    # ----------------------------------------------------------
    # Currency
    #
    # Only compare when QuickBooks actually returns CurrencyRef.
    # ----------------------------------------------------------

    if (
        expected_currency
        and actual_currency
        and expected_currency != actual_currency
    ):

        mismatches.append(
            {
                "field": "currency",
                "expected": expected_currency,
                "actual": actual_currency,
            }
        )

    # ----------------------------------------------------------
    # Payment account
    # ----------------------------------------------------------

    if (
        expected_payment_account_id
        and actual_payment_account_id
        and (
            expected_payment_account_id
            != actual_payment_account_id
        )
    ):

        mismatches.append(
            {
                "field": "payment_account",
                "expected": (
                    expected_payment_account_id
                ),
                "actual": (
                    actual_payment_account_id
                ),
            }
        )

    # ==========================================================
    # 10. RECONCILIATION STATUS
    # ==========================================================

    if mismatches:

        reconciliation_status = (
            QuickBooksExportRecord
            .RECONCILIATION_MISMATCH
        )

    else:

        reconciliation_status = (
            QuickBooksExportRecord
            .RECONCILIATION_VERIFIED
        )

    # ==========================================================
    # 11. BUILD QUICKBOOKS PURCHASE DETAILS
    # ==========================================================

    quickbooks_purchase = {
        "id": actual_transaction_id,

        "total_amount": (
            str(actual_amount)
        ),

        "currency_ref": (
            currency_ref
            if currency_ref
            else None
        ),

        "currency": (
            actual_currency
            or None
        ),

        "exchange_rate": exchange_rate,

        "home_total_amount": (
            home_total_amount
        ),

        "account_ref": (
            account_ref
            if account_ref
            else None
        ),

        "payment_account_id": (
            actual_payment_account_id
            or None
        ),

        "txn_date": txn_date,

        "sync_token": sync_token,

        "private_note": private_note,

        "line_count": len(
            quickbooks_lines
        ),
    }

    # ==========================================================
    # 12. STORE RECONCILIATION RESULT
    # ==========================================================

    export_record.reconciliation_status = (
        reconciliation_status
    )

    export_record.reconciliation_error = None

    export_record.reconciled_at = timezone.now()

    export_record.reconciliation_data = {

        # ------------------------------------------------------
        # Expected ZepEx values
        # ------------------------------------------------------

        "expected": {
            "transaction_id": (
                transaction_id
            ),
            "amount": str(
                expected_amount
            ),
            "currency": (
                expected_currency
            ),
            "payment_account_id": (
                expected_payment_account_id
            ),
        },

        # ------------------------------------------------------
        # Actual QuickBooks values
        # ------------------------------------------------------

        "quickbooks": (
            quickbooks_purchase
        ),

        # ------------------------------------------------------
        # Comparison
        # ------------------------------------------------------

        "mismatches": (
            mismatches
        ),
    }

    export_record.save(
        update_fields=[
            "reconciliation_status",
            "reconciliation_error",
            "reconciliation_data",
            "reconciled_at",
            "updated_at",
        ]
    )

    # ==========================================================
    # 13. AUDIT LOG
    # ==========================================================

    action = (
        "QUICKBOOKS_RECONCILIATION_VERIFIED"
        if not mismatches
        else "QUICKBOOKS_RECONCILIATION_MISMATCH"
    )

    create_integration_audit_log(
        company=company,
        integration=integration,
        provider="QUICKBOOKS",
        action=action,
        action_by=None,
        message=(
            "QuickBooks transaction reconciliation completed."
        ),
        metadata={
            "report_id": str(
                report.id
            ),
            "export_record_id": str(
                export_record.id
            ),
            "quickbooks_transaction_id": (
                transaction_id
            ),
            "reconciliation_status": (
                reconciliation_status
            ),
            "mismatches": (
                mismatches
            ),
        },
    )

    # ==========================================================
    # 14. RESPONSE
    # ==========================================================

    return {
        "success": (
            reconciliation_status
            == QuickBooksExportRecord
            .RECONCILIATION_VERIFIED
        ),

        "report_id": str(
            report.id
        ),

        "export_record_id": str(
            export_record.id
        ),

        "quickbooks_transaction_id": (
            transaction_id
        ),

        "reconciliation_status": (
            reconciliation_status
        ),

        "mismatches": (
            mismatches
        ),

        # ------------------------------------------------------
        # IMPORTANT:
        # Actual transaction returned by QuickBooks.
        # ------------------------------------------------------

        "quickbooks_purchase": (
            quickbooks_purchase
        ),

        "reconciled_at": (
            export_record
            .reconciled_at
            .isoformat()
        ),
    }
