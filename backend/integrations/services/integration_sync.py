import logging

from django.utils import timezone

from audit_logs.utils import (
    create_integration_audit_log,
)

from integrations.models import (
    IntegrationSyncLog,
)

from integrations.encryption_services import (
    decrypt_integration_config,
)

from integrations.services.bamboohr import (
    BambooHRClient,
    BambooHRAuthenticationError,
    BambooHRPermissionError,
    BambooHRConnectionError,
    BambooHRIntegrationError,
)

from integrations.services.bamboohr_sync import (
    sync_bamboohr_employees,
)


logger = logging.getLogger(__name__)


class IntegrationSyncError(Exception):
    """
    Base exception for integration synchronization errors.
    """


def run_bamboohr_sync(
    *,
    integration,
    trigger=IntegrationSyncLog.TRIGGER_MANUAL,
):
    """
    Run complete BambooHR -> ZepEx synchronization.

    Used by:
    - Manual API sync
    - Celery scheduled sync

    Flow:

        Integration
            ↓
        Read encrypted credentials
            ↓
        BambooHR API
            ↓
        Fetch employees
            ↓
        sync_bamboohr_employees()
            ↓
        Update CompanyIntegration
            ↓
        IntegrationSyncLog
            ↓
        AuditLog
    """

    # ==========================================================
    # 1. VALIDATE INTEGRATION
    # ==========================================================

    if not integration:
        raise IntegrationSyncError(
            "Integration is required."
        )

    if not integration.is_active:
        raise IntegrationSyncError(
            "Integration is inactive."
        )

    if not integration.is_connected:
        raise IntegrationSyncError(
            "BambooHR integration is not connected."
        )

    # ==========================================================
    # 2. CREATE SYNC LOG
    # ==========================================================

    sync_log = IntegrationSyncLog.objects.create(
        integration=integration,
        trigger=trigger,
        status=IntegrationSyncLog.STATUS_RUNNING,
    )

    # ==========================================================
    # 3. AUDIT — SYNC STARTED
    # ==========================================================

    create_integration_audit_log(
        company=integration.company,
        integration=integration,
        provider="BAMBOOHR",
        action="BAMBOOHR_SYNC_STARTED",
        action_by=None,
        message="BambooHR synchronization started.",
        metadata={
            "trigger": trigger,
            "sync_log_id": str(
                sync_log.id
            ),
        },
    )

    try:

        # ======================================================
        # 4. READ CREDENTIALS
        # ======================================================

        try:
            credential = integration.credential

        except Exception as exc:

            raise IntegrationSyncError(
                "Integration credentials are not configured."
            ) from exc

        if not credential.encrypted_config:

            raise IntegrationSyncError(
                "Integration credentials are empty."
            )

        try:

            config = decrypt_integration_config(
                credential.encrypted_config
            )

        except Exception as exc:

            raise IntegrationSyncError(
                "Unable to decrypt BambooHR credentials."
            ) from exc

        # ======================================================
        # 5. VALIDATE CONFIG
        # ======================================================

        company_domain = (
            config.get(
                "company_domain"
            )
            or ""
        ).strip()

        api_key = (
            config.get(
                "api_key"
            )
            or ""
        ).strip()

        if not company_domain:

            raise IntegrationSyncError(
                "BambooHR company domain is missing."
            )

        if not api_key:

            raise IntegrationSyncError(
                "BambooHR API key is missing."
            )

        # ======================================================
        # 6. CREATE BAMBOOHR CLIENT
        # ======================================================

        client = BambooHRClient(
            company_domain=company_domain,
            api_key=api_key,
        )

        logger.info(
            (
                "Starting BambooHR sync. "
                "company=%s integration=%s trigger=%s"
            ),
            integration.company_id,
            integration.id,
            trigger,
        )

        # ======================================================
        # 7. FETCH BAMBOOHR EMPLOYEES
        # ======================================================

        employees = (
            client.get_all_employees()
        )

        logger.info(
            (
                "Fetched %s BambooHR employees "
                "for company=%s."
            ),
            len(
                employees
            ),
            integration.company_id,
        )

        # ======================================================
        # 8. SYNC INTO ZEPEX
        # ======================================================

        sync_result = (
            sync_bamboohr_employees(
                integration=integration,
                employees=employees,
            )
        )

        stats = (
            sync_result.get(
                "stats"
            )
            or {}
        )

        errors = (
            sync_result.get(
                "errors"
            )
            or []
        )

        # ======================================================
        # 9. UPDATE COMPANY INTEGRATION
        # ======================================================

        now = timezone.now()

        integration.last_synced_at = now
        integration.last_sync_status = (
            "SUCCESS"
        )
        integration.last_sync_error = None

        integration.save(
            update_fields=[
                "last_synced_at",
                "last_sync_status",
                "last_sync_error",
                "updated_at",
            ]
        )

        # ======================================================
        # 10. CALCULATE SUMMARY COUNTS
        # ======================================================

        records_created = (
            stats.get(
                "users_created",
                0,
            )
            + stats.get(
                "departments_created",
                0,
            )
            + stats.get(
                "mappings_created",
                0,
            )
        )

        records_updated = (
            stats.get(
                "users_updated",
                0,
            )
            + stats.get(
                "profiles_updated",
                0,
            )
            + stats.get(
                "mappings_updated",
                0,
            )
            + stats.get(
                "managers_updated",
                0,
            )
            + stats.get(
                "department_managers_updated",
                0,
            )
        )

        records_skipped = (
            stats.get(
                "skipped",
                0,
            )
        )

        # ======================================================
        # 11. UPDATE SYNC LOG
        # ======================================================

        sync_log.status = (
            IntegrationSyncLog.STATUS_SUCCESS
        )

        sync_log.records_received = len(
            employees
        )

        sync_log.records_created = (
            records_created
        )

        sync_log.records_updated = (
            records_updated
        )

        sync_log.records_skipped = (
            records_skipped
        )

        sync_log.stats = stats

        sync_log.errors = errors

        sync_log.error_message = None

        sync_log.completed_at = now

        sync_log.save(
            update_fields=[
                "status",
                "records_received",
                "records_created",
                "records_updated",
                "records_skipped",
                "stats",
                "errors",
                "error_message",
                "completed_at",
            ]
        )

        # ======================================================
        # 12. AUDIT — SYNC COMPLETED
        # ======================================================

        create_integration_audit_log(
            company=integration.company,
            integration=integration,
            provider="BAMBOOHR",
            action="BAMBOOHR_SYNC_COMPLETED",
            action_by=None,
            message=(
                "BambooHR synchronization "
                "completed successfully."
            ),
            metadata={
                "trigger": trigger,
                "sync_log_id": str(
                    sync_log.id
                ),
                "company_domain": (
                    company_domain
                ),
                "records_received": len(
                    employees
                ),
                "records_created": (
                    records_created
                ),
                "records_updated": (
                    records_updated
                ),
                "records_skipped": (
                    records_skipped
                ),
                "stats": stats,
            },
        )

        logger.info(
            (
                "BambooHR sync completed. "
                "company=%s integration=%s "
                "received=%s created=%s "
                "updated=%s skipped=%s"
            ),
            integration.company_id,
            integration.id,
            len(
                employees
            ),
            records_created,
            records_updated,
            records_skipped,
        )

        # ======================================================
        # 13. RETURN RESULT
        # ======================================================

        return {
            "success": True,

            "integration_id": str(
                integration.id
            ),

            "provider": (
                integration.provider
            ),

            "trigger": trigger,

            "last_synced_at": (
                integration.last_synced_at
            ),

            "stats": stats,

            "errors": errors,

            "sync_log_id": str(
                sync_log.id
            ),
        }

    # ==========================================================
    # BAMBOOHR AUTH FAILURE
    # ==========================================================

    except BambooHRAuthenticationError as exc:

        return _handle_sync_failure(
            integration=integration,
            sync_log=sync_log,
            error=str(
                exc
            ),
            error_type=(
                "AUTHENTICATION_ERROR"
            ),
            trigger=trigger,
        )

    # ==========================================================
    # BAMBOOHR PERMISSION FAILURE
    # ==========================================================

    except BambooHRPermissionError as exc:

        return _handle_sync_failure(
            integration=integration,
            sync_log=sync_log,
            error=str(
                exc
            ),
            error_type=(
                "PERMISSION_ERROR"
            ),
            trigger=trigger,
        )

    # ==========================================================
    # BAMBOOHR CONNECTION FAILURE
    # ==========================================================

    except BambooHRConnectionError as exc:

        return _handle_sync_failure(
            integration=integration,
            sync_log=sync_log,
            error=str(
                exc
            ),
            error_type=(
                "CONNECTION_ERROR"
            ),
            trigger=trigger,
        )

    # ==========================================================
    # OTHER BAMBOOHR FAILURE
    # ==========================================================

    except BambooHRIntegrationError as exc:

        return _handle_sync_failure(
            integration=integration,
            sync_log=sync_log,
            error=str(
                exc
            ),
            error_type=(
                "BAMBOOHR_ERROR"
            ),
            trigger=trigger,
        )

    # ==========================================================
    # ZEPEX / CONFIGURATION FAILURE
    # ==========================================================

    except IntegrationSyncError as exc:

        return _handle_sync_failure(
            integration=integration,
            sync_log=sync_log,
            error=str(
                exc
            ),
            error_type=(
                "CONFIGURATION_ERROR"
            ),
            trigger=trigger,
        )

    # ==========================================================
    # UNKNOWN FAILURE
    # ==========================================================

    except Exception as exc:

        logger.exception(
            (
                "Unexpected BambooHR sync failure. "
                "integration=%s company=%s"
            ),
            integration.id,
            integration.company_id,
        )

        return _handle_sync_failure(
            integration=integration,
            sync_log=sync_log,
            error=str(
                exc
            ),
            error_type=(
                "INTERNAL_ERROR"
            ),
            trigger=trigger,
        )


