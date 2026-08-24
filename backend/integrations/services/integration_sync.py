import logging

from datetime import timedelta

from django.utils import timezone

from audit_logs.utils import (
    create_integration_audit_log,
)

from integrations.models import (
    IntegrationCredential,
    IntegrationSyncLog,
)

from integrations.encryption_services import (
    decrypt_integration_config,
    encrypt_integration_config,
)

from integrations.services.bamboohr import (
    BambooHRClient,
    BambooHROAuthService,
    BambooHRAuthenticationError,
    BambooHRPermissionError,
    BambooHRConnectionError,
    BambooHRIntegrationError,
)

from integrations.services.bamboohr_sync import (
    sync_bamboohr_departments,
    sync_bamboohr_employees_only,
    sync_bamboohr_managers,
    sync_bamboohr_all,
)


logger = logging.getLogger(__name__)


# ==============================================================
# BAMBOOHR SYNC RESOURCES
# ==============================================================

RESOURCE_DEPARTMENTS = "DEPARTMENTS"
RESOURCE_EMPLOYEES = "EMPLOYEES"
RESOURCE_MANAGERS = "MANAGERS"
RESOURCE_ALL = "ALL"


VALID_BAMBOOHR_SYNC_RESOURCES = {
    RESOURCE_DEPARTMENTS,
    RESOURCE_EMPLOYEES,
    RESOURCE_MANAGERS,
    RESOURCE_ALL,
}


class IntegrationSyncError(Exception):
    """
    Base exception for integration synchronization errors.
    """


# ==============================================================
# MAIN BAMBOOHR SYNC RUNNER
# ==============================================================


