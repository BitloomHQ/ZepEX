import logging

from tenants.models import Company

from .email_fetcher import EmailFetcher, ImapAuthError
from .email_processor import process_parsed_email

logger = logging.getLogger(__name__)


def run_email_fetch_once():
    """
    Fetch unread reimbursement emails from every active company
    that has its own IMAP configuration.

    Each company is processed using its own mailbox and
    IMAP credentials.
    """

    companies = (
        Company.objects.filter(
            is_active=True,
            is_verified=True,
            reimbursement_email__isnull=False,
            imap_host__isnull=False,
            imap_username__isnull=False,
            imap_password__isnull=False,
        )
        .exclude(reimbursement_email="")
        .exclude(imap_host="")
        .exclude(imap_username="")
        .exclude(imap_password="")
    )

    if not companies.exists():
        return {
            "success": True,
            "count": 0,
            "companies_processed": 0,
            "results": [],
            "message": "No companies with IMAP configured.",
        }

    all_results = []
    total_emails = 0
    companies_processed = 0

    for company in companies:

        logger.info(
            "Starting email fetch for company: %s (%s)",
            company.name,
            company.id,
        )

        fetcher = EmailFetcher(company)

        try:
            # --------------------------------------------------
            # 1. Connect using THIS company's IMAP credentials
            # --------------------------------------------------

            fetcher.connect()

            # --------------------------------------------------
            # 2. Fetch unread emails from THIS mailbox
            # --------------------------------------------------

            emails = fetcher.fetch_unread_emails()

            logger.info(
                "Found %s unread email(s) for company %s.",
                len(emails),
                company.name,
            )

            company_results = []

            # --------------------------------------------------
            # 3. Process each email with company context
            # --------------------------------------------------

            for parsed in emails:

                result = process_parsed_email(
                    parsed_email=parsed,
                    company=company,
                )

                company_results.append(result)

            total_emails += len(emails)
            companies_processed += 1

            # --------------------------------------------------
            # 4. Company result
            # --------------------------------------------------

            all_results.append(
                {
                    "company_id": str(company.id),
                    "company_name": company.name,
                    "reimbursement_email": (
                        company.reimbursement_email
                    ),
                    "count": len(emails),
                    "success": True,
                    "results": company_results,
                }
            )

        # ------------------------------------------------------
        # 5. IMAP authentication failure
        # ------------------------------------------------------

        except ImapAuthError as exc:

            logger.error(
                "IMAP authentication failed for company %s: %s",
                company.name,
                exc,
            )

            all_results.append(
                {
                    "company_id": str(company.id),
                    "company_name": company.name,
                    "reimbursement_email": (
                        company.reimbursement_email
                    ),
                    "success": False,
                    "auth_failed": True,
                    "error": str(exc),
                }
            )

        # ------------------------------------------------------
        # 6. Other company-specific errors
        # ------------------------------------------------------

        except Exception as exc:

            logger.exception(
                "Email fetch failed for company %s.",
                company.name,
            )

            all_results.append(
                {
                    "company_id": str(company.id),
                    "company_name": company.name,
                    "reimbursement_email": (
                        company.reimbursement_email
                    ),
                    "success": False,
                    "error": str(exc),
                }
            )

        # ------------------------------------------------------
        # 7. Always disconnect
        # ------------------------------------------------------

        finally:
            fetcher.disconnect()

    # ----------------------------------------------------------
    # 8. Final result
    # ----------------------------------------------------------

    return {
        "success": True,
        "count": total_emails,
        "companies_processed": companies_processed,
        "results": all_results,
    }