import email
import imaplib
import logging

from django.conf import settings

from .email_parser import parse_email

logger = logging.getLogger(__name__)


class EmailFetcher:
    def __init__(self):
        self.connection = None

    def connect(self):
        host = getattr(settings, "IMAP_HOST", None)
        user = getattr(settings, "IMAP_EMAIL", None)
        password = getattr(settings, "IMAP_PASSWORD", None)
        port = int(getattr(settings, "IMAP_PORT", 993) or 993)

        if not host or not user or not password:
            raise RuntimeError(
                "IMAP is not configured. Set IMAP_HOST, IMAP_EMAIL, and IMAP_PASSWORD."
            )

        self.connection = imaplib.IMAP4_SSL(host, port)
        self.connection.login(user, password)
        logger.info("Connected to IMAP server %s", host)

    def disconnect(self):
        if self.connection:
            try:
                self.connection.logout()
            except Exception:
                logger.exception("IMAP logout failed.")
            finally:
                self.connection = None
            logger.info("Disconnected from IMAP server.")

    def fetch_unread_emails(self):
        if not self.connection:
            raise RuntimeError("Not connected to IMAP server")

        self.connection.select("INBOX")
        status, messages = self.connection.search(None, "UNSEEN")

        if status != "OK":
            logger.error("IMAP search failed: %s", status)
            return []

        email_ids = messages[0].split()
        logger.info("Unread email count: %s", len(email_ids))

        parsed_emails = []

        for email_id in email_ids:
            status, data = self.connection.fetch(email_id, "(RFC822)")
            if status != "OK" or not data or not data[0]:
                logger.error("Unable to fetch email %s", email_id)
                continue

            raw_email = data[0][1]
            message = email.message_from_bytes(raw_email)
            parsed = parse_email(message)
            parsed_emails.append(parsed)

            self.connection.store(email_id, "+FLAGS", "\\Seen")

        return parsed_emails
