from django.db import transaction
from django.utils import timezone

from .services import recalculate_receipt_from_line_items, recalculate_report_total
from tenants.models import UserProfile
from expenses.models import (
    ApprovalWorkflow,
    ApprovalWorkflowStep,
    ApprovalHistory,
    ExpenseReport,
    ExpenseReceipt,
)


def get_workflow(employee):
    try:
        return ApprovalWorkflow.objects.get(
            company=employee.company,
            start_role=employee.company_role,
            is_active=True,
        )
    except ApprovalWorkflow.DoesNotExist:
        return None


def get_first_step(workflow):
    return workflow.steps.filter(
        is_active=True
    ).select_related(
        "approver_role",
        "department",
        "specific_user",
        "specific_user__user",
    ).order_by("step_order").first()


def get_next_step(current_step):
    return ApprovalWorkflowStep.objects.filter(
        workflow=current_step.workflow,
        is_active=True,
        step_order__gt=current_step.step_order,
    ).select_related(
        "approver_role",
        "department",
        "specific_user",
        "specific_user__user",
    ).order_by("step_order").first()

def get_next_valid_step(
    employee,
    workflow,
    current_step,
    previous_approver,
):
    """
    Finds the next valid workflow step.

    Automatically skips:
    - Missing approver
    - Inactive approver
    - Duplicate approver (same person approving twice)
    """

    steps_skipped = 0

    remaining_steps = workflow.steps.filter(
        is_active=True,
        step_order__gt=current_step.step_order
    ).order_by("step_order")

    for step in remaining_steps:

        approver, error = resolve_step_approver(
            employee=employee,
            workflow_step=step,
        )

        # -----------------------------------
        # Skip if approver cannot be resolved
        # -----------------------------------
        if error or approver is None:
            steps_skipped += 1
            continue

        # -----------------------------------
        # Skip inactive users
        # -----------------------------------
        if not approver.user.is_active:
            steps_skipped += 1
            continue

        # -----------------------------------
        # Skip duplicate approver
        # -----------------------------------
        if (
            previous_approver
            and approver.id == previous_approver.id
        ):
            steps_skipped += 1
            continue

        return (
            step,
            approver,
            steps_skipped,
        )

    return (
        None,
        None,
        steps_skipped,
    )


def resolve_step_approver(employee, workflow_step):

    if workflow_step.approver_type == ApprovalWorkflowStep.APPROVER_REPORTING_MANAGER:

        if not employee.reporting_manager:
            return None, "Reporting manager is not assigned."

        return employee.reporting_manager, None

    if workflow_step.approver_type == ApprovalWorkflowStep.APPROVER_DEPARTMENT_MANAGER:

        target_department = workflow_step.department or employee.department

        if not target_department:
            return None, "Employee department is not assigned."

        if not target_department.manager:
            return None, "Department manager is not assigned."

        return target_department.manager, None

    if workflow_step.approver_type == ApprovalWorkflowStep.APPROVER_SPECIFIC_USER:

        if not workflow_step.specific_user:
            return None, "Specific approver is not configured."

        if not workflow_step.specific_user.user.is_active:
            return None, "Specific approver is inactive."

        return workflow_step.specific_user, None

    if workflow_step.approver_type == ApprovalWorkflowStep.APPROVER_COMPANY_ROLE:

        if not workflow_step.approver_role:
            return None, "Approver role is not configured."

        approver_query = UserProfile.objects.filter(
            company=employee.company,
            company_role=workflow_step.approver_role,
            user__is_active=True,
        ).exclude(
            id=employee.id
        ).select_related(
            "user",
            "department",
            "company_role",
        )

        if workflow_step.routing_type == ApprovalWorkflowStep.ROUTING_DEPARTMENT:
            target_department = workflow_step.department or employee.department

            if not target_department:
                return None, "Employee department is not assigned."

            approver_query = approver_query.filter(
                department=target_department
            )

        approver = approver_query.first()

        if not approver:
            return (
                None,
                f"No active user found with role '{workflow_step.approver_role.name}'."
            )

        return approver, None

    return None, "Invalid approver type."