def run_bamboohr_sync(
    *,
    integration,
    trigger=IntegrationSyncLog.TRIGGER_MANUAL,
    resource=RESOURCE_ALL,
):
    """
    Run BambooHR -> ZepEx synchronization.

    Supported resources:

        DEPARTMENTS
        EMPLOYEES
        MANAGERS
        ALL

    OAuth flow:

        Read encrypted OAuth credentials
                    ↓
        Create BambooHR client
                    ↓
        Fetch BambooHR employees
                    ↓
        Access token expired?
              ↓             ↓
             YES            NO
              ↓             ↓
        Refresh token       Continue
              ↓
        Save new encrypted tokens
              ↓
        Retry BambooHR request
                    ↓
        Run requested resource sync
                    ↓
        Update CompanyIntegration
                    ↓
        Update IntegrationSyncLog
                    ↓
        Create AuditLog
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
    # 2. VALIDATE RESOURCE
    # ==========================================================

    resource = str(
        resource or RESOURCE_ALL
    ).strip().upper()

    if (
        resource
        not in VALID_BAMBOOHR_SYNC_RESOURCES
    ):

        raise IntegrationSyncError(
            (
                "Invalid BambooHR sync resource. "
                "Allowed resources are: "
                "DEPARTMENTS, EMPLOYEES, "
                "MANAGERS, ALL."
            )
        )

    # ==========================================================
    # 3. CREATE SYNC LOG
    # ==========================================================

    sync_log = (
        IntegrationSyncLog.objects.create(
            integration=integration,
            trigger=trigger,
            status=(
                IntegrationSyncLog
                .STATUS_RUNNING
            ),
            stats={
                "resource": resource,
            },
        )
    )

    # ==========================================================
    # 4. AUDIT — SYNC STARTED
    # ==========================================================

    create_integration_audit_log(
        company=integration.company,
        integration=integration,
        provider="BAMBOOHR",
        action="BAMBOOHR_SYNC_STARTED",
        action_by=None,
        message=(
            f"BambooHR {resource.lower()} "
            "synchronization started."
        ),
        metadata={
            "trigger": trigger,
            "resource": resource,
            "sync_log_id": str(
                sync_log.id
            ),
        },
    )

    try:

        # ======================================================
        # 5. READ CREDENTIALS
        # ======================================================

        try:

            credential = (
                integration.credential
            )

        except Exception as exc:

            raise IntegrationSyncError(
                (
                    "Integration credentials "
                    "are not configured."
                )
            ) from exc

        if not credential.encrypted_config:

            raise IntegrationSyncError(
                "Integration credentials are empty."
            )

        try:

            config = (
                decrypt_integration_config(
                    credential.encrypted_config
                )
            )

        except Exception as exc:

            raise IntegrationSyncError(
                (
                    "Unable to decrypt "
                    "BambooHR credentials."
                )
            ) from exc

        # ======================================================
        # 6. VALIDATE OAUTH CONFIG
        # ======================================================

        company_domain = (
            config.get(
                "company_domain"
            )
            or ""
        ).strip()

        access_token = (
            config.get(
                "access_token"
            )
            or ""
        ).strip()

        refresh_token = (
            config.get(
                "refresh_token"
            )
            or ""
        ).strip()

        if not company_domain:

            raise IntegrationSyncError(
                (
                    "BambooHR company domain "
                    "is missing."
                )
            )

        if not access_token:

            raise IntegrationSyncError(
                (
                    "BambooHR OAuth access token "
                    "is missing."
                )
            )

        # ======================================================
        # 7. CREATE BAMBOOHR CLIENT
        # ======================================================

        client = BambooHRClient(
            company_domain=company_domain,
            access_token=access_token,
        )

        logger.info(
            (
                "Starting BambooHR sync. "
                "company=%s integration=%s "
                "trigger=%s resource=%s"
            ),
            integration.company_id,
            integration.id,
            trigger,
            resource,
        )

        # ======================================================
        # 8. FETCH BAMBOOHR EMPLOYEES
        # ======================================================

        try:

            employees = (
                client.get_all_employees()
            )

        # ======================================================
        # ACCESS TOKEN EXPIRED
        # ======================================================

        except BambooHRAuthenticationError:

            logger.info(
                (
                    "BambooHR access token "
                    "expired. Attempting refresh. "
                    "integration=%s"
                ),
                integration.id,
            )

            if not refresh_token:

                raise BambooHRAuthenticationError(
                    (
                        "BambooHR access token "
                        "expired and no refresh "
                        "token is available."
                    )
                )

            # ==================================================
            # 8A. REFRESH ACCESS TOKEN
            # ==================================================

            oauth_service = (
                BambooHROAuthService(
                    company_domain=(
                        company_domain
                    ),
                )
            )

            token_data = (
                oauth_service
                .refresh_access_token(
                    refresh_token=(
                        refresh_token
                    ),
                )
            )

            new_access_token = (
                token_data.get(
                    "access_token"
                )
                or ""
            ).strip()

            if not new_access_token:

                raise (
                    BambooHRAuthenticationError(
                        (
                            "BambooHR token refresh "
                            "did not return an "
                            "access token."
                        )
                    )
                )

            # ==================================================
            # 8B. REFRESH TOKEN ROTATION
            # ==================================================

            new_refresh_token = (
                token_data.get(
                    "refresh_token"
                )
                or refresh_token
            )

            expires_in = (
                token_data.get(
                    "expires_in"
                )
            )

            # ==================================================
            # 8C. UPDATE ENCRYPTED CONFIG
            # ==================================================

            config[
                "access_token"
            ] = new_access_token

            config[
                "refresh_token"
            ] = new_refresh_token

            config[
                "token_type"
            ] = (
                token_data.get(
                    "token_type"
                )
                or config.get(
                    "token_type"
                )
                or "Bearer"
            )

            if token_data.get(
                "scope"
            ):

                config[
                    "scope"
                ] = token_data.get(
                    "scope"
                )

            if expires_in:

                config[
                    "access_token_expires_at"
                ] = (
                    timezone.now()
                    + timedelta(
                        seconds=int(
                            expires_in
                        )
                    )
                ).isoformat()

            else:

                config[
                    "access_token_expires_at"
                ] = None

            encrypted_config = (
                encrypt_integration_config(
                    config
                )
            )

            (
                IntegrationCredential.objects
                .update_or_create(
                    integration=integration,
                    defaults={
                        "encrypted_config": (
                            encrypted_config
                        ),
                    },
                )
            )

            logger.info(
                (
                    "BambooHR OAuth token "
                    "refreshed successfully. "
                    "integration=%s"
                ),
                integration.id,
            )

            # ==================================================
            # 8D. CREATE CLIENT WITH NEW TOKEN
            # ==================================================

            client = BambooHRClient(
                company_domain=company_domain,
                access_token=(
                    new_access_token
                ),
            )

            # ==================================================
            # 8E. RETRY FETCH
            # ==================================================

            employees = (
                client.get_all_employees()
            )

        logger.info(
            (
                "Fetched %s BambooHR employees "
                "for company=%s resource=%s."
            ),
            len(employees),
            integration.company_id,
            resource,
        )

        # ======================================================
        # 9. RUN REQUESTED RESOURCE SYNC
        # ======================================================

        if resource == RESOURCE_DEPARTMENTS:

            sync_result = (
                sync_bamboohr_departments(
                    integration=integration,
                    employees=employees,
                )
            )

        elif resource == RESOURCE_EMPLOYEES:

            sync_result = (
                sync_bamboohr_employees_only(
                    integration=integration,
                    employees=employees,
                )
            )

        elif resource == RESOURCE_MANAGERS:

            sync_result = (
                sync_bamboohr_managers(
                    integration=integration,
                    employees=employees,
                )
            )

        elif resource == RESOURCE_ALL:

            sync_result = (
                sync_bamboohr_all(
                    integration=integration,
                    employees=employees,
                )
            )

        else:

            # Defensive fallback.
            raise IntegrationSyncError(
                (
                    "Unsupported BambooHR "
                    "sync resource."
                )
            )

        # ======================================================
        # 10. READ RESULT
        # ======================================================

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
        # 11. CHECK SERVICE RESULT
        # ======================================================

        if not sync_result.get(
            "success",
            False,
        ):

            raise IntegrationSyncError(
                (
                    "BambooHR "
                    f"{resource.lower()} "
                    "synchronization did not "
                    "complete successfully."
                )
            )

        # ======================================================
        # 12. UPDATE COMPANY INTEGRATION
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
        # 13. CALCULATE CREATED COUNT
        # ======================================================

        records_created = (
            stats.get(
                "users_created",
                0,
            )
            + stats.get(
                "profiles_created",
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
            + stats.get(
                "managers_mapped",
                0,
            )
            + stats.get(
                "department_managers_mapped",
                0,
            )
        )

        # ======================================================
        # 14. CALCULATE UPDATED COUNT
        # ======================================================

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

        # ======================================================
        # 15. CALCULATE SKIPPED COUNT
        # ======================================================

        records_skipped = (
            stats.get(
                "skipped",
                0,
            )
        )

        # ======================================================
        # 16. UPDATE SYNC LOG
        # ======================================================

        sync_log.status = (
            IntegrationSyncLog
            .STATUS_SUCCESS
        )

        sync_log.records_received = (
            len(employees)
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

        sync_log.stats = {
            "resource": resource,
            **stats,
        }

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
        # 17. AUDIT — SYNC COMPLETED
        # ======================================================

        create_integration_audit_log(
            company=integration.company,
            integration=integration,
            provider="BAMBOOHR",
            action="BAMBOOHR_SYNC_COMPLETED",
            action_by=None,
            message=(
                f"BambooHR {resource.lower()} "
                "synchronization completed "
                "successfully."
            ),
            metadata={
                "trigger": trigger,
                "resource": resource,

                "sync_log_id": str(
                    sync_log.id
                ),

                "company_domain": (
                    company_domain
                ),

                "records_received": (
                    len(employees)
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
                "resource=%s received=%s "
                "created=%s updated=%s "
                "skipped=%s"
            ),
            integration.company_id,
            integration.id,
            resource,
            len(employees),
            records_created,
            records_updated,
            records_skipped,
        )

        # ======================================================
        # 18. RESPONSE
        # ======================================================

        return {
            "success": True,

            "integration_id": str(
                integration.id
            ),

            "provider": (
                integration.provider
            ),

            "resource": resource,

            "trigger": trigger,

            "last_synced_at": (
                integration.last_synced_at
            ),

            "records": {
                "received": len(
                    employees
                ),
                "created": (
                    records_created
                ),
                "updated": (
                    records_updated
                ),
                "skipped": (
                    records_skipped
                ),
            },

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
            resource=resource,
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
            resource=resource,
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
            resource=resource,
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
            resource=resource,
        )

    # ==========================================================
    # CONFIGURATION / SYNC FAILURE
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
            resource=resource,
        )

    # ==========================================================
    # UNKNOWN FAILURE
    # ==========================================================

    except Exception as exc:

        logger.exception(
            (
                "Unexpected BambooHR sync failure. "
                "integration=%s company=%s "
                "resource=%s"
            ),
            integration.id,
            integration.company_id,
            resource,
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
            resource=resource,
        )


# ==============================================================
# FAILURE HANDLER
# ==============================================================


def _handle_sync_failure(
    *,
    integration,
    sync_log,
    error,
    error_type,
    trigger=None,
    resource=None,
):
    """
    Store failed synchronization result in:

    - CompanyIntegration
    - IntegrationSyncLog
    - AuditLog
    """

    now = timezone.now()

    logger.error(
        (
            "Integration sync failed. "
            "company=%s integration=%s "
            "resource=%s error_type=%s "
            "error=%s"
        ),
        integration.company_id,
        integration.id,
        resource,
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
        IntegrationSyncLog
        .STATUS_FAILED
    )

    sync_log.error_message = (
        error
    )

    sync_log.stats = {
        **(
            sync_log.stats
            if isinstance(
                sync_log.stats,
                dict,
            )
            else {}
        ),
        "resource": resource,
    }

    sync_log.errors = [
        {
            "type": error_type,
            "resource": resource,
            "message": error,
        }
    ]

    sync_log.completed_at = now

    sync_log.save(
        update_fields=[
            "status",
            "stats",
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
            f"BambooHR "
            f"{str(resource or 'ALL').lower()} "
            "synchronization failed."
        ),
        metadata={
            "trigger": trigger,
            "resource": resource,

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

        "resource": resource,

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