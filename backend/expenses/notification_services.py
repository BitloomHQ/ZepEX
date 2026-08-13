from .models import Notification


def create_notification(
    *,
    recipient,
    company,
    title,
    message,
    notification_type,
    report=None,
    receipt=None,
):
    """
    Create an in-app notification for a UserProfile.

    recipient:
        tenants.UserProfile instance

    company:
        tenants.Company instance

    report:
        Optional ExpenseReport instance

    receipt:
        Optional ExpenseReceipt instance
    """

    if not recipient:
        return None

    return Notification.objects.create(
        recipient=recipient,
        company=company,
        report=report,
        receipt=receipt,
        notification_type=notification_type,
        title=title,
        message=message,
    )


# ==========================================================
# REPORT APPROVED
# ==========================================================

def notify_report_approved(
    *,
    recipient,
    report,
    approver_name,
):
    return create_notification(
        recipient=recipient,
        company=report.company,
        report=report,
        notification_type=Notification.TYPE_APPROVAL,
        title="Expense Report Approved",
        message=(
            f"Your expense report #{report.id} "
            f"has been approved by {approver_name}."
        ),
    )


# ==========================================================
# REPORT REJECTED
# ==========================================================

def notify_report_rejected(
    *,
    recipient,
    report,
    approver_name,
    reason,
):
    """
    Notify the employee when their expense report
    is rejected.
    """

    reason = (reason or "").strip()

    if not reason:
        reason = "No rejection reason was provided."

    return create_notification(
        recipient=recipient,
        company=report.company,
        report=report,
        notification_type=Notification.TYPE_REJECTION,
        title="Expense Report Rejected",
        message=(
            f"Your expense report #{report.id} "
            f"has been rejected by {approver_name}. "
            f"Reason: {reason}"
        ),
    )


# ==========================================================
# NEXT APPROVER
# ==========================================================

def notify_next_approver(
    *,
    recipient,
    report,
    employee_name,
):
    """
    Notify the next approver that an expense report
    is waiting for their approval.
    """

    return create_notification(
        recipient=recipient,
        company=report.company,
        report=report,
        notification_type=Notification.TYPE_WORKFLOW,
        title="Expense Report Awaiting Your Approval",
        message=(
            f"Expense report #{report.id} submitted by "
            f"{employee_name} is waiting for your approval."
        ),
    )


# ==========================================================
# REPORT PAID
# ==========================================================

def notify_report_paid(
    *,
    recipient,
    report,
):
    """
    Notify the employee that their reimbursement
    has been paid.
    """

    return create_notification(
        recipient=recipient,
        company=report.company,
        report=report,
        notification_type=Notification.TYPE_PAYMENT,
        title="Reimbursement Paid",
        message=(
            f"Your expense report #{report.id} "
            "has been marked as paid."
        ),
    )