def can_user_approve_step(user_profile, report, workflow_step):
    if user_profile.role == "COMPANY_ADMIN":
        return True, None

    if report.current_approver_id and report.current_approver_id != user_profile.id:
        return False, "You are not the current approver for this report."

    approver_type = workflow_step.approver_type

    if approver_type == ApprovalWorkflowStep.APPROVER_REPORTING_MANAGER:
        manager = report.employee.reporting_manager
        if not manager:
            return False, "Employee does not have a reporting manager."
        if manager.id != user_profile.id:
            return False, "Only the reporting manager can approve."
        return True, None

    if approver_type == ApprovalWorkflowStep.APPROVER_DEPARTMENT_MANAGER:
        department = report.department
        if not department:
            return False, "Report has no department."
        if not department.manager:
            return False, "Department manager is not configured."
        if department.manager.id != user_profile.id:
            return False, "Only the department manager can approve."
        return True, None

    if approver_type == ApprovalWorkflowStep.APPROVER_COMPANY_ROLE:
        if user_profile.company_role != workflow_step.approver_role:
            return False, "Current role cannot approve this workflow step."
        return True, None

    if approver_type == ApprovalWorkflowStep.APPROVER_SPECIFIC_USER:
        if not workflow_step.specific_user:
            return False, "Specific approver is not configured."
        if workflow_step.specific_user.id != user_profile.id:
            return False, "Only the configured user can approve."
        return True, None

    return False, "Unknown workflow approver type."


def start_workflow(report):
    employee = report.employee

    workflow = get_workflow(employee)

    if workflow is None:
        return False, f"No workflow configured for '{employee.company_role.name}'."

    first_step = get_first_step(workflow)

    if first_step is None:
        return False, "Workflow has no active steps."

    approver, error = resolve_step_approver(
        employee=employee,
        workflow_step=first_step,
    )

    if error:
        return False, error

    report.status = ExpenseReport.STATUS_SUBMITTED
    report.current_workflow_step = first_step
    report.current_approver = approver
    report.workflow_completed = False
    report.submitted_at = timezone.now()

    report.save(update_fields=[
        "status",
        "current_workflow_step",
        "current_approver",
        "workflow_completed",
        "submitted_at",
        "updated_at",
    ])

    report.receipts.all().update(
        status=ExpenseReceipt.STATUS_PENDING_APPROVAL
    )

    ApprovalHistory.objects.create(
        report=report,
        action_by=employee,
        action=ApprovalHistory.ACTION_REPORT_SUBMITTED,
        comments=(
            f"Workflow started. Current approver: "
            f"{approver.user.get_full_name() or approver.user.email}"
        )
    )

    return True, {
        "workflow": workflow,
        "step": first_step,
        "approver": approver,
    }


def approve_current_step(report, approver_profile, notes=""):

    current_step = report.current_workflow_step

    if not current_step:
        return False, "Current workflow step not found."

    allowed, error = can_user_approve_step(
        approver_profile,
        report,
        current_step,
    )

    if not allowed:
        return False, error

    ApprovalHistory.objects.create(
        report=report,
        action_by=approver_profile,
        action=ApprovalHistory.ACTION_STEP_APPROVED,
        comments=notes,
    )

    next_step, next_approver, skipped = get_next_valid_step(
        employee=report.employee,
        workflow=current_step.workflow,
        current_step=current_step,
        previous_approver=approver_profile,
    )

    # ----------------------------------
    # No more valid approvers
    # ----------------------------------

    if next_step is None:
        success, result = complete_workflow(
            report,
            approver_profile,
        )

        if success:
            result["steps_skipped"] = skipped

        return success, result

    # ----------------------------------
    # Move to next valid approver
    # ----------------------------------

    report.current_workflow_step = next_step
    report.current_approver = next_approver
    report.status = ExpenseReport.STATUS_SUBMITTED
    report.workflow_completed = False

    report.save(update_fields=[
        "current_workflow_step",
        "current_approver",
        "status",
        "workflow_completed",
        "updated_at",
    ])

    report.receipts.all().update(
        status=ExpenseReceipt.STATUS_PENDING_APPROVAL
    )

    return True, {
        "completed": False,
        "current_step": current_step,
        "next_step": next_step,
        "next_approver": next_approver,
        "steps_skipped": skipped,
    }


from django.db import transaction


