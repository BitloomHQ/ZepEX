from django.core.management.base import BaseCommand

from expenses.email_fetcher import EmailFetcher
from expenses.email_parser import parse_email
from expenses.email_processor import process_parsed_email


class Command(BaseCommand):
    help = "Fetch unread reimbursement emails and process receipts."

    def handle(self, *args, **options):

        fetcher = EmailFetcher()

        try:
            self.stdout.write("Connecting to IMAP...")

            fetcher.connect()

            emails = fetcher.fetch_unread_emails()

            self.stdout.write(
                f"Found {len(emails)} unread email(s)."
            )

            for index, message in enumerate(emails, start=1):

                self.stdout.write(
                    f"\nProcessing email {index}..."
                )

                parsed_email = parse_email(message)

                self.stdout.write(
                    f"Sender : {parsed_email['sender_email']}"
                )

                self.stdout.write(
                    f"Subject : {parsed_email['subject']}"
                )

                self.stdout.write(
                    f"Attachments : {len(parsed_email['attachments'])}"
                )

                result = process_parsed_email(parsed_email)

                self.stdout.write(str(result))

            self.stdout.write(
                self.style.SUCCESS(
                    "\nAll unread emails processed successfully."
                )
            )

        except Exception as e:

            self.stdout.write(
                self.style.ERROR(str(e))
            )

        finally:

            fetcher.disconnect()