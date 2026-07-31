import email
from email.header import decode_header
from email.utils import parseaddr


ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def decode_mime_header(value):
    """
    Decode MIME encoded headers like:
    =?UTF-8?B?...?=
    """
    if not value:
        return ""

    decoded = decode_header(value)

    result = ""

    for text, encoding in decoded:
        if isinstance(text, bytes):
            result += text.decode(
                encoding or "utf-8",
                errors="ignore"
            )
        else:
            result += text

    return result.strip()


def parse_email(message):
    """
    Parse one email.message.EmailMessage object.

    Returns:
    {
        sender_email,
        original_recipient,
        subject,
        message_id,
        received_date,
        attachments
    }
    """

    sender_email = parseaddr(
        message.get("From", "")
    )[1].lower()

    original_recipient = parseaddr(
        message.get("To", "")
    )[1].lower()

    subject = decode_mime_header(
        message.get("Subject", "")
    )

    message_id = message.get(
        "Message-ID",
        ""
    )

    received_date = message.get(
        "Date",
        ""
    )

    attachments = []

    for part in message.walk():

        filename = part.get_filename()

        if not filename:
            continue

        filename = decode_mime_header(filename)

        extension = filename.split(".")[-1].lower()

        if extension not in ALLOWED_EXTENSIONS:
            continue

        payload = part.get_payload(decode=True)

        attachments.append(
            {
                "filename": filename,
                "content_type": part.get_content_type(),
                "content": payload,
            }
        )

    return {
        "sender_email": sender_email,
        "original_recipient": original_recipient,
        "subject": subject,
        "message_id": message_id,
        "received_date": received_date,
        "attachments": attachments,
    }