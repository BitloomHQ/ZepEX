import logging

from celery import shared_task

from .email_fetcher import EmailFetcher
from .email_processor import process_parsed_email
from .ai_processor import process_receipt

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_receipt_task(self, receipt_id):
    """
    Background AI processing for a receipt.
    """
    try:
        logger.info("Starting AI for receipt %s", receipt_id)

        result = process_receipt(receipt_id)

        logger.info("Finished AI for receipt %s", receipt_id)

        return result

    except Exception as exc:
        logger.exception("AI processing failed.")

        raise self.retry(
            exc=exc,
            countdown=60,
        )


@shared_task
def fetch_emails_task():
    """
    Fetch unread reimbursement emails.
    """

    fetcher = EmailFetcher()

    try:
        fetcher.connect()

        emails = fetcher.fetch_unread_emails()

        logger.info(
            "Found %s unread emails.",
            len(emails),
        )

        for parsed_email in emails:
            process_parsed_email(parsed_email)

    except Exception:
        logger.exception("Email fetch failed.")

    finally:
        fetcher.disconnect()