import logging

from celery import shared_task

from tenants.models import Company

from integrations.models import (
    CompanyIntegration,
    IntegrationSyncLog,
)

from integrations.services.integration_sync import (
    run_bamboohr_sync,
    RESOURCE_ALL,
)

from .services.quickbooks_export import (
    export_report_to_quickbooks,
    QuickBooksExportError,
)


logger = logging.getLogger(__name__)


# ==============================================================
# BAMBOOHR TASKS
# ==============================================================


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_single_bamboohr_integration(
    self,
    integration_id,
):
    """
    Synchronize one BambooHR integration.

    Scheduled sync always performs a complete sync:

        Departments
            ↓
        Employees
            ↓
        Managers

    OAuth token refresh is handled inside
    run_bamboohr_sync().
    """

    # ==========================================================
    # 1. FIND ACTIVE BAMBOOHR INTEGRATION
    # ==========================================================

    try:

        integration = (
            CompanyIntegration.objects
            .select_related(
                "company",
                "credential",
            )
            .get(
                id=integration_id,
                provider=(
                    CompanyIntegration
                    .PROVIDER_BAMBOOHR
                ),
                is_connected=True,
                is_active=True,
            )
        )

    except CompanyIntegration.DoesNotExist:

        logger.warning(
            (
                "BambooHR integration not found "
                "or no longer active. "
                "integration_id=%s"
            ),
            integration_id,
        )

        return {
            "success": False,
            "skipped": True,
            "error": (
                "BambooHR integration not found "
                "or inactive."
            ),
        }

    # ==========================================================
    # 2. RUN COMPLETE BAMBOOHR SYNC
    # ==========================================================

    try:

        result = run_bamboohr_sync(
            integration=integration,
            trigger=(
                IntegrationSyncLog
                .TRIGGER_SCHEDULED
            ),
            resource=RESOURCE_ALL,
        )

        logger.info(
            (
                "Scheduled BambooHR sync finished. "
                "integration=%s "
                "resource=%s "
                "success=%s"
            ),
            integration.id,
            RESOURCE_ALL,
            result.get(
                "success"
            ),
        )

        return result

    # ==========================================================
    # 3. UNEXPECTED FAILURE
    # ==========================================================

    except Exception as exc:

        logger.exception(
            (
                "Scheduled BambooHR sync crashed. "
                "integration=%s"
            ),
            integration.id,
        )

        raise self.retry(
            exc=exc,
        )


# ==============================================================
# BAMBOOHR — QUEUE ALL CONNECTED COMPANIES
# ==============================================================


@shared_task
def sync_all_bamboohr_integrations():
    """
    Queue complete BambooHR synchronization for
    every connected and active BambooHR integration.

    Each integration is queued independently.
    """

    integrations = (
        CompanyIntegration.objects
        .filter(
            provider=(
                CompanyIntegration
                .PROVIDER_BAMBOOHR
            ),
            is_connected=True,
            is_active=True,
        )
        .values_list(
            "id",
            flat=True,
        )
    )

    integration_ids = list(
        integrations
    )

    queued = 0

    for integration_id in integration_ids:

        sync_single_bamboohr_integration.delay(
            str(
                integration_id
            )
        )

        queued += 1

    logger.info(
        (
            "Queued %s BambooHR "
            "integration sync(s)."
        ),
        queued,
    )

    return {
        "success": True,
        "resource": RESOURCE_ALL,
        "queued": queued,
    }


# ==============================================================
# QUICKBOOKS TASKS
# ==============================================================


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def export_report_to_quickbooks_task(
    self,
    report_id,
    company_id,
):
    """
    Background Celery task for exporting a PAID
    ZepEx ExpenseReport to QuickBooks.

    Business logic remains inside
    export_report_to_quickbooks().
    """

    logger.info(
        (
            "Starting QuickBooks background export. "
            "company=%s report=%s"
        ),
        company_id,
        report_id,
    )

    # ==========================================================
    # 1. FIND COMPANY
    # ==========================================================

    try:

        company = (
            Company.objects.get(
                id=company_id,
            )
        )

    except Company.DoesNotExist:

        logger.error(
            (
                "QuickBooks export failed because "
                "company does not exist. "
                "company=%s report=%s"
            ),
            company_id,
            report_id,
        )

        return {
            "success": False,
            "error": (
                "Company not found."
            ),
        }

    # ==========================================================
    # 2. RUN QUICKBOOKS EXPORT
    # ==========================================================

    try:

        result = (
            export_report_to_quickbooks(
                report_id=report_id,
                company=company,
            )
        )

        logger.info(
            (
                "QuickBooks background export "
                "completed successfully. "
                "company=%s report=%s"
            ),
            company_id,
            report_id,
        )

        return result

    # ==========================================================
    # 3. BUSINESS / VALIDATION ERROR
    # ==========================================================

    except QuickBooksExportError as exc:

        logger.warning(
            (
                "QuickBooks export rejected. "
                "company=%s report=%s "
                "error=%s"
            ),
            company_id,
            report_id,
            str(
                exc
            ),
        )

        # Do not retry business errors such as:
        #
        # - Report is not PAID
        # - Missing category mappings
        # - Already exported
        # - QuickBooks disconnected

        return {
            "success": False,
            "error": str(
                exc
            ),
        }

    # ==========================================================
    # 4. UNEXPECTED ERROR
    # ==========================================================

    except Exception as exc:

        logger.exception(
            (
                "Unexpected QuickBooks "
                "background export error. "
                "company=%s report=%s"
            ),
            company_id,
            report_id,
        )

        try:

            raise self.retry(
                exc=exc,
            )

        except self.MaxRetriesExceededError:

            logger.exception(
                (
                    "QuickBooks export reached "
                    "maximum retry attempts. "
                    "company=%s report=%s"
                ),
                company_id,
                report_id,
            )

            return {
                "success": False,
                "error": (
                    "QuickBooks export failed "
                    "after multiple attempts."
                ),
            }