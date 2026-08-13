import email
import imaplib
import logging

from tenants.encryption_services import decrypt_imap_password

from .email_parser import parse_email


logger = logging.getLogger(__name__)


class ImapAuthError(RuntimeError):
    """IMAP username/password rejected by the mail server."""


class EmailFetcher:

    def __init__(self, company):
        self.company = company
        self.connection = None

    # ==========================================================
    # CONNECT
    # ==========================================================

    def connect(self):
        """
        Connect to the IMAP mailbox configured for this company.

        The saved IMAP app password is encrypted in the database,
        so it is decrypted here before login.
        """

        host = (
            self.company.imap_host or ""
        ).strip()

        username = (
            self.company.imap_username or ""
        ).strip()

        encrypted_password = (
            self.company.imap_password or ""
        ).strip()

        port = (
            self.company.imap_port or 993
        )

        # ------------------------------------------------------
        # Validate configuration
        # ------------------------------------------------------

        if not host:
            raise RuntimeError(
                f"IMAP host is not configured for "
                f"company {self.company.name}."
            )

        if not username:
            raise RuntimeError(
                f"IMAP username is not configured for "
                f"company {self.company.name}."
            )

        if not encrypted_password:
            raise RuntimeError(
                f"IMAP app password is not configured for "
                f"company {self.company.name}."
            )

        # ------------------------------------------------------
        # Decrypt saved app password
        # ------------------------------------------------------

        try:

            password = decrypt_imap_password(
                encrypted_password
            )

        except Exception as exc:

            logger.exception(
                "Unable to decrypt IMAP password "
                "for company=%s.",
                self.company.id,
            )

            raise RuntimeError(
                "Unable to decrypt the company's "
                "stored IMAP password."
            ) from exc

        password = (
            password or ""
        ).replace(" ", "")

        if not password:
            raise RuntimeError(
                f"Decrypted IMAP password is empty for "
                f"company {self.company.name}."
            )

        # ------------------------------------------------------
        # Connect
        # ------------------------------------------------------

        try:

            logger.info(
                "Connecting to IMAP for company=%s "
                "host=%s port=%s mailbox=%s",
                self.company.id,
                host,
                port,
                username,
            )

            self.connection = imaplib.IMAP4_SSL(
                host,
                port,
            )

            # --------------------------------------------------
            # Login to reimbursement mailbox
            # --------------------------------------------------

            self.connection.login(
                username,
                password,
            )

        except imaplib.IMAP4.error as exc:

            self.connection = None

            logger.error(
                "IMAP authentication failed for "
                "company=%s mailbox=%s",
                self.company.id,
                username,
            )

            raise ImapAuthError(
                "Unable to authenticate with the company's "
                "reimbursement mailbox. Check the IMAP host, "
                "port, username and app password."
            ) from exc

        except Exception:

            self.connection = None

            logger.exception(
                "Unable to connect to IMAP "
                "for company=%s.",
                self.company.id,
            )

            raise

        logger.info(
            "Successfully connected to reimbursement mailbox "
            "for company=%s mailbox=%s",
            self.company.id,
            username,
        )

    # ==========================================================
    # DISCONNECT
    # ==========================================================

    def disconnect(self):
        """
        Disconnect from the company's IMAP server.
        """

        if not self.connection:
            return

        try:

            self.connection.logout()

        except Exception:

            logger.exception(
                "IMAP logout failed for company %s.",
                self.company.id,
            )

        finally:

            self.connection = None

    # ==========================================================
    # FETCH UNREAD EMAILS
    # ==========================================================

    def fetch_unread_emails(self):
        """
        Fetch unread emails from this company's
        reimbursement mailbox.
        """

        if not self.connection:
            raise RuntimeError(
                "Not connected to IMAP server."
            )

        # ------------------------------------------------------
        # Open INBOX
        # ------------------------------------------------------

        status, _ = self.connection.select(
            "INBOX"
        )

        if status != "OK":

            raise RuntimeError(
                f"Unable to open INBOX for "
                f"company {self.company.name}."
            )

        # ------------------------------------------------------
        # Search unread emails
        # ------------------------------------------------------

        status, messages = self.connection.search(
            None,
            "UNSEEN",
        )

        if status != "OK":

            logger.error(
                "IMAP search failed for company %s: %s",
                self.company.id,
                status,
            )

            return []

        email_ids = messages[0].split()

        logger.info(
            "Company %s has %s unread email(s).",
            self.company.id,
            len(email_ids),
        )

        parsed_emails = []

        # ------------------------------------------------------
        # Process emails
        # ------------------------------------------------------

        for email_id in email_ids:

            try:

                status, data = self.connection.fetch(
                    email_id,
                    "(RFC822)",
                )

                if (
                    status != "OK"
                    or not data
                    or not data[0]
                ):

                    logger.error(
                        "Unable to fetch email %s "
                        "for company %s.",
                        email_id,
                        self.company.id,
                    )

                    continue

                raw_email = data[0][1]

                message = email.message_from_bytes(
                    raw_email
                )

                parsed = parse_email(
                    message
                )

                # --------------------------------------------------
                # Keep mailbox/company context
                # --------------------------------------------------

                parsed["company_id"] = str(
                    self.company.id
                )

                parsed[
                    "company_reimbursement_email"
                ] = self.company.reimbursement_email

                parsed_emails.append(
                    parsed
                )

                # --------------------------------------------------
                # Mark read after successful parsing
                # --------------------------------------------------

                self.connection.store(
                    email_id,
                    "+FLAGS",
                    "\\Seen",
                )

            except Exception:

                logger.exception(
                    "Failed processing email %s "
                    "for company %s.",
                    email_id,
                    self.company.id,
                )

                # Keep unread if parsing/fetching failed.
                continue

        return parsed_emails


