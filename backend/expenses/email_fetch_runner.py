import logging

from .email_fetcher import EmailFetcher, ImapAuthError
from .email_processor import process_parsed_email

logger = logging.getLogger(__name__)


def run_email_fetch_once():
    """
    Connect to IMAP, process unread receipt emails, disconnect.
    Shared by Celery task, management command, and in-process poller.
    """
    from django.conf import settings

    if not (
        getattr(settings, "IMAP_HOST", None)
        and getattr(settings, "IMAP_EMAIL", None)
        and getattr(settings, "IMAP_PASSWORD", None)
    ):
        return {
            "success": False,
            "skipped": True,
            "reason": "IMAP not configured",
        }

    fetcher = EmailFetcher()

    try:
        fetcher.connect()
        emails = fetcher.fetch_unread_emails()
        logger.info("Found %s unread email(s).", len(emails))

        results = [process_parsed_email(parsed) for parsed in emails]
        return {
            "success": True,
            "count": len(emails),
            "results": results,
        }
    except ImapAuthError as exc:
        logger.error("%s", exc)
        return {
            "success": False,
            "error": str(exc),
            "auth_failed": True,
        }
    except Exception:
        logger.exception("Email fetch failed.")
        return {
            "success": False,
            "error": "Email fetch failed.",
        }
    finally:
        fetcher.disconnect()
