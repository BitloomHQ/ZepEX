import logging

from datetime import timedelta

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from tenants.models import Company

from integrations.models import (
    CompanyIntegration,
    IntegrationChangeLog,
    IntegrationCredential,
    IntegrationEmployeeMapping,
    IntegrationSyncLog,
    QuickBooksExportRecord,
)

from integrations.encryption_services import (
    decrypt_integration_config,
    encrypt_integration_config,
)

from integrations.services.bamboohr import (
    BambooHRAuthenticationError,
    BambooHRClient,
    BambooHRConnectionError,
    BambooHRIntegrationError,
    BambooHROAuthService,
    BambooHRPermissionError,
)

from integrations.services.bamboohr_sync import (
    sync_bamboohr_all,
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

# Celery Beat may call the BambooHR dispatcher frequently, but each
# integration should only run a full sync when this interval has elapsed.
BAMBOOHR_SCHEDULED_SYNC_INTERVAL = timedelta(hours=1)

BAMBOOHR_WEBHOOK_EVENT_TYPES = {
    "employee.created",
    "employee.updated",
    "employee.deleted",
}


# ==============================================================
# BAMBOOHR WEBHOOK HELPERS
# ==============================================================


def _complete_bamboohr_webhook_sync_log(
    *,
    sync_log,
    success,
    stats=None,
    errors=None,
    error_message=None,
):
    """
    Complete one BambooHR webhook synchronization log.
    """

    stats = (
        stats
        if isinstance(stats, dict)
        else {}
    )

    errors = (
        errors
        if isinstance(errors, list)
        else []
    )

    record_created = bool(
        stats.get("mappings_created")
        or stats.get("record_created")
    )

    record_updated = bool(
        stats.get("record_updated")
        or stats.get("mappings_updated")
        or stats.get("users_updated")
        or stats.get("profiles_updated")
        or stats.get("employees_activated")
        or stats.get("employees_deactivated")
        or stats.get("job_titles_updated")
    )

    sync_log.status = (
        IntegrationSyncLog.STATUS_SUCCESS
        if success
        else IntegrationSyncLog.STATUS_FAILED
    )

    sync_log.records_received = int(
        stats.get("received", 1)
        or 0
    )

    sync_log.records_created = (
        1
        if record_created
        else 0
    )

    sync_log.records_updated = (
        1
        if record_updated
        else 0
    )

    sync_log.records_skipped = min(
        int(
            stats.get("skipped", 0)
            or 0
        ),
        1,
    )

    sync_log.stats = stats
    sync_log.errors = errors
    sync_log.error_message = (
        str(error_message)
        if error_message
        else None
    )
    sync_log.completed_at = timezone.now()

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


def _get_bamboohr_webhook_employee(
    *,
    integration,
    employee_id,
):
    """
    Fetch one BambooHR employee for a webhook event.

    If the access token has expired, refresh it, preserve the
    encrypted webhook signing key, and retry once.
    """

    try:
        credential = integration.credential

    except IntegrationCredential.DoesNotExist as exc:
        raise BambooHRAuthenticationError(
            "BambooHR credentials are missing."
        ) from exc

    try:
        config = decrypt_integration_config(
            credential.encrypted_config
        )

    except Exception as exc:
        raise BambooHRAuthenticationError(
            "Unable to decrypt BambooHR credentials."
        ) from exc

    company_domain = str(
        config.get("company_domain")
        or ""
    ).strip()

    access_token = str(
        config.get("access_token")
        or ""
    ).strip()

    refresh_token = str(
        config.get("refresh_token")
        or ""
    ).strip()

    if not company_domain:
        raise BambooHRIntegrationError(
            "BambooHR company domain is missing."
        )

    if not access_token:
        raise BambooHRAuthenticationError(
            "BambooHR access token is missing."
        )

    client = BambooHRClient(
        company_domain=company_domain,
        access_token=access_token,
    )

    try:
        return client.get_employee(
            employee_id
        )

    except BambooHRAuthenticationError:

        if not refresh_token:
            raise BambooHRAuthenticationError(
                (
                    "BambooHR access token expired and "
                    "no refresh token is available."
                )
            )

    oauth_service = BambooHROAuthService(
        company_domain=company_domain,
    )

    token_data = (
        oauth_service.refresh_access_token(
            refresh_token=refresh_token,
        )
    )

    new_access_token = str(
        token_data.get("access_token")
        or ""
    ).strip()

    new_refresh_token = str(
        token_data.get("refresh_token")
        or refresh_token
    ).strip()

    if not new_access_token:
        raise BambooHRAuthenticationError(
            (
                "BambooHR token refresh did not "
                "return an access token."
            )
        )

    config["access_token"] = (
        new_access_token
    )

    config["refresh_token"] = (
        new_refresh_token
    )

    expires_in = token_data.get(
        "expires_in"
    )

    if expires_in:
        config["access_token_expires_at"] = (
            timezone.now()
            + timedelta(
                seconds=int(expires_in)
            )
        ).isoformat()

    credential.encrypted_config = (
        encrypt_integration_config(
            config
        )
    )

    credential.save(
        update_fields=[
            "encrypted_config",
            "updated_at",
        ]
    )

    refreshed_client = BambooHRClient(
        company_domain=company_domain,
        access_token=new_access_token,
    )

    return refreshed_client.get_employee(
        employee_id
    )


def _deactivate_deleted_bamboohr_employee(
    *,
    integration,
    employee_id,
    sync_log,
    event_timestamp=None,
):
    """
    Deactivate the mapped ZepEx user after BambooHR sends
    employee.deleted. The integration mapping is retained for
    audit history and idempotent retry handling.
    """

    mapping = (
        IntegrationEmployeeMapping.objects
        .select_for_update()
        .select_related(
            "user_profile",
            "user_profile__user",
        )
        .filter(
            integration=integration,
            external_employee_id=str(
                employee_id
            ),
        )
        .first()
    )

    if not mapping:
        return {
            "success": True,
            "stats": {
                "received": 1,
                "skipped": 1,
                "record_updated": 0,
            },
            "errors": [
                {
                    "external_employee_id": str(
                        employee_id
                    ),
                    "warning": (
                        "BambooHR employee mapping "
                        "was not found."
                    ),
                }
            ],
        }

    profile = mapping.user_profile
    user = profile.user
    was_active = bool(user.is_active)

    if was_active:
        user.is_active = False
        user.save(
            update_fields=[
                "is_active",
            ]
        )

        display_name = (
            user.get_full_name().strip()
            or user.email
            or user.username
        )

        IntegrationChangeLog.objects.create(
            integration=integration,
            sync_log=sync_log,
            resource_type=(
                IntegrationChangeLog
                .RESOURCE_EMPLOYEE
            ),
            external_resource_id=str(
                employee_id
            ),
            resource_name=display_name,
            change_type=(
                IntegrationChangeLog
                .CHANGE_DEACTIVATED
            ),
            field_name="is_active",
            old_value="True",
            new_value="False",
            details={
                "source": "BAMBOOHR_WEBHOOK",
                "event": "employee.deleted",
                "event_timestamp": event_timestamp,
            },
        )

    mapping.last_synced_at = timezone.now()
    mapping.save(
        update_fields=[
            "last_synced_at",
            "updated_at",
        ]
    )

    return {
        "success": True,
        "stats": {
            "received": 1,
            "skipped": 0,
            "employees_deactivated": (
                1
                if was_active
                else 0
            ),
            "record_updated": (
                1
                if was_active
                else 0
            ),
        },
        "errors": [],
    }


# ==============================================================
# BAMBOOHR — PROCESS WEBHOOK EVENT
# ==============================================================


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_bamboohr_webhook_event(
    self,
    integration_id,
    event_type,
    employee_id,
    event_timestamp=None,
):
    """
    Process one verified BambooHR employee webhook event.

    Events for the same integration are serialized with a
    database row lock to prevent concurrent employee creation,
    token refresh, or mapping updates.
    """

    event_type = str(
        event_type
        or ""
    ).strip().lower()

    employee_id = str(
        employee_id
        or ""
    ).strip()

    if event_type not in BAMBOOHR_WEBHOOK_EVENT_TYPES:
        return {
            "success": False,
            "error_type": "INVALID_EVENT",
            "error": (
                "Unsupported BambooHR webhook event."
            ),
        }

    if not employee_id:
        return {
            "success": False,
            "error_type": "INVALID_EVENT",
            "error": (
                "BambooHR employee ID is missing."
            ),
        }

    try:
        integration = (
            CompanyIntegration.objects
            .select_related(
                "company",
            )
            .get(
                id=integration_id,
                provider=(
                    CompanyIntegration
                    .PROVIDER_BAMBOOHR
                ),
                is_connected=True,
                is_active=True,
                bamboohr_webhook_enabled=True,
            )
        )

    except CompanyIntegration.DoesNotExist:
        return {
            "success": False,
            "skipped": True,
            "error_type": (
                "INTEGRATION_NOT_AVAILABLE"
            ),
            "error": (
                "BambooHR integration is unavailable."
            ),
        }

    sync_log = IntegrationSyncLog.objects.create(
        integration=integration,
        status=(
            IntegrationSyncLog.STATUS_RUNNING
        ),
        trigger=(
            IntegrationSyncLog.TRIGGER_WEBHOOK
        ),
        stats={
            "resource": "ALL",
            "event_type": event_type,
            "employee_id": employee_id,
            "event_timestamp": event_timestamp,
        },
    )

    try:

        with transaction.atomic():

            integration = (
                CompanyIntegration.objects
                .select_for_update()
                .select_related(
                    "company",
                )
                .get(
                    id=integration.id,
                    provider=(
                        CompanyIntegration
                        .PROVIDER_BAMBOOHR
                    ),
                    is_connected=True,
                    is_active=True,
                    bamboohr_webhook_enabled=True,
                )
            )

            if event_type == "employee.deleted":

                result = (
                    _deactivate_deleted_bamboohr_employee(
                        integration=integration,
                        employee_id=employee_id,
                        sync_log=sync_log,
                        event_timestamp=(
                            event_timestamp
                        ),
                    )
                )

            else:

                employee = (
                    _get_bamboohr_webhook_employee(
                        integration=integration,
                        employee_id=employee_id,
                    )
                )

                result = sync_bamboohr_all(
                    integration=integration,
                    employees=[employee],
                    sync_log=sync_log,
                )

            result_success = bool(
                result.get("success")
            )

            integration.last_synced_at = (
                timezone.now()
            )
            integration.last_sync_status = (
                IntegrationSyncLog.STATUS_SUCCESS
                if result_success
                else IntegrationSyncLog.STATUS_FAILED
            )
            integration.last_sync_error = (
                None
                if result_success
                else (
                    "BambooHR webhook employee "
                    "synchronization completed "
                    "with errors."
                )
            )

            integration.save(
                update_fields=[
                    "last_synced_at",
                    "last_sync_status",
                    "last_sync_error",
                    "updated_at",
                ]
            )

        result_stats = (
            result.get("stats")
            or {}
        )

        result_stats.update(
            {
                "resource": "ALL",
                "event_type": event_type,
                "employee_id": employee_id,
                "event_timestamp": event_timestamp,
            }
        )

        result_errors = (
            result.get("errors")
            or []
        )

        _complete_bamboohr_webhook_sync_log(
            sync_log=sync_log,
            success=result_success,
            stats=result_stats,
            errors=result_errors,
            error_message=(
                None
                if result_success
                else (
                    "BambooHR webhook employee "
                    "synchronization completed "
                    "with errors."
                )
            ),
        )

        logger.info(
            (
                "BambooHR webhook event processed. "
                "integration=%s event=%s employee=%s "
                "success=%s"
            ),
            integration.id,
            event_type,
            employee_id,
            result_success,
        )

        return {
            "success": result_success,
            "integration_id": str(
                integration.id
            ),
            "event_type": event_type,
            "employee_id": employee_id,
            "sync_log_id": str(
                sync_log.id
            ),
            "stats": result_stats,
            "errors": result_errors,
        }

    except BambooHRConnectionError as exc:

        _complete_bamboohr_webhook_sync_log(
            sync_log=sync_log,
            success=False,
            stats={
                "received": 1,
                "resource": "ALL",
                "event_type": event_type,
                "employee_id": employee_id,
                "event_timestamp": event_timestamp,
            },
            errors=[],
            error_message=str(exc),
        )

        logger.warning(
            (
                "Transient BambooHR webhook sync failure. "
                "integration=%s event=%s employee=%s"
            ),
            integration.id,
            event_type,
            employee_id,
        )

        raise self.retry(
            exc=exc,
        )

    except (
        BambooHRAuthenticationError,
        BambooHRPermissionError,
        BambooHRIntegrationError,
        ValueError,
    ) as exc:

        _complete_bamboohr_webhook_sync_log(
            sync_log=sync_log,
            success=False,
            stats={
                "received": 1,
                "resource": "ALL",
                "event_type": event_type,
                "employee_id": employee_id,
                "event_timestamp": event_timestamp,
            },
            errors=[],
            error_message=str(exc),
        )

        integration.last_sync_status = (
            IntegrationSyncLog.STATUS_FAILED
        )
        integration.last_sync_error = str(exc)
        integration.save(
            update_fields=[
                "last_sync_status",
                "last_sync_error",
                "updated_at",
            ]
        )

        logger.warning(
            (
                "BambooHR webhook event could not be "
                "processed. integration=%s event=%s "
                "employee=%s error_type=%s"
            ),
            integration.id,
            event_type,
            employee_id,
            exc.__class__.__name__,
        )

        return {
            "success": False,
            "integration_id": str(
                integration.id
            ),
            "event_type": event_type,
            "employee_id": employee_id,
            "sync_log_id": str(
                sync_log.id
            ),
            "error_type": (
                exc.__class__.__name__
            ),
            "error": str(exc),
        }

    except Exception as exc:

        _complete_bamboohr_webhook_sync_log(
            sync_log=sync_log,
            success=False,
            stats={
                "received": 1,
                "resource": "ALL",
                "event_type": event_type,
                "employee_id": employee_id,
                "event_timestamp": event_timestamp,
            },
            errors=[],
            error_message=(
                "Unexpected BambooHR webhook "
                "processing failure."
            ),
        )

        logger.exception(
            (
                "Unexpected BambooHR webhook failure. "
                "integration=%s event=%s employee=%s"
            ),
            integration.id,
            event_type,
            employee_id,
        )

        raise self.retry(
            exc=exc,
        )


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
    Queue BambooHR synchronization only for integrations that are due.

    Celery Beat can safely call this dispatcher every 15 minutes.
    A connected BambooHR integration is queued when:

    - it has never synchronized, or
    - its last successful/attempted sync is at least one hour old.

    Each company still receives its own independent Celery task so a
    failure in one tenant does not block another tenant.
    """

    now = timezone.now()
    due_before = now - BAMBOOHR_SCHEDULED_SYNC_INTERVAL

    # ==========================================================
    # 1. FIND ALL AVAILABLE BAMBOOHR INTEGRATIONS
    # ==========================================================

    base_queryset = (
        CompanyIntegration.objects
        .filter(
            provider=(
                CompanyIntegration
                .PROVIDER_BAMBOOHR
            ),
            is_connected=True,
            is_active=True,
        )
    )

    available_count = base_queryset.count()

    if available_count == 0:
        logger.info(
            "Scheduled BambooHR sync found no connected integrations."
        )

        return {
            "success": True,
            "resource": RESOURCE_ALL,
            "found": 0,
            "due": 0,
            "queued": 0,
            "skipped_recent": 0,
            "checked_at": now.isoformat(),
            "sync_interval_minutes": int(
                BAMBOOHR_SCHEDULED_SYNC_INTERVAL.total_seconds() // 60
            ),
        }

    # ==========================================================
    # 2. SELECT ONLY INTEGRATIONS THAT ARE DUE
    # ==========================================================

    due_queryset = (
        base_queryset
        .filter(
            Q(last_synced_at__isnull=True)
            | Q(last_synced_at__lte=due_before)
        )
        .order_by(
            "last_synced_at",
            "id",
        )
    )

    integration_ids = list(
        due_queryset.values_list(
            "id",
            flat=True,
        )
    )

    due_count = len(integration_ids)
    skipped_recent = max(available_count - due_count, 0)

    # ==========================================================
    # 3. NOTHING IS DUE
    # ==========================================================

    if not integration_ids:
        logger.info(
            (
                "Scheduled BambooHR dispatcher found no integrations "
                "due for synchronization. connected=%s skipped_recent=%s"
            ),
            available_count,
            skipped_recent,
        )

        return {
            "success": True,
            "resource": RESOURCE_ALL,
            "found": available_count,
            "due": 0,
            "queued": 0,
            "skipped_recent": skipped_recent,
            "checked_at": now.isoformat(),
            "sync_interval_minutes": int(
                BAMBOOHR_SCHEDULED_SYNC_INTERVAL.total_seconds() // 60
            ),
        }

    # ==========================================================
    # 4. QUEUE EACH DUE COMPANY INDEPENDENTLY
    # ==========================================================

    queued = 0

    for integration_id in integration_ids:
        sync_single_bamboohr_integration.delay(
            str(integration_id)
        )
        queued += 1

    logger.info(
        (
            "Queued %s/%s BambooHR integration(s) for scheduled sync. "
            "skipped_recent=%s interval_minutes=%s"
        ),
        queued,
        available_count,
        skipped_recent,
        int(BAMBOOHR_SCHEDULED_SYNC_INTERVAL.total_seconds() // 60),
    )

    return {
        "success": True,
        "resource": RESOURCE_ALL,
        "found": available_count,
        "due": due_count,
        "queued": queued,
        "skipped_recent": skipped_recent,
        "checked_at": now.isoformat(),
        "due_before": due_before.isoformat(),
        "sync_interval_minutes": int(
            BAMBOOHR_SCHEDULED_SYNC_INTERVAL.total_seconds() // 60
        ),
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