# ==============================================================
# TEST IMAP CONNECTION
# ==============================================================

def test_imap_connection(
    *,
    host,
    port,
    username,
    password,
):
    """
    Test credentials supplied by the Company Admin.

    IMPORTANT:
    This password is the temporary/plain password received
    from the frontend. It has NOT yet been encrypted or saved.
    """

    host = (
        host or ""
    ).strip()

    username = (
        username or ""
    ).strip()

    password = (
        password or ""
    ).replace(" ", "")

    try:
        port = int(
            port or 993
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "IMAP port must be a valid number."
        ) from exc

    # ----------------------------------------------------------
    # Validation
    # ----------------------------------------------------------

    if not host:
        raise ValueError(
            "IMAP host is required."
        )

    if not username:
        raise ValueError(
            "IMAP username is required."
        )

    if not password:
        raise ValueError(
            "IMAP app password is required."
        )

    if port < 1 or port > 65535:
        raise ValueError(
            "IMAP port must be between 1 and 65535."
        )

    connection = None

    try:

        connection = imaplib.IMAP4_SSL(
            host,
            port,
        )

        connection.login(
            username,
            password,
        )

        # Optional extra validation:
        # make sure INBOX can actually be accessed.
        status, _ = connection.select(
            "INBOX",
            readonly=True,
        )

        if status != "OK":
            raise RuntimeError(
                "IMAP login succeeded but INBOX "
                "could not be accessed."
            )

        logger.info(
            "IMAP test connection successful "
            "for mailbox=%s host=%s port=%s.",
            username,
            host,
            port,
        )

        return {
            "success": True,
            "message": (
                "IMAP connection successful."
            ),
        }

    except imaplib.IMAP4.error as exc:

        logger.warning(
            "IMAP test authentication failed "
            "for mailbox=%s host=%s.",
            username,
            host,
        )

        raise ImapAuthError(
            "IMAP authentication failed. "
            "Check the username, app password, "
            "host and port."
        ) from exc

    finally:

        if connection:

            try:
                connection.logout()

            except Exception:

                logger.exception(
                    "Failed to close IMAP test connection."
                )