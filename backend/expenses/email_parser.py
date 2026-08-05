from email.header import decode_header
from email.utils import parseaddr


ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}

# Headers that may carry the company reimbursement address after a forward.
_FORWARD_RECIPIENT_HEADERS = (
    "X-Original-To",
    "X-Forwarded-To",
    "Delivered-To",
    "Envelope-To",
    "X-Envelope-To",
    "Resent-To",
)


def decode_mime_header(value):
    if not value:
        return ""

    decoded = decode_header(value)
    result = ""

    for text, encoding in decoded:
        if isinstance(text, bytes):
            result += text.decode(encoding or "utf-8", errors="ignore")
        else:
            result += text

    return result.strip()


def _emails_from_header(value: str) -> list[str]:
    if not value:
        return []
    addresses = []
    for part in value.split(","):
        addr = parseaddr(part)[1].strip().lower()
        if addr and "@" in addr:
            addresses.append(addr)
    return addresses


def parse_email(message):
    """
    Parse one email.message.Message into a dict for process_parsed_email.
    """
    sender_email = parseaddr(message.get("From", ""))[1].lower().strip()

    recipient_candidates: list[str] = []
    for header in ("To", "Cc", *_FORWARD_RECIPIENT_HEADERS):
        for addr in _emails_from_header(message.get(header, "")):
            if addr not in recipient_candidates:
                recipient_candidates.append(addr)

    # Prefer To / forward headers; first non-empty wins as primary recipient.
    original_recipient = recipient_candidates[0] if recipient_candidates else ""

    subject = decode_mime_header(message.get("Subject", ""))
    message_id = (message.get("Message-ID") or "").strip()
    received_date = message.get("Date", "")

    attachments = []
    for part in message.walk():
        filename = part.get_filename()
        if not filename:
            continue

        filename = decode_mime_header(filename)
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in ALLOWED_EXTENSIONS:
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        attachments.append(
            {
                "filename": filename,
                "content_type": part.get_content_type(),
                "content": payload,
            }
        )

    return {
        "sender_email": sender_email,
        "recipient_email": original_recipient,
        "original_recipient": original_recipient,
        "recipient_candidates": recipient_candidates,
        "subject": subject,
        "message_id": message_id,
        "received_date": received_date,
        "attachments": attachments,
    }