def _handle_sync_failure(
    *,
    integration,
    sync_log,
    error,
    error_type,
    trigger=None,
):
    """
    Store a failed synchronization result in:

    - CompanyIntegration
    - IntegrationSyncLog
    - AuditLog

    This keeps manual and scheduled sync behaviour
    consistent.
    """

    now = timezone.now()

    logger.error(
        (
            "Integration sync failed. "
            "company=%s integration=%s "
            "error_type=%s error=%s"
        ),
        integration.company_id,
        integration.id,
        error_type,
        error,
    )

    # ==========================================================
    # 1. UPDATE INTEGRATION
    # ==========================================================

    integration.last_sync_status = (
        "FAILED"
    )

    integration.last_sync_error = (
        error
    )

    integration.save(
        update_fields=[
            "last_sync_status",
            "last_sync_error",
            "updated_at",
        ]
    )

    # ==========================================================
    # 2. UPDATE SYNC LOG
    # ==========================================================

    sync_log.status = (
        IntegrationSyncLog.STATUS_FAILED
    )

    sync_log.error_message = (
        error
    )

    sync_log.errors = [
        {
            "type": (
                error_type
            ),
            "message": (
                error
            ),
        }
    ]

    sync_log.completed_at = (
        now
    )

    sync_log.save(
        update_fields=[
            "status",
            "error_message",
            "errors",
            "completed_at",
        ]
    )

    # ==========================================================
    # 3. AUDIT — SYNC FAILED
    # ==========================================================

    create_integration_audit_log(
        company=integration.company,
        integration=integration,
        provider="BAMBOOHR",
        action="BAMBOOHR_SYNC_FAILED",
        action_by=None,
        message=(
            "BambooHR synchronization failed."
        ),
        metadata={
            "trigger": trigger,
            "sync_log_id": str(
                sync_log.id
            ),
            "error_type": (
                error_type
            ),
            "error": (
                error
            ),
        },
    )

    # ==========================================================
    # 4. RESPONSE
    # ==========================================================

    return {
        "success": False,

        "integration_id": str(
            integration.id
        ),

        "provider": (
            integration.provider
        ),

        "error_type": (
            error_type
        ),

        "error": (
            error
        ),

        "sync_log_id": str(
            sync_log.id
        ),
    }