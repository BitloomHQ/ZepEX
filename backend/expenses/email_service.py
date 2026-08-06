from tenants.models import Company, UserProfile

from .models import (
    ExpenseReport,
    ExpenseSubmission,
    ExpenseReceipt,
)
from .report_utils import get_or_create_current_month_report
from .ai_processor import process_receipt

from .audit_services import create_audit_log
from .models import ExpenseAuditTrail


ALLOWED_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"]


def ingest_forwarded_receipt_email(
    *,
    sender_email,
    original_recipient,
    subject="",
    uploaded_file=None,
):
    """
    Creates an ExpenseSubmission and ExpenseReceipt from an
    forwarded reimbursement email and immediately sends the
    receipt through the AI pipeline.
    """

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    if not sender_email:
        return {
            "success": False,
            "error": "sender_email is required."
        }

    if not original_recipient:
        return {
            "success": False,
            "error": "original_recipient is required."
        }

    if not uploaded_file:
        return {
            "success": False,
            "error": "Receipt attachment is required."
        }

    extension = uploaded_file.name.split(".")[-1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        return {
            "success": False,
            "error": "Only PDF, JPG, JPEG and PNG files are allowed."
        }

    # ---------------------------------------------------------
    # Find Company
    # ---------------------------------------------------------

    try:
        company = Company.objects.get(
            reimbursement_email__iexact=original_recipient,
            is_active=True,
            is_verified=True,
        )

    except Company.DoesNotExist:
        return {
            "success": False,
            "error": (
                "No verified company found for this reimbursement email."
            ),
        }

    # ---------------------------------------------------------
    # Find Employee
    # ---------------------------------------------------------

    try:
        employee = (
            UserProfile.objects
            .select_related(
                "user",
                "company",
                "department",
                "company_role",
            )
            .get(
                company=company,
                user__email__iexact=sender_email,
                user__is_active=True,
            )
        )

    except UserProfile.DoesNotExist:
        return {
            "success": False,
            "error": (
                "Sender is not a registered employee for this company."
            ),
        }

    # ---------------------------------------------------------
    # Permission Checks
    # ---------------------------------------------------------

    if not employee.company_role:
        return {
            "success": False,
            "error": "Company role is not assigned."
        }

    if not employee.company_role.can_upload_receipt:
        return {
            "success": False,
            "error": (
                "Employee is not allowed to upload receipts."
            ),
        }

    if not employee.department:
        return {
            "success": False,
            "error": "Department is not assigned."
        }

    # ---------------------------------------------------------
    # Get Current Month Report
    # ---------------------------------------------------------

    report = get_or_create_current_month_report(employee)

    if report.status != ExpenseReport.STATUS_DRAFT:
        return {
            "success": False,
            "error": (
                "Current month's report has already been submitted."
            ),
        }

    # ---------------------------------------------------------
    # Create Submission
    # ---------------------------------------------------------

    submission = ExpenseSubmission.objects.create(
        report=report,
        company=company,
        employee=employee,
        source=ExpenseSubmission.SOURCE_EMAIL,
        email_subject=subject,
    )

    # ---------------------------------------------------------
    # Create Receipt
    # ---------------------------------------------------------

    receipt = ExpenseReceipt.objects.create(
    report=report,
    submission=submission,
    company=company,
    employee=employee,
    department=employee.department,
    receipt_file=uploaded_file,
    status=ExpenseReceipt.STATUS_AI_PROCESSING,
    ai_status=ExpenseReceipt.AI_PROCESSING,
    ai_error_message=None,
    ai_retry_count=0,
)

    create_audit_log(
    company=company,
    action="RECEIPT_UPLOADED",
    action_by=employee,
    message="Receipt received via email.",
    metadata={
        "receipt_id": str(receipt.id),
        "report_id": str(report.id),
        "submission_id": str(submission.id),
        "filename": receipt.receipt_file.name,
        "source": ExpenseSubmission.SOURCE_EMAIL,
        "department": employee.department.name if employee.department else None,
    },
)
    create_audit_log(
    company=company,
    action="AI_PROCESSING_STARTED",
    action_by=employee,
    message="AI extraction started for emailed receipt.",
    metadata={
        "receipt_id": str(receipt.id),
        "report_id": str(report.id),
        "submission_id": str(submission.id),
    },
)
    # ---------------------------------------------------------
    # Start AI Processing
    # ---------------------------------------------------------

    try:
        ai_result = process_receipt(receipt.id)
    except Exception as e:
        ai_result = {
            "success": False,
            "error": str(e),
        }

    receipt.refresh_from_db()

    return {
    "success": True,
    "company": company,
    "employee": employee,
    "report": report,
    "submission": submission,
    "receipt": receipt,
    "ai_result": ai_result,
}