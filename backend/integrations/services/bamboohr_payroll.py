import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from audit_logs.utils import create_integration_audit_log
from expenses.models import ExpenseReport
from expenses.payment_services import ExpensePaymentError, mark_approved_report_paid
from expenses.services import recalculate_receipt_from_line_items, recalculate_report_total

from integrations.encryption_services import (
    decrypt_integration_config,
    encrypt_integration_config,
)
from integrations.models import (
    BambooHRPayrollBatch,
    BambooHRPayrollBatchItem,
    CompanyIntegration,
    IntegrationCredential,
    IntegrationEmployeeMapping,
)
from integrations.services.bamboohr import (
    BambooHRAuthenticationError,
    BambooHRClient,
    BambooHRIntegrationError,
    BambooHROAuthService,
)
from integrations.services.quickbooks_export import get_report_company_currency


class BambooHRPayrollError(Exception):
    def __init__(self, message, *, code="BAMBOOHR_PAYROLL_ERROR"):
        super().__init__(message)
        self.code = code


def can_manage_bamboohr_payroll(profile):
    """Payroll confirmation uses the same authority as Accounts mark-paid."""

    if profile.role == "COMPANY_ADMIN":
        return True

    return bool(
        profile.company_role
        and profile.company_role.can_mark_paid
    )


def get_connected_bamboohr_integration(company):
    integration = (
        CompanyIntegration.objects
        .filter(
            company=company,
            provider=CompanyIntegration.PROVIDER_BAMBOOHR,
            is_connected=True,
            is_active=True,
        )
        .first()
    )
    if not integration:
        raise BambooHRPayrollError(
            "BambooHR is not connected.",
            code="BAMBOOHR_NOT_CONNECTED",
        )
    return integration


def _read_bamboohr_config(integration):
    try:
        credential = integration.credential
    except IntegrationCredential.DoesNotExist as exc:
        raise BambooHRPayrollError(
            "BambooHR credentials are missing.",
            code="BAMBOOHR_CREDENTIALS_MISSING",
        ) from exc

    try:
        config = decrypt_integration_config(credential.encrypted_config)
    except Exception as exc:
        raise BambooHRPayrollError(
            "Unable to decrypt BambooHR credentials.",
            code="BAMBOOHR_CREDENTIALS_INVALID",
        ) from exc

    if not isinstance(config, dict):
        raise BambooHRPayrollError(
            "BambooHR credentials are invalid.",
            code="BAMBOOHR_CREDENTIALS_INVALID",
        )

    return credential, config


def _fetch_bamboohr_payroll_employee(integration, employee_id):
    """Fetch payroll-readiness fields and refresh OAuth once when required."""

    credential, config = _read_bamboohr_config(integration)
    company_domain = str(config.get("company_domain") or "").strip()
    access_token = str(config.get("access_token") or "").strip()
    refresh_token = str(config.get("refresh_token") or "").strip()

    if not company_domain or not access_token:
        raise BambooHRPayrollError(
            "BambooHR OAuth configuration is incomplete.",
            code="BAMBOOHR_OAUTH_INCOMPLETE",
        )

    fields = [
        "firstName",
        "lastName",
        "workEmail",
        "status",
        "employeeNumber",
        "includeInPayroll",
    ]

    client = BambooHRClient(
        company_domain=company_domain,
        access_token=access_token,
    )

    try:
        return client.get_employee(employee_id, fields=fields)
    except BambooHRAuthenticationError:
        if not refresh_token:
            raise BambooHRPayrollError(
                "BambooHR access token expired and no refresh token is available.",
                code="BAMBOOHR_REFRESH_TOKEN_MISSING",
            )
    except BambooHRIntegrationError as exc:
        raise BambooHRPayrollError(
            str(exc),
            code="BAMBOOHR_EMPLOYEE_VALIDATION_FAILED",
        ) from exc

    oauth_service = BambooHROAuthService(company_domain=company_domain)
    try:
        token_data = oauth_service.refresh_access_token(refresh_token=refresh_token)
    except BambooHRIntegrationError as exc:
        raise BambooHRPayrollError(
            str(exc),
            code="BAMBOOHR_TOKEN_REFRESH_FAILED",
        ) from exc
    new_access_token = str(token_data.get("access_token") or "").strip()
    new_refresh_token = str(
        token_data.get("refresh_token") or refresh_token
    ).strip()

    if not new_access_token:
        raise BambooHRPayrollError(
            "BambooHR token refresh did not return an access token.",
            code="BAMBOOHR_TOKEN_REFRESH_FAILED",
        )

    config["access_token"] = new_access_token
    config["refresh_token"] = new_refresh_token
    if token_data.get("expires_in"):
        config["access_token_expires_at"] = (
            timezone.now()
            + timedelta(seconds=int(token_data["expires_in"]))
        ).isoformat()

    credential.encrypted_config = encrypt_integration_config(config)
    credential.save(update_fields=["encrypted_config", "updated_at"])

    refreshed_client = BambooHRClient(
        company_domain=company_domain,
        access_token=new_access_token,
    )
    try:
        return refreshed_client.get_employee(employee_id, fields=fields)
    except BambooHRIntegrationError as exc:
        raise BambooHRPayrollError(
            str(exc),
            code="BAMBOOHR_EMPLOYEE_VALIDATION_FAILED",
        ) from exc


