import logging

from django.core.files.base import ContentFile

from .email_service import ingest_forwarded_receipt_email
from .models import IncomingEmail

logger = logging.getLogger(__name__)


def process_parsed_email(parsed_email):
    """
    Process one parsed email and create receipts.
    """

    logger.info("========== PROCESSING EMAIL ==========")
    logger.info("Message ID: %s", parsed_email.get("message_id"))
    logger.info("Sender: %s", parsed_email.get("sender_email"))
    logger.info("Recipient: %s", parsed_email.get("recipient_email"))
    logger.info("Subject: %s", parsed_email.get("subject"))

    message_id = parsed_email.get("message_id")

    if IncomingEmail.objects.filter(
        message_id=message_id
    ).exists():

        logger.info("Email already processed.")

        return {
            "success": False,
            "error": "Email has already been processed.",
        }

    attachments = parsed_email.get("attachments", [])

    logger.info(
        "Attachments Found: %s",
        len(attachments),
    )

    if not attachments:

        logger.warning("No attachments found.")

        IncomingEmail.objects.create(
            message_id=message_id,
            sender_email=parsed_email["sender_email"],
            recipient_email=parsed_email["recipient_email"],
            subject=parsed_email["subject"],
            processed=False,
        )

        return {
            "success": False,
            "error": "No supported attachments found.",
        }

    results = []

    for attachment in attachments:

        logger.info(
            "Processing Attachment: %s",
            attachment["filename"],
        )

        uploaded_file = ContentFile(
            attachment["content"],
            name=attachment["filename"],
        )

        result = ingest_forwarded_receipt_email(
            sender_email=parsed_email["sender_email"],
            original_recipient=parsed_email["recipient_email"],
            subject=parsed_email["subject"],
            uploaded_file=uploaded_file,
        )

        logger.info("Email Service Result: %s", result)

        results.append(result)

    IncomingEmail.objects.create(
        message_id=message_id,
        sender_email=parsed_email["sender_email"],
        recipient_email=parsed_email["recipient_email"],
        subject=parsed_email["subject"],
        processed=True,
    )

    logger.info("========== EMAIL COMPLETED ==========")

    return {
        "success": True,
        "results": results,
    }