@transaction.atomic
def complete_workflow(report, approver_profile):
    # --------------------------------------------------
    # 1. Recalculate all receipt totals
    # --------------------------------------------------
    #
    # This ensures removed/restored line items are reflected
    # in the final reimbursement amount.
    #
    for receipt in report.receipts.all():
        recalculate_receipt_from_line_items(receipt)

    # --------------------------------------------------
    # 2. Recalculate final monthly report total
    # --------------------------------------------------

    recalculate_report_total(report)
    report.refresh_from_db()

    # --------------------------------------------------
    # 3. Complete workflow
    # --------------------------------------------------

    report.workflow_completed = True
    report.status = ExpenseReport.STATUS_APPROVED
    report.current_workflow_step = None
    report.current_approver = None

    report.save(
        update_fields=[
            "workflow_completed",
            "status",
            "current_workflow_step",
            "current_approver",
            "updated_at",
        ]
    )

    # --------------------------------------------------
    # 4. Approve only receipts that were not rejected
    # --------------------------------------------------
    #
    # IMPORTANT:
    # A receipt that the approver explicitly rejected
    # must remain REJECTED.
    #
    report.receipts.exclude(
        status=ExpenseReceipt.STATUS_REJECTED
    ).update(
        status=ExpenseReceipt.STATUS_APPROVED
    )

    # --------------------------------------------------
    # 5. Record workflow completion in ApprovalHistory
    # --------------------------------------------------

    ApprovalHistory.objects.create(
        report=report,
        action_by=approver_profile,
        action=ApprovalHistory.ACTION_STEP_APPROVED,
        comments="Final approval workflow step completed.",
    )

    return True, {
        "completed": True,
        "approved_by": approver_profile,
    }

def reject_current_step(report, approver_profile, notes):
    current_step = report.current_workflow_step

    if not current_step:
        return False, "Current workflow step not found."

    allowed, error = can_user_approve_step(
        approver_profile,
        report,
        current_step,
    )

    if not allowed:
        return False, error

    report.status = ExpenseReport.STATUS_REJECTED
    report.current_workflow_step = None
    report.current_approver = None
    report.workflow_completed = True

    report.save(update_fields=[
        "status",
        "current_workflow_step",
        "current_approver",
        "workflow_completed",
        "updated_at",
    ])

    report.receipts.all().update(
        status=ExpenseReceipt.STATUS_REJECTED
    )

    ApprovalHistory.objects.create(
        report=report,
        action_by=approver_profile,
        action=ApprovalHistory.ACTION_STEP_REJECTED,
        comments=notes,
    )

    return True, {
        "rejected": True,
        "step": current_step,
    }

def simulate_workflow(employee):
    """
    Simulates the approval workflow without creating
    or modifying any ExpenseReport.
    """

    workflow = get_workflow(employee)

    if workflow is None:
        return False, "No workflow configured."

    current_step = get_first_step(workflow)

    if current_step is None:
        return False, "Workflow has no active steps."

    previous_approver = None
    skipped_steps = 0

    flow = []

    while current_step:

        approver, error = resolve_step_approver(
            employee=employee,
            workflow_step=current_step,
        )

        if error or approver is None:

            flow.append({
                "step_order": current_step.step_order,
                "status": "SKIPPED",
                "reason": error,
            })

            skipped_steps += 1

        elif previous_approver and approver.id == previous_approver.id:

            flow.append({
                "step_order": current_step.step_order,
                "status": "SKIPPED",
                "reason": "Duplicate approver skipped.",
            })

            skipped_steps += 1

        elif not approver.user.is_active:

            flow.append({
                "step_order": current_step.step_order,
                "status": "SKIPPED",
                "reason": "Inactive approver.",
            })

            skipped_steps += 1

        else:

            flow.append({
                "step_order": current_step.step_order,
                "status": "APPROVAL",

                "approver_type":
                    current_step.get_approver_type_display(),

                "approver": (
                    approver.user.get_full_name()
                    or approver.user.email
                ),

                "email": approver.user.email,
            })

            previous_approver = approver

        current_step = get_next_step(current_step)

    return True, {
        "workflow_name": workflow.name,
        "start_role": workflow.start_role.name,
        "total_steps": workflow.steps.filter(
            is_active=True
        ).count(),
        "steps_skipped": skipped_steps,
        "flow": flow,
    }

def reorder_workflow_steps(workflow):
    active_steps = list(
        ApprovalWorkflowStep.objects.filter(
            workflow=workflow,
            is_active=True,
        ).order_by(
            "step_order",
            "created_at",
        )
    )

    # Temporary numbering to avoid unique constraint conflict
    for index, step in enumerate(active_steps, start=1):
        step.step_order = index + 1000
        step.save(update_fields=["step_order"])

    # Final numbering
    for index, step in enumerate(active_steps, start=1):
        step.step_order = index
        step.save(update_fields=["step_order"])

    return active_steps    


from django.db import transaction
from django.utils import timezone


