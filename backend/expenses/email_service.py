from tenants.models import Company, UserProfile

from .models import (
    ExpenseReport,
    ExpenseSubmission,
    ExpenseReceipt,
)
from .report_utils import get_or_create_current_month_report
from .audit_services import create_audit_log


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

    New email architecture:

        Company IMAP mailbox
                ↓
        EmailFetcher(company)
                ↓
        process_parsed_email()
                ↓
        ingest_receipt_email()
                ↓
        Validate employee belongs to company
                ↓
        Create ExpenseSubmission
                ↓
        Create ExpenseReceipt
                ↓
        Queue AI processing

    The company is determined by the IMAP mailbox that
    fetched the email.

    IMPORTANT:
    An employee can only submit a receipt through the
    reimbursement mailbox belonging to their own company.
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

    sender_email = sender_email.strip().lower()

    subject = (subject or "").strip()

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
            "error": "Company reimbursement email is not configured.",
        }

    # =========================================================
    # 3. VALIDATE ATTACHMENT
    # =========================================================

    filename = uploaded_file.name or ""

    if "." not in filename:
        return {
            "success": False,
            "error": (
                "Receipt file must have a valid extension."
            ),
        }

    extension = filename.rsplit(".", 1)[-1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        return {
            "success": False,
            "error": (
                "Only PDF, JPG, JPEG and PNG files are allowed."
            ),
        }

    # =========================================================
    # 4. FIND EMPLOYEE INSIDE THIS COMPANY
    # =========================================================
    #
    # This is the most important company-isolation check.
    #
    # Example:
    #
    # Company A mailbox
    # reimbursement@companyA.com
    #
    # Employee A
    # employeeA@companyA.com
    #
    # → ACCEPT
    #
    # Company A mailbox
    # reimbursement@companyA.com
    #
    # Employee B
    # employeeB@companyB.com
    #
    # → REJECT
    #
    # The employee must belong to the exact company whose
    # IMAP mailbox fetched the email.
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
                "Sender is not a registered active employee "
                "of this company."
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
    # 6. EMPLOYEE PERMISSION CHECK
    # =========================================================

    if not employee.company_role:
        return {
            "success": False,
            "error": "Company role is not assigned.",
        }

    if not employee.company_role.can_upload_receipt:
        return {
            "success": False,
            "error": (
                "Employee is not allowed to upload receipts."
            ),
        }

    # =========================================================
    # 7. DEPARTMENT CHECK
    # =========================================================

    if not employee.department:
        return {
            "success": False,
            "error": "Department is not assigned.",
        }

    # =========================================================
    # 8. GET CURRENT MONTH REPORT
    # =========================================================

    report = get_or_create_current_month_report(employee)

    if report.status != ExpenseReport.STATUS_DRAFT:
        return {
            "success": False,
            "error": (
                "Current month's report has already been submitted."
            ),
        }

    # =========================================================
    # 9. CREATE EXPENSE SUBMISSION
    # =========================================================

    submission = ExpenseSubmission.objects.create(
        report=report,
        company=company,
        employee=employee,
        source=ExpenseSubmission.SOURCE_EMAIL,
        email_subject=subject,
    )

    # =========================================================
    # 10. CREATE EXPENSE RECEIPT
    # =========================================================

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

    # =========================================================
    # 11. AUDIT LOG — RECEIPT RECEIVED
    # =========================================================

    create_audit_log(
        company=company,
        action="RECEIPT_UPLOADED",
        action_by=employee,
        message=(
            "Receipt received via company reimbursement email."
        ),
        metadata={
            "receipt_id": str(receipt.id),
            "report_id": str(report.id),
            "submission_id": str(submission.id),
            "filename": receipt.receipt_file.name,
            "source": ExpenseSubmission.SOURCE_EMAIL,
            "sender_email": sender_email,
            "reimbursement_email": company.reimbursement_email,
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
    # 12. AUDIT LOG — AI PROCESSING
    # =========================================================
    #
    # AI is queued by email_processor.py.
    #
    # We do NOT call process_receipt() directly here.
    # This prevents synchronous AI processing and avoids
    # processing the same receipt twice.
    # =========================================================

    create_audit_log(
        company=company,
        action="AI_PROCESSING_STARTED",
        action_by=employee,
        message=(
            "AI extraction started for emailed receipt."
        ),
        metadata={
            "receipt_id": str(receipt.id),
            "report_id": str(report.id),
            "submission_id": str(submission.id),
            "source": ExpenseSubmission.SOURCE_EMAIL,
        },
    )

    # =========================================================
    # 13. RETURN RESULT
    # =========================================================
    #
    # email_processor.py will queue the AI task after this
    # function successfully returns.
    # =========================================================

    return {
        "success": True,
        "company": company,
        "employee": employee,
        "report": report,
        "submission": submission,
        "receipt": receipt,
    }