def _optional_boolean(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _employee_display_name(report):
    name = report.employee.user.get_full_name().strip()
    return name or report.employee.user.email


@transaction.atomic
def create_payroll_batch(
    *,
    integration,
    actor_profile,
    payroll_period_start,
    payroll_period_end,
    pay_date,
    earning_code,
    notes="",
):
    if payroll_period_start > payroll_period_end:
        raise BambooHRPayrollError(
            "Payroll period start must be on or before payroll period end.",
            code="INVALID_PAYROLL_PERIOD",
        )

    batch = BambooHRPayrollBatch.objects.create(
        integration=integration,
        payroll_period_start=payroll_period_start,
        payroll_period_end=payroll_period_end,
        pay_date=pay_date,
        earning_code=str(earning_code or "EXPENSE_REIMBURSEMENT").strip(),
        notes=str(notes or "").strip(),
        created_by=actor_profile,
    )

    create_integration_audit_log(
        company=integration.company,
        integration=integration,
        provider="BAMBOOHR",
        action="BAMBOOHR_PAYROLL_BATCH_CREATED",
        action_by=actor_profile,
        message="BambooHR payroll reimbursement batch created.",
        metadata={
            "batch_id": str(batch.id),
            "pay_date": batch.pay_date.isoformat(),
        },
    )
    return batch


@transaction.atomic
def add_report_to_payroll_batch(*, batch_id, report_id, company):
    try:
        batch = (
            BambooHRPayrollBatch.objects
            .select_for_update()
            .select_related("integration")
            .get(id=batch_id, integration__company=company)
        )
    except BambooHRPayrollBatch.DoesNotExist as exc:
        raise BambooHRPayrollError(
            "BambooHR payroll batch was not found.",
            code="PAYROLL_BATCH_NOT_FOUND",
        ) from exc

    if batch.status != BambooHRPayrollBatch.STATUS_DRAFT:
        raise BambooHRPayrollError(
            "Reports can only be added to a DRAFT payroll batch.",
            code="PAYROLL_BATCH_NOT_DRAFT",
        )

    try:
        report = (
            ExpenseReport.objects
            .select_for_update()
            .select_related("employee", "employee__user", "company")
            .get(id=report_id, company=company)
        )
    except ExpenseReport.DoesNotExist as exc:
        raise BambooHRPayrollError(
            "Expense report was not found.",
            code="REPORT_NOT_FOUND",
        ) from exc

    if report.status != ExpenseReport.STATUS_APPROVED or not report.workflow_completed:
        raise BambooHRPayrollError(
            "Only fully approved reports can be added to payroll.",
            code="REPORT_NOT_APPROVED",
        )

    mapping = (
        IntegrationEmployeeMapping.objects
        .select_related("user_profile", "user_profile__user")
        .filter(
            integration=batch.integration,
            user_profile=report.employee,
        )
        .first()
    )
    if not mapping:
        raise BambooHRPayrollError(
            "The report employee is not mapped to a BambooHR employee.",
            code="BAMBOOHR_EMPLOYEE_MAPPING_MISSING",
        )

    live_employee = _fetch_bamboohr_payroll_employee(
        batch.integration,
        mapping.external_employee_id,
    )
    live_status = str(live_employee.get("status") or "").strip()
    include_in_payroll = _optional_boolean(
        live_employee.get("includeInPayroll")
    )

    if live_status.lower() == "inactive":
        raise BambooHRPayrollError(
            "The mapped BambooHR employee is inactive.",
            code="BAMBOOHR_EMPLOYEE_INACTIVE",
        )
    if include_in_payroll is False:
        raise BambooHRPayrollError(
            "The BambooHR employee is excluded from payroll.",
            code="BAMBOOHR_EMPLOYEE_EXCLUDED_FROM_PAYROLL",
        )

    for receipt in report.receipts.all():
        recalculate_receipt_from_line_items(receipt)
    recalculate_report_total(report)
    report.refresh_from_db()

    amount = Decimal(str(report.total_amount or "0"))
    if amount <= 0:
        raise BambooHRPayrollError(
            "The approved reimbursement amount must be greater than zero.",
            code="INVALID_REIMBURSEMENT_AMOUNT",
        )

    try:
        currency = get_report_company_currency(report)
    except Exception as exc:
        raise BambooHRPayrollError(
            str(exc),
            code="INVALID_REIMBURSEMENT_CURRENCY",
        ) from exc
    if not currency:
        raise BambooHRPayrollError(
            "Unable to determine the report reimbursement currency.",
            code="REIMBURSEMENT_CURRENCY_MISSING",
        )

    try:
        item = BambooHRPayrollBatchItem.objects.create(
            batch=batch,
            report=report,
            employee_mapping=mapping,
            external_employee_id=mapping.external_employee_id,
            employee_number=str(live_employee.get("employeeNumber") or "").strip(),
            external_email=str(
                live_employee.get("workEmail")
                or mapping.external_email
                or report.employee.user.email
                or ""
            ).strip(),
            employee_name=_employee_display_name(report),
            bamboohr_employee_status=live_status,
            include_in_payroll=include_in_payroll,
            amount=amount,
            currency=str(currency).strip().upper(),
            earning_code=batch.earning_code,
        )
    except IntegrityError as exc:
        raise BambooHRPayrollError(
            "This report is already present in an active payroll batch.",
            code="REPORT_ALREADY_IN_PAYROLL",
        ) from exc

    return item


@transaction.atomic
def remove_report_from_payroll_batch(*, batch_id, report_id, company):
    try:
        batch = (
            BambooHRPayrollBatch.objects
            .select_for_update()
            .get(id=batch_id, integration__company=company)
        )
    except BambooHRPayrollBatch.DoesNotExist as exc:
        raise BambooHRPayrollError(
            "BambooHR payroll batch was not found.",
            code="PAYROLL_BATCH_NOT_FOUND",
        ) from exc

    if batch.status != BambooHRPayrollBatch.STATUS_DRAFT:
        raise BambooHRPayrollError(
            "Reports can only be removed from a DRAFT payroll batch.",
            code="PAYROLL_BATCH_NOT_DRAFT",
        )

    item = (
        batch.items
        .select_for_update()
        .filter(report_id=report_id, status=BambooHRPayrollBatchItem.STATUS_PENDING)
        .first()
    )
    if not item:
        raise BambooHRPayrollError(
            "The report is not active in this payroll batch.",
            code="PAYROLL_ITEM_NOT_FOUND",
        )

    item.status = BambooHRPayrollBatchItem.STATUS_REMOVED
    item.removed_at = timezone.now()
    item.save(update_fields=["status", "removed_at", "updated_at"])
    return item


@transaction.atomic
def mark_payroll_batch_ready(*, batch_id, company):
    try:
        batch = (
            BambooHRPayrollBatch.objects
            .select_for_update()
            .get(id=batch_id, integration__company=company)
        )
    except BambooHRPayrollBatch.DoesNotExist as exc:
        raise BambooHRPayrollError(
            "BambooHR payroll batch was not found.",
            code="PAYROLL_BATCH_NOT_FOUND",
        ) from exc

    if batch.status != BambooHRPayrollBatch.STATUS_DRAFT:
        raise BambooHRPayrollError(
            "Only a DRAFT payroll batch can be marked READY.",
            code="INVALID_PAYROLL_BATCH_STATUS",
        )

    items = list(
        batch.items
        .select_related("report")
        .filter(status=BambooHRPayrollBatchItem.STATUS_PENDING)
    )
    if not items:
        raise BambooHRPayrollError(
            "Add at least one approved report before marking the batch ready.",
            code="PAYROLL_BATCH_EMPTY",
        )

    invalid_reports = [
        str(item.report_id)
        for item in items
        if (
            item.report.status != ExpenseReport.STATUS_APPROVED
            or not item.report.workflow_completed
        )
    ]
    if invalid_reports:
        raise BambooHRPayrollError(
            "Some reports are no longer approved: " + ", ".join(invalid_reports),
            code="PAYROLL_REPORTS_NO_LONGER_APPROVED",
        )

    batch.status = BambooHRPayrollBatch.STATUS_READY
    batch.save(update_fields=["status", "updated_at"])
    return batch


@transaction.atomic
def build_payroll_batch_csv(*, batch_id, company):
    try:
        batch = (
            BambooHRPayrollBatch.objects
            .select_for_update()
            .select_related("integration")
            .get(id=batch_id, integration__company=company)
        )
    except BambooHRPayrollBatch.DoesNotExist as exc:
        raise BambooHRPayrollError(
            "BambooHR payroll batch was not found.",
            code="PAYROLL_BATCH_NOT_FOUND",
        ) from exc

    if batch.status not in {
        BambooHRPayrollBatch.STATUS_READY,
        BambooHRPayrollBatch.STATUS_EXPORTED,
    }:
        raise BambooHRPayrollError(
            "The payroll batch must be READY before CSV export.",
            code="PAYROLL_BATCH_NOT_READY",
        )

    items = list(
        batch.items
        .filter(
            status__in=[
                BambooHRPayrollBatchItem.STATUS_PENDING,
                BambooHRPayrollBatchItem.STATUS_EXPORTED,
            ]
        )
        .order_by("employee_name", "report_id")
    )
    if not items:
        raise BambooHRPayrollError(
            "The payroll batch has no exportable reports.",
            code="PAYROLL_BATCH_EMPTY",
        )

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "BambooHR Employee ID",
            "Employee Number",
            "Employee Name",
            "Work Email",
            "Earning Code",
            "Reimbursement Amount",
            "Currency",
            "Pay Date",
            "Payroll Period Start",
            "Payroll Period End",
            "ZepEx Report ID",
            "ZepEx Batch ID",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.external_employee_id,
                item.employee_number,
                item.employee_name,
                item.external_email,
                item.earning_code,
                f"{item.amount:.2f}",
                item.currency,
                batch.pay_date.isoformat(),
                batch.payroll_period_start.isoformat(),
                batch.payroll_period_end.isoformat(),
                str(item.report_id),
                str(batch.id),
            ]
        )

    now = timezone.now()
    batch.status = BambooHRPayrollBatch.STATUS_EXPORTED
    batch.exported_at = now
    batch.save(update_fields=["status", "exported_at", "updated_at"])
    batch.items.filter(
        status=BambooHRPayrollBatchItem.STATUS_PENDING
    ).update(
        status=BambooHRPayrollBatchItem.STATUS_EXPORTED,
        exported_at=now,
    )

    return batch, output.getvalue()


