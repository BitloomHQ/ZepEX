import logging

from datetime import timedelta

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from django.db.models import Q
from django.utils import timezone

from tenants.models import Company

from integrations.models import (
    CompanyIntegration,
    IntegrationSyncLog,
    QuickBooksExportRecord,
)

from integrations.services.integration_sync import (
    run_bamboohr_sync,
    RESOURCE_ALL,
)

from .services.quickbooks_export import (
    export_report_to_quickbooks,
    reconcile_quickbooks_export,
    QuickBooksExportError,
)


logger = logging.getLogger(__name__)


# ==============================================================
# BAMBOOHR CONFIG
# ==============================================================

BAMBOOHR_RETRYABLE_ERROR_TYPES = {
    "CONNECTION_ERROR",
    "INTERNAL_ERROR",
}


# ==============================================================
# BAMBOOHR — SYNC SINGLE INTEGRATION
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
    Synchronize one connected BambooHR integration.

    Scheduled synchronization always performs:

        Departments
            ↓
        Employees
            ↓
        Managers

    OAuth access-token refresh is handled inside
    run_bamboohr_sync().

    Celery retries only transient failures such as:

        CONNECTION_ERROR
        INTERNAL_ERROR

    Authentication, permission and configuration errors
    are returned without repeated retries because they
    usually require administrator intervention.
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
                "Scheduled BambooHR sync skipped. "
                "Integration not found, disconnected, "
                "or inactive. integration_id=%s"
            ),
            integration_id,
        )

        return {
            "success": False,
            "skipped": True,
            "integration_id": str(
                integration_id
            ),
            "error_type": (
                "INTEGRATION_NOT_AVAILABLE"
            ),
            "error": (
                "BambooHR integration not found "
                "or inactive."
            ),
        }

    # ==========================================================
    # 2. RUN COMPLETE BAMBOOHR SYNC
    # ==========================================================

    try:

        result = (
            run_bamboohr_sync(
                integration=integration,
                trigger=(
                    IntegrationSyncLog
                    .TRIGGER_SCHEDULED
                ),
                resource=RESOURCE_ALL,
            )
        )

        # ======================================================
        # 3. VALIDATE RESULT TYPE
        # ======================================================

        if not isinstance(
            result,
            dict,
        ):

            raise RuntimeError(
                (
                    "BambooHR synchronization "
                    "returned an invalid result."
                )
            )

        # ======================================================
        # 4. SUCCESS
        # ======================================================

        if result.get(
            "success"
        ):

            logger.info(
                (
                    "Scheduled BambooHR sync "
                    "completed successfully. "
                    "company=%s "
                    "integration=%s "
                    "received=%s "
                    "created=%s "
                    "updated=%s "
                    "skipped=%s"
                ),
                integration.company_id,
                integration.id,
                (
                    result.get(
                        "records",
                        {},
                    )
                    .get(
                        "received",
                        0,
                    )
                ),
                (
                    result.get(
                        "records",
                        {},
                    )
                    .get(
                        "created",
                        0,
                    )
                ),
                (
                    result.get(
                        "records",
                        {},
                    )
                    .get(
                        "updated",
                        0,
                    )
                ),
                (
                    result.get(
                        "records",
                        {},
                    )
                    .get(
                        "skipped",
                        0,
                    )
                ),
            )

            return result

        # ======================================================
        # 5. FAILED RESULT
        # ======================================================

        error_type = (
            result.get(
                "error_type"
            )
            or "UNKNOWN_ERROR"
        )

        error_message = (
            result.get(
                "error"
            )
            or (
                "BambooHR synchronization "
                "failed."
            )
        )

        logger.warning(
            (
                "Scheduled BambooHR sync failed. "
                "company=%s "
                "integration=%s "
                "error_type=%s "
                "error=%s"
            ),
            integration.company_id,
            integration.id,
            error_type,
            error_message,
        )

        # ======================================================
        # 6. RETRY TRANSIENT FAILURE
        # ======================================================

        if (
            error_type
            in BAMBOOHR_RETRYABLE_ERROR_TYPES
        ):

            try:

                raise self.retry(
                    exc=RuntimeError(
                        error_message
                    ),
                )

            except MaxRetriesExceededError:

                logger.error(
                    (
                        "BambooHR scheduled sync "
                        "reached maximum retry attempts. "
                        "company=%s "
                        "integration=%s"
                    ),
                    integration.company_id,
                    integration.id,
                )

                return {
                    **result,
                    "retry_exhausted": True,
                }

        # ======================================================
        # 7. NON-RETRYABLE FAILURE
        # ======================================================
        #
        # Examples:
        #
        # AUTHENTICATION_ERROR
        # PERMISSION_ERROR
        # CONFIGURATION_ERROR
        # BAMBOOHR_ERROR
        #
        # These should not repeatedly hammer BambooHR.
        # ======================================================

        return result

    # ==========================================================
    # 8. UNEXPECTED CELERY/TASK FAILURE
    # ==========================================================

    except MaxRetriesExceededError:

        logger.error(
            (
                "Scheduled BambooHR sync reached "
                "maximum retry attempts. "
                "company=%s "
                "integration=%s"
            ),
            integration.company_id,
            integration.id,
        )

        return {
            "success": False,
            "integration_id": str(
                integration.id
            ),
            "provider": "BAMBOOHR",
            "resource": RESOURCE_ALL,
            "error_type": (
                "RETRY_EXHAUSTED"
            ),
            "error": (
                "BambooHR scheduled sync failed "
                "after multiple attempts."
            ),
        }

    except Exception as exc:

        logger.exception(
            (
                "Scheduled BambooHR sync crashed. "
                "company=%s "
                "integration=%s"
            ),
            integration.company_id,
            integration.id,
        )

        try:

            raise self.retry(
                exc=exc,
            )

        except MaxRetriesExceededError:

            logger.error(
                (
                    "Scheduled BambooHR sync "
                    "reached maximum retry attempts "
                    "after unexpected failure. "
                    "company=%s "
                    "integration=%s"
                ),
                integration.company_id,
                integration.id,
            )

            return {
                "success": False,
                "integration_id": str(
                    integration.id
                ),
                "provider": "BAMBOOHR",
                "resource": RESOURCE_ALL,
                "error_type": (
                    "RETRY_EXHAUSTED"
                ),
                "error": (
                    "BambooHR scheduled sync failed "
                    "after multiple attempts."
                ),
            }


