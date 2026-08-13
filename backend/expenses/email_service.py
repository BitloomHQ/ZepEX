from tenants.models import UserProfile

from audit_logs.utils import create_audit_log

from .models import (
    ExpenseReport,
    ExpenseSubmission,
    ExpenseReceipt,
)
from .report_utils import get_or_create_current_month_report


ALLOWED_EXTENSIONS = [
    "pdf",
    "jpg",
    "jpeg",
    "png",
]


def ingest_receipt_email(
    *,
    company,
    sender_email,
    subject="",
    uploaded_file=None,
):
    """
    Process a receipt received directly in a company's
    reimbursement mailbox.

    Flow:

        Company IMAP mailbox
                ↓
        EmailFetcher(company)
                ↓
        process_parsed_email()
                ↓
        ingest_receipt_email()
                ↓
        Validate sender belongs to company
                ↓
        Create ExpenseSubmission
                ↓
        Create ExpenseReceipt
                ↓
        email_processor.py queues AI processing

    The company is determined from the mailbox being polled.
    """

    # =========================================================
    # 1. BASIC VALIDATION
    # =========================================================

    if not company:
        return {
            "success": False,
            "error": "Company is required.",
        }

    if not sender_email:
        return {
            "success": False,
            "error": "Sender email is required.",
        }

    if not uploaded_file:
        return {
            "success": False,
            "error": "Receipt attachment is required.",
        }

    sender_email = (
        sender_email
        .strip()
        .lower()
    )

    subject = (
        subject or ""
    ).strip()

    # =========================================================
    # 2. COMPANY VALIDATION
    # =========================================================

    if not company.is_active:
        return {
            "success": False,
            "error": "Company is inactive.",
        }

    if not company.is_verified:
        return {
            "success": False,
            "error": "Company is not verified.",
        }

    if not company.reimbursement_email:
        return {
            "success": False,
            "error": (
                "Company reimbursement email "
                "is not configured."
            ),
        }

    # =========================================================
    # 3. VALIDATE ATTACHMENT
    # =========================================================

    filename = (
        uploaded_file.name or ""
    ).strip()

    if "." not in filename:
        return {
            "success": False,
            "error": (
                "Receipt file must have "
                "a valid extension."
            ),
        }

    extension = (
        filename
        .rsplit(".", 1)[-1]
        .lower()
    )

    if extension not in ALLOWED_EXTENSIONS:
        return {
            "success": False,
            "error": (
                "Only PDF, JPG, JPEG and PNG "
                "files are allowed."
            ),
        }

    # =========================================================
    # 4. FIND EMPLOYEE INSIDE THIS COMPANY
    # =========================================================
    #
    # This is the multi-tenant security check.
    #
    # Company A mailbox:
    #
    #   Company A employee -> accepted
    #   Company B employee -> rejected
    #
    # =========================================================

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
                "Sender is not a registered "
                "active employee of this company."
            ),
        }

    # =========================================================
    # 5. EXTRA COMPANY SAFETY CHECK
    # =========================================================

    if employee.company_id != company.id:
        return {
            "success": False,
            "error": (
                "Sender does not belong to the company "
                "associated with this reimbursement mailbox."
            ),
        }

    # =========================================================
    # 6. EMPLOYEE ROLE CHECK
    # =========================================================

    if not employee.company_role:
        return {
            "success": False,
            "error": "Company role is not assigned.",
        }

    # =========================================================
    # 7. UPLOAD PERMISSION CHECK
    # =========================================================

    if not employee.company_role.can_upload_receipt:
        return {
            "success": False,
            "error": (
                "Employee is not allowed "
                "to upload receipts."
            ),
        }

    # =========================================================
    # 8. DEPARTMENT CHECK
    # =========================================================

    if not employee.department:
        return {
            "success": False,
            "error": "Department is not assigned.",
        }

    # =========================================================
    # 9. GET CURRENT MONTH REPORT
    # =========================================================

    report = get_or_create_current_month_report(
        employee
    )

    if report.status != ExpenseReport.STATUS_DRAFT:
        return {
            "success": False,
            "error": (
                "Current month's report "
                "has already been submitted."
            ),
        }

    # =========================================================
    # 10. CREATE EXPENSE SUBMISSION
    # =========================================================

    submission = ExpenseSubmission.objects.create(
        report=report,
        company=company,
        employee=employee,
        source=ExpenseSubmission.SOURCE_EMAIL,
        email_subject=subject,
    )

    # =========================================================
    # 11. CREATE EXPENSE RECEIPT
    # =========================================================

    receipt = ExpenseReceipt.objects.create(
        report=report,
        submission=submission,
        company=company,
        employee=employee,
        department=employee.department,
        receipt_file=uploaded_file,

        status=(
            ExpenseReceipt.STATUS_AI_PROCESSING
        ),

        ai_status=(
            ExpenseReceipt.AI_PROCESSING
        ),

        ai_error_message=None,
        ai_retry_count=0,
    )

    # =========================================================
    # 12. AUDIT — EMAIL RECEIPT CREATED
    # =========================================================

    create_audit_log(
        company=company,
        action="RECEIPT_UPLOADED",
        action_by=employee,
        message=(
            "Receipt received via company "
            "reimbursement email."
        ),
        metadata={
            "receipt_id": str(receipt.id),
            "report_id": str(report.id),
            "submission_id": str(submission.id),

            "filename": (
                receipt.receipt_file.name
            ),

            "source": (
                ExpenseSubmission.SOURCE_EMAIL
            ),

            "sender_email": sender_email,

            "reimbursement_email": (
                company.reimbursement_email
            ),

            "company_id": str(company.id),
            "company_name": company.name,

            "department": (
                employee.department.name
                if employee.department
                else None
            ),
        },
    )

    # =========================================================
    # 13. DO NOT START AI HERE
    # =========================================================
    #
    # AI processing is queued AFTER this function returns
    # successfully inside email_processor.py:
    #
    # queue_receipt_ai_processing(...)
    #
    # This prevents duplicate AI execution.
    # =========================================================

    return {
        "success": True,
        "company": company,
        "employee": employee,
        "report": report,
        "submission": submission,
        "receipt": receipt,
    }