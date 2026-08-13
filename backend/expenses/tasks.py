import logging

from celery import shared_task

from .ai_processor import process_receipt
from .email_fetch_runner import run_email_fetch_once

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
)
def process_receipt_task(
    self,
    receipt_id,
):
    """
    Background AI processing for a receipt.
    """

    try:
        logger.info(
            "Starting AI for receipt %s",
            receipt_id,
        )

        result = process_receipt(
            receipt_id
        )

        logger.info(
            "Finished AI for receipt %s success=%s",
            receipt_id,
            result.get("success"),
        )

        return result

    except Exception as exc:

        logger.exception(
            "AI processing failed for receipt %s.",
            receipt_id,
        )

        raise self.retry(
            exc=exc,
            countdown=60,
        )


@shared_task
def fetch_emails_task():
    """
    Fetch reimbursement emails from all configured
    company IMAP mailboxes.
    """

    logger.info(
        "Starting scheduled reimbursement email fetch."
    )

    result = run_email_fetch_once()

    logger.info(
        "Email fetch completed. "
        "companies_processed=%s emails=%s",
        result.get("companies_processed", 0),
        result.get("count", 0),
    )

    return result