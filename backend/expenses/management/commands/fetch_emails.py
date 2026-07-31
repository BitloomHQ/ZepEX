from django.core.management.base import BaseCommand

from expenses.email_fetch_runner import run_email_fetch_once


class Command(BaseCommand):
    help = "Fetch unread reimbursement emails and process receipt attachments."

    def handle(self, *args, **options):
        self.stdout.write("Fetching unread emails via IMAP...")
        result = run_email_fetch_once()

        if result.get("skipped"):
            self.stdout.write(
                self.style.WARNING(result.get("reason") or "Skipped.")
            )
            return

        if not result.get("success"):
            self.stdout.write(
                self.style.ERROR(result.get("error") or "Fetch failed.")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {result.get('count', 0)} unread email(s)."
            )
        )
        for item in result.get("results") or []:
            self.stdout.write(str(item))