@transaction.atomic
def confirm_payroll_batch(
    *,
    batch_id,
    company,
    actor_profile,
    payroll_run_reference,
    notes="",
):
    reference = str(payroll_run_reference or "").strip()
    if not reference:
        raise BambooHRPayrollError(
            "payroll_run_reference is required.",
            code="PAYROLL_RUN_REFERENCE_REQUIRED",
        )

    try:
        batch = (
            BambooHRPayrollBatch.objects
            .select_for_update()
            .select_related("integration")
            .get(id=batch_id, integration__company=company)
        )
    except BambooHRPayrollBatch.DoesNotExist as exc:
        raise BambooHRPayrollError(
            "BambooHR payroll batch was not found.",
            code="PAYROLL_BATCH_NOT_FOUND",
        ) from exc

    if batch.status != BambooHRPayrollBatch.STATUS_EXPORTED:
        raise BambooHRPayrollError(
            "Only an EXPORTED payroll batch can be confirmed.",
            code="PAYROLL_BATCH_NOT_EXPORTED",
        )

    items = list(
        batch.items
        .select_for_update()
        .select_related("report")
        .filter(status=BambooHRPayrollBatchItem.STATUS_EXPORTED)
    )
    if not items:
        raise BambooHRPayrollError(
            "The payroll batch has no exported reports.",
            code="PAYROLL_BATCH_EMPTY",
        )

    payment_results = []
    for item in items:
        try:
            result = mark_approved_report_paid(
                report_id=item.report_id,
                company=company,
                actor_profile=actor_profile,
                notes=(
                    str(notes or "").strip()
                    or f"Paid through BambooHR payroll batch {batch.id}."
                ),
                payment_source="BAMBOOHR_PAYROLL",
                payment_reference=reference,
            )
        except ExpensePaymentError as exc:
            raise BambooHRPayrollError(
                f"Report {item.report_id}: {exc}",
                code=exc.code,
            ) from exc

        item.status = BambooHRPayrollBatchItem.STATUS_CONFIRMED
        item.confirmed_at = timezone.now()
        item.error_message = None
        item.save(
            update_fields=[
                "status",
                "confirmed_at",
                "error_message",
                "updated_at",
            ]
        )
        payment_results.append(
            {
                "report_id": str(item.report_id),
                "amount": str(item.amount),
                "currency": item.currency,
                "quickbooks_export": result["quickbooks_export"],
            }
        )

    batch.status = BambooHRPayrollBatch.STATUS_CONFIRMED
    batch.confirmed_by = actor_profile
    batch.confirmed_at = timezone.now()
    batch.payroll_run_reference = reference
    batch.save(
        update_fields=[
            "status",
            "confirmed_by",
            "confirmed_at",
            "payroll_run_reference",
            "updated_at",
        ]
    )

    create_integration_audit_log(
        company=company,
        integration=batch.integration,
        provider="BAMBOOHR",
        action="BAMBOOHR_PAYROLL_BATCH_CONFIRMED",
        action_by=actor_profile,
        message="BambooHR payroll reimbursement batch confirmed as processed.",
        metadata={
            "batch_id": str(batch.id),
            "payroll_run_reference": reference,
            "report_count": len(payment_results),
        },
    )

    return batch, payment_results
