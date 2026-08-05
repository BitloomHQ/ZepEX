import hashlib
import logging

from django.core.files.base import ContentFile

from audit_logs.utils import create_audit_log

from .ai_queue import queue_receipt_ai_processing
from .email_service import ingest_forwarded_receipt_email
from .models import IncomingEmail

logger = logging.getLogger(__name__)


def _stable_message_id(parsed_email: dict) -> str:
    message_id = (parsed_email.get("message_id") or "").strip()
    if message_id:
        return message_id[:500]

    digest = hashlib.sha256(
        "|".join(
            [
                parsed_email.get("sender_email") or "",
                parsed_email.get("recipient_email")
                or parsed_email.get("original_recipient")
                or "",
                parsed_email.get("subject") or "",
                parsed_email.get("received_date") or "",
                str(len(parsed_email.get("attachments") or [])),
            ]
        ).encode("utf-8")
    ).hexdigest()
    return f"generated-{digest}"


def process_parsed_email(parsed_email):
    """
    Process one parsed email and create receipts for supported attachments.
    """
    sender_email = (parsed_email.get("sender_email") or "").lower().strip()
    recipient_email = (
        parsed_email.get("recipient_email")
        or parsed_email.get("original_recipient")
        or ""
    ).lower().strip()
    subject = parsed_email.get("subject") or ""
    recipient_candidates = parsed_email.get("recipient_candidates") or []
    message_id = _stable_message_id(parsed_email)

    logger.info(
        "Processing email message_id=%s sender=%s recipient=%s",
        message_id,
        sender_email,
        recipient_email,
    )

    if IncomingEmail.objects.filter(message_id=message_id).exists():
        return {
            "success": False,
            "error": "Email has already been processed.",
        }

    attachments = parsed_email.get("attachments") or []
    if not attachments:
        IncomingEmail.objects.create(
            message_id=message_id,
            sender_email=sender_email or "unknown@invalid",
            recipient_email=recipient_email or "unknown@invalid",
            subject=subject[:500],
            processed=False,
        )
        return {
            "success": False,
            "error": "No supported attachments found.",
        }

    results = []
    any_success = False

    for attachment in attachments:
        uploaded_file = ContentFile(
            attachment["content"],
            name=attachment["filename"],
        )

        result = ingest_forwarded_receipt_email(
            sender_email=sender_email,
            original_recipient=recipient_email,
            subject=subject,
            uploaded_file=uploaded_file,
            recipient_candidates=recipient_candidates,
        )
        results.append(
            {
                "filename": attachment["filename"],
                "success": result.get("success"),
                "error": result.get("error"),
                "receipt_id": (
                    str(result["receipt"].id)
                    if result.get("success") and result.get("receipt")
                    else None
                ),
            }
        )

        if not result.get("success"):
            logger.warning(
                "Ingest failed for %s: %s",
                attachment["filename"],
                result.get("error"),
            )
            continue

        any_success = True
        receipt = result["receipt"]
        company = result["company"]
        employee = result["employee"]
        report = result["report"]

        queue_receipt_ai_processing(
            receipt_id=str(receipt.id),
            company=company,
            action_by=employee,
            report_id=str(report.id),
        )

        create_audit_log(
            company=company,
            action="EMAIL_RECEIPT_RECEIVED",
            action_by=employee,
            message=f"Receipt email received from {sender_email}",
            metadata={
                "receipt_id": str(receipt.id),
                "report_id": str(report.id),
                "sender_email": sender_email,
                "recipient_email": recipient_email,
                "email_subject": subject,
                "filename": attachment["filename"],
            },
        )

    IncomingEmail.objects.create(
        message_id=message_id,
        sender_email=sender_email or "unknown@invalid",
        recipient_email=recipient_email or "unknown@invalid",
        subject=subject[:500],
        processed=any_success,
    )

    return {
        "success": any_success,
        "results": results,
        "error": None if any_success else "All attachments failed to ingest.",
    }
