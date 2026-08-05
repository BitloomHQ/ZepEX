from django.conf import settings

from tenants.models import Company, UserProfile

from .models import ExpenseReceipt, ExpenseReport, ExpenseSubmission
from .report_utils import get_or_create_current_month_report


ALLOWED_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"]


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def resolve_company_for_inbound_email(
    *,
    sender_email: str,
    original_recipient: str = "",
    recipient_candidates: list[str] | None = None,
):
    """
    Resolve company for an inbound receipt email.

    Prefer matching company.reimbursement_email to To / forward headers.
    If mail landed in the platform inbox, fall back to the unique employee
    matching sender_email.
    """
    platform = _normalize_email(
        getattr(settings, "PLATFORM_RECEIPT_EMAIL", "")
    )

    candidates: list[str] = []
    for addr in [original_recipient, *(recipient_candidates or [])]:
        normalized = _normalize_email(addr)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    for addr in candidates:
        if platform and addr == platform:
            continue
        company = Company.objects.filter(
            reimbursement_email__iexact=addr,
            is_active=True,
            is_verified=True,
        ).first()
        if company:
            return company, None

    sender = _normalize_email(sender_email)
    if not sender:
        return None, "sender_email is required."

    matches = list(
        UserProfile.objects.select_related(
            "user",
            "company",
            "department",
            "company_role",
        ).filter(
            user__email__iexact=sender,
            user__is_active=True,
            company__is_active=True,
            company__is_verified=True,
        )
    )

    if len(matches) == 1:
        return matches[0].company, None

    if len(matches) > 1:
        return (
            None,
            "Sender matches multiple companies; use a company reimbursement address.",
        )

    if candidates and all(platform and addr == platform for addr in candidates):
        return (
            None,
            "Email reached the platform inbox but no company/employee match was found.",
        )

    return (
        None,
        "No verified company found for this reimbursement email.",
    )


def ingest_forwarded_receipt_email(
    *,
    sender_email,
    original_recipient="",
    subject="",
    uploaded_file=None,
    recipient_candidates=None,
):
    """
    Create ExpenseSubmission + ExpenseReceipt from an inbound email attachment.

    Does not run AI — callers should queue processing after a successful ingest.
    """
    sender_email = _normalize_email(sender_email)
    original_recipient = _normalize_email(original_recipient)

    if not sender_email:
        return {"success": False, "error": "sender_email is required."}

    if not uploaded_file:
        return {"success": False, "error": "Receipt attachment is required."}

    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        return {
            "success": False,
            "error": "Only PDF, JPG, JPEG and PNG files are allowed.",
        }

    company, resolve_error = resolve_company_for_inbound_email(
        sender_email=sender_email,
        original_recipient=original_recipient,
        recipient_candidates=recipient_candidates,
    )
    if not company:
        return {"success": False, "error": resolve_error}

    try:
        employee = UserProfile.objects.select_related(
            "user",
            "company",
            "department",
            "company_role",
        ).get(
            company=company,
            user__email__iexact=sender_email,
            user__is_active=True,
        )
    except UserProfile.DoesNotExist:
        return {
            "success": False,
            "error": "Sender is not a registered employee for this company.",
        }

    if not employee.company_role:
        return {"success": False, "error": "Company role is not assigned."}

    if not employee.company_role.can_upload_receipt:
        return {
            "success": False,
            "error": "Employee is not allowed to upload receipts.",
        }

    if not employee.department:
        return {"success": False, "error": "Department is not assigned."}

    report = get_or_create_current_month_report(employee)

    if report.status != ExpenseReport.STATUS_DRAFT:
        return {
            "success": False,
            "error": "Current month's report has already been submitted.",
        }

    submission = ExpenseSubmission.objects.create(
        report=report,
        company=company,
        employee=employee,
        source=ExpenseSubmission.SOURCE_EMAIL,
        email_subject=subject or "",
    )

    receipt = ExpenseReceipt.objects.create(
        report=report,
        submission=submission,
        company=company,
        employee=employee,
        department=employee.department,
        receipt_file=uploaded_file,
        status=ExpenseReceipt.STATUS_AI_PROCESSING,
        ai_status=ExpenseReceipt.AI_PENDING,
        ai_error_message=None,
        ai_retry_count=0,
    )

    return {
        "success": True,
        "company": company,
        "employee": employee,
        "report": report,
        "submission": submission,
        "receipt": receipt,
    }