@transaction.atomic
def approve_receipt(
    *,
    report,
    receipt,
    approver_profile,
    notes="",
):
    current_step = report.current_workflow_step

    if not current_step:
        return False, "Current workflow step not found."

    if receipt.report_id != report.id:
        return False, "Receipt does not belong to this report."

    allowed, error = can_user_approve_step(
        approver_profile,
        report,
        current_step,
    )

    if not allowed:
        return False, error

    if receipt.status == ExpenseReceipt.STATUS_REJECTED:
        return False, "This receipt has already been rejected."

    receipt.status = ExpenseReceipt.STATUS_APPROVED

    receipt.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    ApprovalHistory.objects.create(
        report=report,
        receipt=receipt,
        action_by=approver_profile,
        action=ApprovalHistory.ACTION_RECEIPT_APPROVED,
        comments=notes.strip() if notes else "",
    )

    return True, {
        "receipt": receipt,
        "approved": True,
    }


@transaction.atomic
def reject_receipt(
    *,
    report,
    receipt,
    approver_profile,
    notes,
):
    current_step = report.current_workflow_step

    if not current_step:
        return False, "Current workflow step not found."

    if receipt.report_id != report.id:
        return False, "Receipt does not belong to this report."

    allowed, error = can_user_approve_step(
        approver_profile,
        report,
        current_step,
    )

    if not allowed:
        return False, error

    if not notes or not notes.strip():
        return False, "Rejection reason is required."

    receipt.status = ExpenseReceipt.STATUS_REJECTED

    receipt.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    ApprovalHistory.objects.create(
        report=report,
        receipt=receipt,
        action_by=approver_profile,
        action=ApprovalHistory.ACTION_RECEIPT_REJECTED,
        comments=notes.strip(),
    )

    return True, {
        "receipt": receipt,
        "rejected": True,
        "reason": notes.strip(),
    }


@transaction.atomic
def remove_receipt_line_item(
    *,
    report,
    line_item,
    approver_profile,
    reason,
):
    current_step = report.current_workflow_step

    if not current_step:
        return False, "Current workflow step not found."

    if line_item.receipt.report_id != report.id:
        return False, "Line item does not belong to this report."

    allowed, error = can_user_approve_step(
        approver_profile,
        report,
        current_step,
    )

    if not allowed:
        return False, error

    if not reason or not reason.strip():
        return False, "Removal reason is required."

    if line_item.is_removed:
        return False, "This line item has already been removed."

    line_item.is_removed = True
    line_item.removed_by = approver_profile
    line_item.removed_at = timezone.now()
    line_item.removal_reason = reason.strip()

    line_item.save(
        update_fields=[
            "is_removed",
            "removed_by",
            "removed_at",
            "removal_reason",
        ]
    )

    receipt = line_item.receipt

    recalculate_receipt_from_line_items(receipt)

    if report:
        recalculate_report_total(report)

    ApprovalHistory.objects.create(
        report=report,
        receipt=receipt,
        line_item=line_item,
        action_by=approver_profile,
        action=ApprovalHistory.ACTION_LINE_ITEM_REMOVED,
        comments=reason.strip(),
    )

    return True, {
        "line_item": line_item,
        "receipt": receipt,
        "removed": True,
    }


@transaction.atomic
def restore_receipt_line_item(
    *,
    report,
    line_item,
    approver_profile,
    notes="",
):
    current_step = report.current_workflow_step

    if not current_step:
        return False, "Current workflow step not found."

    if line_item.receipt.report_id != report.id:
        return False, "Line item does not belong to this report."

    allowed, error = can_user_approve_step(
        approver_profile,
        report,
        current_step,
    )

    if not allowed:
        return False, error

    if not line_item.is_removed:
        return False, "This line item is not removed."

    line_item.is_removed = False
    line_item.removed_by = None
    line_item.removed_at = None
    line_item.removal_reason = ""

    line_item.save(
        update_fields=[
            "is_removed",
            "removed_by",
            "removed_at",
            "removal_reason",
        ]
    )

    receipt = line_item.receipt

    recalculate_receipt_from_line_items(receipt)

    if report:
        recalculate_report_total(report)

    ApprovalHistory.objects.create(
        report=report,
        receipt=receipt,
        line_item=line_item,
        action_by=approver_profile,
        action=ApprovalHistory.ACTION_LINE_ITEM_RESTORED,
        comments=notes.strip() if notes else "",
    )

    return True, {
        "line_item": line_item,
        "receipt": receipt,
        "restored": True,
    }