import email
import imaplib
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class EmailFetcher:

    def __init__(self):
        self.connection = None

    def connect(self):
        self.connection = imaplib.IMAP4_SSL(
            settings.IMAP_HOST,
            settings.IMAP_PORT,
        )

        self.connection.login(
            settings.IMAP_EMAIL,
            settings.IMAP_PASSWORD,
        )

        logger.info("✅ Connected to IMAP server.")

    def disconnect(self):
        if self.connection:
            self.connection.logout()
            logger.info("✅ Disconnected from IMAP server.")

    def fetch_unread_emails(self):

        if not self.connection:
            raise RuntimeError("Not connected to IMAP server")

        self.connection.select("INBOX")

        status, messages = self.connection.search(None, "UNSEEN")

        logger.info("IMAP Search Status: %s", status)
        logger.info("Email IDs: %s", messages)

        if status != "OK":
            return []

        email_ids = messages[0].split()

        logger.info("Unread Email Count: %s", len(email_ids))

        parsed_emails = []

        for email_id in email_ids:

            logger.info("Fetching Email ID: %s", email_id)

            status, data = self.connection.fetch(
                email_id,
                "(RFC822)"
            )

            if status != "OK":
                logger.error("Unable to fetch email %s", email_id)
                continue

            raw_email = data[0][1]

            message = email.message_from_bytes(raw_email)

            attachments = []

            for part in message.walk():

                filename = part.get_filename()

                if not filename:
                    continue

                payload = part.get_payload(decode=True)

                if not payload:
                    continue

                attachments.append(
                    {
                        "filename": filename,
                        "content": payload,
                    }
                )

            parsed_email = {
                "message_id": message.get("Message-ID"),
                "sender_email": email.utils.parseaddr(
                    message.get("From")
                )[1],
                "recipient_email": email.utils.parseaddr(
                    message.get("To")
                )[1],
                "subject": message.get("Subject", ""),
                "attachments": attachments,
            }

            logger.info(
                "Parsed Email: %s -> %s",
                parsed_email["sender_email"],
                parsed_email["recipient_email"],
            )

            logger.info(
                "Attachment Count: %s",
                len(attachments),
            )

            parsed_emails.append(parsed_email)

            self.connection.store(
                email_id,
                "+FLAGS",
                "\\Seen",
            )

        return parsed_emails