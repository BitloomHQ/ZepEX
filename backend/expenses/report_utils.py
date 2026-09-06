from datetime import date

from django.db import transaction
from django.db.models import Q

from .models import (
    ApprovalWorkflowStep,
    ExpenseReport,
)


@transaction.atomic
def get_or_create_current_month_report(profile):
    """
    Return the employee's report for the current month.

    The lookup uses only the fields covered by the report's
    unique constraint: company, employee and month.

    If the existing report is still DRAFT, its department and
    receipt departments are synchronized with the employee's
    current department.
    """

    current_month = date.today().replace(day=1)

    report, created = ExpenseReport.objects.get_or_create(
        company=profile.company,
        employee=profile,
        month=current_month,
        defaults={
            "department": profile.department,
            "status": ExpenseReport.STATUS_DRAFT,
        },
    )

    if (
        not created
        and report.status == ExpenseReport.STATUS_DRAFT
        and report.department_id != profile.department_id
    ):
        report.department = profile.department

        report.save(
            update_fields=[
                "department",
                "updated_at",
            ]
        )

        report.receipts.update(
            department=profile.department
        )

    return report


def _approver_department_ids(profile):
    ids = set(
        profile.managed_departments.values_list(
            "id",
            flat=True,
        )
    )

    if profile.department_id:
        ids.add(profile.department_id)

    return ids


def can_approve_report(
    profile,
    report,
    current_step,
):
    if profile.company_role != current_step.approver_role:
        return False

    dept_ids = _approver_department_ids(profile)

    if current_step.department_id:
        return current_step.department_id in dept_ids

    if (
        current_step.routing_type
        == ApprovalWorkflowStep.ROUTING_COMPANY
    ):
        return True

    if (
        current_step.routing_type
        == ApprovalWorkflowStep.ROUTING_DEPARTMENT
    ):
        return bool(
            report.department_id
            and report.department_id in dept_ids
        )

    return False


def get_pending_approval_reports_for(profile):
    """
    Return reports awaiting approval by the given
    approver profile.
    """

    dept_ids = _approver_department_ids(profile)

    routing = Q(
        current_workflow_step__department__isnull=True,
        current_workflow_step__routing_type=(
            ApprovalWorkflowStep.ROUTING_COMPANY
        ),
    )

    if dept_ids:
        routing |= Q(
            current_workflow_step__department_id__in=dept_ids
        )

        routing |= Q(
            current_workflow_step__department__isnull=True,
            current_workflow_step__routing_type=(
                ApprovalWorkflowStep.ROUTING_DEPARTMENT
            ),
            department_id__in=dept_ids,
        )

    return (
        ExpenseReport.objects
        .filter(
            company=profile.company,
            current_workflow_step__approver_role=(
                profile.company_role
            ),
            workflow_completed=False,
            status=ExpenseReport.STATUS_SUBMITTED,
        )
        .filter(routing)
        .select_related(
            "employee",
            "employee__user",
            "department",
            "current_workflow_step",
            "current_workflow_step__approver_role",
            "current_workflow_step__department",
        )
        .prefetch_related(
            "receipts",
            "receipts__line_items",
        )
        .distinct()
        .order_by("-submitted_at")
    )


def is_payment_queue_role(company_role):
    """
    Return whether the role handles payment rather
    than workflow approval.
    """

    if not company_role:
        return False

    return (
        company_role.can_mark_paid
        and not company_role.can_approve_expense
    )


def get_reports_awaiting_payment(company):
    """
    Return reports visible to the Accounts/payment team.

    Includes:
    1. Fully approved reports.
    2. Rejected reports for final Accounts handling.
    3. Reports currently on a payment workflow step.
    """

    payment_step = Q(
        status=ExpenseReport.STATUS_SUBMITTED,
        workflow_completed=False,
        current_workflow_step__approver_role__can_mark_paid=True,
    )

    return (
        ExpenseReport.objects
        .filter(company=company)
        .filter(
            Q(
                status=ExpenseReport.STATUS_APPROVED,
                workflow_completed=True,
            )
            | Q(
                status=ExpenseReport.STATUS_REJECTED,
                workflow_completed=True,
            )
            | payment_step
        )
        .select_related(
            "employee",
            "employee__user",
            "department",
            "current_workflow_step",
            "current_workflow_step__approver_role",
            "current_approver",
            "current_approver__user",
        )
        .prefetch_related(
            "receipts",
            "receipts__line_items",
            "approval_history",
        )
        .distinct()
        .order_by("-updated_at")
    )