# ==============================================================
# BAMBOOHR — QUEUE ALL CONNECTED COMPANIES
# ==============================================================


@shared_task
def sync_all_bamboohr_integrations():
    """
    Queue a complete BambooHR synchronization for every
    connected and active BambooHR integration.

    Each company gets its own independent Celery task.

    This provides tenant isolation:

        Company A
            ↓
        Task A

        Company B
            ↓
        Task B

        Company C
            ↓
        Task C

    Failure in one company's sync does not stop another
    company's BambooHR synchronization.
    """

    integration_ids = list(
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

    # ==========================================================
    # NO CONNECTED INTEGRATIONS
    # ==========================================================

    if not integration_ids:

        logger.info(
            (
                "Scheduled BambooHR sync found "
                "no connected integrations."
            )
        )

        return {
            "success": True,
            "resource": RESOURCE_ALL,
            "found": 0,
            "queued": 0,
        }

    # ==========================================================
    # QUEUE EACH COMPANY INDEPENDENTLY
    # ==========================================================

    queued = 0

    for integration_id in (
        integration_ids
    ):

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
        "found": len(
            integration_ids
        ),
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

        except MaxRetriesExceededError:

            logger.error(
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

# ==============================================================
# QUICKBOOKS — RECONCILIATION TASKS
# ==============================================================


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def reconcile_single_quickbooks_export_task(
    self,
    export_record_id,
):
    """
    Reconcile one successful QuickBooks export against
    the actual Purchase transaction in QuickBooks.

    The reconciliation service determines whether the
    transaction is:

        VERIFIED
        MISMATCH
        MISSING
        ERROR
    """

    # ==========================================================
    # 1. FIND EXPORT RECORD
    # ==========================================================

    try:

        export_record = (
            QuickBooksExportRecord.objects
            .select_related(
                "integration",
                "integration__company",
                "report",
            )
            .get(
                id=export_record_id,
                status=(
                    QuickBooksExportRecord
                    .STATUS_SUCCESS
                ),
            )
        )

    except QuickBooksExportRecord.DoesNotExist:

        logger.warning(
            (
                "QuickBooks reconciliation skipped. "
                "Successful export record not found. "
                "export_record=%s"
            ),
            export_record_id,
        )

        return {
            "success": False,
            "skipped": True,
            "export_record_id": str(
                export_record_id
            ),
            "error": (
                "Successful QuickBooks export "
                "record not found."
            ),
        }

    integration = export_record.integration

    # ==========================================================
    # 2. INTEGRATION MUST STILL BE AVAILABLE
    # ==========================================================

    if not (
        integration.is_connected
        and integration.is_active
    ):

        logger.warning(
            (
                "QuickBooks reconciliation skipped. "
                "Integration disconnected or inactive. "
                "integration=%s export_record=%s"
            ),
            integration.id,
            export_record.id,
        )

        return {
            "success": False,
            "skipped": True,
            "export_record_id": str(
                export_record.id
            ),
            "error": (
                "QuickBooks integration is "
                "disconnected or inactive."
            ),
        }

    # ==========================================================
    # 3. RUN RECONCILIATION
    # ==========================================================

    try:

        result = reconcile_quickbooks_export(
            report_id=export_record.report_id,
            company=integration.company,
        )

        logger.info(
            (
                "QuickBooks automatic reconciliation "
                "completed. company=%s report=%s "
                "export_record=%s status=%s"
            ),
            integration.company_id,
            export_record.report_id,
            export_record.id,
            result.get(
                "reconciliation_status"
            ),
        )

        return result

    # ==========================================================
    # 4. EXPECTED QUICKBOOKS / BUSINESS FAILURE
    # ==========================================================

    except QuickBooksExportError as exc:

        logger.warning(
            (
                "QuickBooks automatic reconciliation "
                "rejected. company=%s report=%s "
                "export_record=%s error=%s"
            ),
            integration.company_id,
            export_record.report_id,
            export_record.id,
            str(exc),
        )

        return {
            "success": False,
            "export_record_id": str(
                export_record.id
            ),
            "error": str(exc),
        }

    # ==========================================================
    # 5. UNEXPECTED FAILURE — RETRY
    # ==========================================================

    except Exception as exc:

        logger.exception(
            (
                "Unexpected QuickBooks automatic "
                "reconciliation error. "
                "company=%s report=%s "
                "export_record=%s"
            ),
            integration.company_id,
            export_record.report_id,
            export_record.id,
        )

        try:

            raise self.retry(
                exc=exc,
            )

        except MaxRetriesExceededError:

            logger.error(
                (
                    "QuickBooks reconciliation reached "
                    "maximum retry attempts. "
                    "export_record=%s"
                ),
                export_record.id,
            )

            return {
                "success": False,
                "export_record_id": str(
                    export_record.id
                ),
                "error": (
                    "QuickBooks reconciliation failed "
                    "after multiple attempts."
                ),
            }


# ==============================================================
# QUICKBOOKS — QUEUE RECONCILIATIONS
# ==============================================================


@shared_task
def reconcile_all_quickbooks_exports():
    """
    Queue smart reconciliation for successful QuickBooks exports.

    Selection policy:

    - NOT_CHECKED:
        Reconcile immediately.

    - VERIFIED:
        Recheck after 24 hours. This detects a transaction that
        was later edited or deleted in QuickBooks without calling
        QuickBooks every minute.

    - MISMATCH:
        Recheck after 6 hours. A finance user may correct the
        transaction in QuickBooks.

    - MISSING:
        Recheck after 6 hours. A transaction may be restored or
        replaced outside ZepEx.

    - ERROR:
        Recheck after 30 minutes.

    Celery Beat can safely call this dispatcher frequently because
    only records that are due are queued.
    """

    now = timezone.now()

    verified_cutoff = now - timedelta(hours=24)
    mismatch_cutoff = now - timedelta(hours=6)
    missing_cutoff = now - timedelta(hours=6)
    error_cutoff = now - timedelta(minutes=30)

    # ==========================================================
    # 1. BASE ELIGIBILITY
    # ==========================================================

    base_queryset = (
        QuickBooksExportRecord.objects
        .filter(
            status=(
                QuickBooksExportRecord
                .STATUS_SUCCESS
            ),
            integration__provider=(
                CompanyIntegration
                .PROVIDER_QUICKBOOKS
            ),
            integration__is_connected=True,
            integration__is_active=True,
        )
    )

    # ==========================================================
    # 2. FIND ONLY RECORDS THAT ARE DUE
    # ==========================================================

    due_filter = (
        Q(
            reconciliation_status=(
                QuickBooksExportRecord
                .RECONCILIATION_NOT_CHECKED
            )
        )
        |
        Q(
            reconciliation_status=(
                QuickBooksExportRecord
                .RECONCILIATION_VERIFIED
            ),
            reconciled_at__lt=verified_cutoff,
        )
        |
        Q(
            reconciliation_status=(
                QuickBooksExportRecord
                .RECONCILIATION_MISMATCH
            ),
            reconciled_at__lt=mismatch_cutoff,
        )
        |
        Q(
            reconciliation_status=(
                QuickBooksExportRecord
                .RECONCILIATION_MISSING
            ),
            reconciled_at__lt=missing_cutoff,
        )
        |
        Q(
            reconciliation_status=(
                QuickBooksExportRecord
                .RECONCILIATION_ERROR
            ),
            reconciled_at__lt=error_cutoff,
        )
        |
        Q(
            reconciled_at__isnull=True,
        )
    )

    export_ids = list(
        base_queryset
        .filter(due_filter)
        .order_by(
            "reconciled_at",
            "id",
        )
        .values_list(
            "id",
            flat=True,
        )
    )

    # ==========================================================
    # 3. NOTHING IS DUE
    # ==========================================================

    if not export_ids:

        logger.info(
            "Automatic QuickBooks reconciliation "
            "found no exports due for reconciliation."
        )

        return {
            "success": True,
            "found": 0,
            "queued": 0,
            "checked_at": now.isoformat(),
        }

    # ==========================================================
    # 4. QUEUE EACH EXPORT INDEPENDENTLY
    # ==========================================================

    queued = 0

    for export_id in export_ids:

        reconcile_single_quickbooks_export_task.delay(
            str(export_id)
        )

        queued += 1

    logger.info(
        (
            "Queued %s QuickBooks export(s) "
            "for smart reconciliation."
        ),
        queued,
    )

    return {
        "success": True,
        "found": len(export_ids),
        "queued": queued,
        "checked_at": now.isoformat(),
        "policy": {
            "not_checked": "immediate",
            "verified_recheck_hours": 24,
            "mismatch_recheck_hours": 6,
            "missing_recheck_hours": 6,
            "error_recheck_minutes": 30,
        },
    }

