import logging
from functools import partial

from django.db import transaction
from django.utils import timezone

from audit_logs.utils import create_audit_log
from integrations.models import CompanyIntegration

from .email_notifications import send_workflow_status_email
from tenants.models import UserProfile

from .models import ApprovalHistory, ExpenseReceipt, ExpenseReport
from .notification_services import notify_report_paid
from .report_utils import get_reports_awaiting_payment
from .services import recalculate_receipt_from_line_items, recalculate_report_total


logger = logging.getLogger(__name__)


class ExpensePaymentError(Exception):
    """Expected validation error while completing a reimbursement payment."""

    def __init__(self, message, *, code="PAYMENT_VALIDATION_FAILED"):
        super().__init__(message)
        self.code = code


def _send_paid_notifications(*, report_id, actor_profile_id, notes):
    """Run external notifications after the database transaction commits."""

    try:
        report = (
            ExpenseReport.objects
            .select_related("employee", "employee__user")
            .get(id=report_id)
        )
        actor_profile = UserProfile.objects.get(id=actor_profile_id)

        notify_report_paid(
            recipient=report.employee,
            report=report,
        )

        send_workflow_status_email(
            report=report,
            subject="Reimbursement Payment Completed",
            message=(
                "Your reimbursement report has been processed by Accounts "
                "and marked as paid."
            ),
            action="PAID",
            action_by=actor_profile,
            current_step=None,
            notes=notes or "Payment completed successfully.",
            notify_previous_approvers=True,
        )
    except Exception:
        logger.exception(
            "Unable to send paid-report notifications. report=%s",
            report_id,
        )


def _queue_quickbooks_export(*, report_id, company_id):
    from integrations.tasks import export_report_to_quickbooks_task

    export_report_to_quickbooks_task.delay(
        str(report_id),
        str(company_id),
    )


@transaction.atomic
def mark_approved_report_paid(
    *,
    report_id,
    company,
    actor_profile,
    notes="",
    payment_source="MANUAL",
    payment_reference="",
):
    """
    Complete one approved reimbursement using the canonical ZepEx payment flow.

    Both the Accounts endpoint and BambooHR payroll confirmation should call
    this function. External notifications and QuickBooks export are queued only
    after the transaction commits.
    """

    if not actor_profile or actor_profile.company_id != company.id:
        raise ExpensePaymentError(
            "The payment actor does not belong to this company.",
            code="INVALID_PAYMENT_ACTOR",
        )

    is_eligible = (
        get_reports_awaiting_payment(company)
        .filter(id=report_id)
        .exists()
    )
    if not is_eligible:
        raise ExpensePaymentError(
            "Report was not found in the Accounts payment queue.",
            code="REPORT_NOT_IN_PAYMENT_QUEUE",
        )

    try:
        report = (
            ExpenseReport.objects
            .select_for_update()
            .select_related("employee", "employee__user", "department")
            .get(id=report_id, company=company)
        )
    except ExpenseReport.DoesNotExist as exc:
        raise ExpensePaymentError(
            "Expense report was not found.",
            code="REPORT_NOT_FOUND",
        ) from exc

    if report.status != ExpenseReport.STATUS_APPROVED:
        raise ExpensePaymentError(
            "Only approved expense reports can be marked as paid.",
            code="REPORT_NOT_APPROVED",
        )

    if not report.workflow_completed:
        raise ExpensePaymentError(
            "The report has not completed its approval workflow.",
            code="WORKFLOW_NOT_COMPLETED",
        )

    for receipt in report.receipts.all():
        recalculate_receipt_from_line_items(receipt)

    recalculate_report_total(report)
    report.refresh_from_db()

    normalized_notes = str(notes or "").strip()
    source = str(payment_source or "MANUAL").strip().upper()
    reference = str(payment_reference or "").strip()
    previous_status = report.status

    report.status = ExpenseReport.STATUS_PAID
    report.paid_notes = normalized_notes
    report.paid_at = timezone.now()
    report.workflow_completed = True
    report.current_workflow_step = None
    report.current_approver = None
    report.save(
        update_fields=[
            "status",
            "paid_notes",
            "paid_at",
            "workflow_completed",
            "current_workflow_step",
            "current_approver",
            "updated_at",
        ]
    )

    report.receipts.filter(
        status=ExpenseReceipt.STATUS_APPROVED,
    ).update(status=ExpenseReceipt.STATUS_PAID)

    ApprovalHistory.objects.create(
        report=report,
        action_by=actor_profile,
        action=ApprovalHistory.ACTION_PAID,
        comments=normalized_notes,
    )

    is_company_admin = actor_profile.role == "COMPANY_ADMIN"
    actor_role = (
        "COMPANY_ADMIN"
        if is_company_admin
        else actor_profile.company_role.name
    )

    create_audit_log(
        company=company,
        action="MARKED_PAID",
        action_by=actor_profile,
        message=(
            f"{actor_role} marked expense report {report.id} as paid "
            f"using {source}."
        ),
        metadata={
            "report_id": str(report.id),
            "employee_email": report.employee.user.email,
            "department": report.department.name if report.department else None,
            "total_amount": str(report.total_amount),
            "previous_status": previous_status,
            "paid_by": actor_profile.user.email,
            "paid_by_role": actor_role,
            "is_company_admin_override": is_company_admin,
            "notes": normalized_notes,
            "payment_source": source,
            "payment_reference": reference or None,
        },
    )

    quickbooks_integration = (
        CompanyIntegration.objects
        .filter(
            company=company,
            provider=CompanyIntegration.PROVIDER_QUICKBOOKS,
            is_connected=True,
            is_active=True,
            quickbooks_auto_export=True,
        )
        .first()
    )

    transaction.on_commit(
        partial(
            _send_paid_notifications,
            report_id=report.id,
            actor_profile_id=actor_profile.id,
            notes=normalized_notes,
        )
    )

    if quickbooks_integration:
        transaction.on_commit(
            partial(
                _queue_quickbooks_export,
                report_id=report.id,
                company_id=company.id,
            )
        )

    return {
        "report": report,
        "previous_status": previous_status,
        "paid_by": actor_role,
        "quickbooks_auto_export_enabled": bool(quickbooks_integration),
        "quickbooks_export": (
            "QUEUED_AFTER_COMMIT"
            if quickbooks_integration
            else "NOT_QUEUED"
        ),
    }
