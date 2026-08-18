import logging

from .models import AuditLog


logger = logging.getLogger(__name__)


def create_audit_log(
    *,
    company,
    action,
    action_by=None,
    message="",
    metadata=None,
):
    """
    Reusable audit log creator.

    Used by:
    - expenses
    - approvals
    - workflows
    - company management
    - BambooHR integration
    - QuickBooks integration

    The helper is intentionally defensive so that an audit-log
    failure does not normally break the main business operation.
    """

    # ==========================================================
    # 1. BASIC VALIDATION
    # ==========================================================

    if not company:
        logger.warning(
            "Audit log skipped because company is missing. "
            "action=%s",
            action,
        )

        return None

    if not action:
        logger.warning(
            "Audit log skipped because action is missing. "
            "company=%s",
            getattr(
                company,
                "id",
                None,
            ),
        )

        return None

    # ==========================================================
    # 2. NORMALIZE MESSAGE
    # ==========================================================

    message = (
        str(message)
        if message is not None
        else ""
    )

    # ==========================================================
    # 3. NORMALIZE METADATA
    # ==========================================================

    if metadata is None:
        metadata = {}

    if not isinstance(
        metadata,
        dict,
    ):

        metadata = {
            "value": str(
                metadata
            )
        }

    # ==========================================================
    # 4. CREATE AUDIT LOG
    # ==========================================================

    try:

        audit_log = AuditLog.objects.create(
            company=company,
            action=action,
            action_by=action_by,
            message=message,
            metadata=metadata,
        )

        logger.info(
            (
                "Audit log created. "
                "company=%s action=%s "
                "audit_log=%s"
            ),
            getattr(
                company,
                "id",
                None,
            ),
            action,
            audit_log.id,
        )

        return audit_log

    except Exception:

        logger.exception(
            (
                "Unable to create audit log. "
                "company=%s action=%s"
            ),
            getattr(
                company,
                "id",
                None,
            ),
            action,
        )

        return None


def create_integration_audit_log(
    *,
    company,
    action,
    provider,
    action_by=None,
    message="",
    integration=None,
    metadata=None,
):
    """
    Convenience helper specifically for external integrations.

    Automatically adds:
        provider
        integration_id

    Example providers:
        BAMBOOHR
        QUICKBOOKS
    """

    integration_metadata = {
        "provider": (
            str(provider)
            if provider
            else None
        ),
    }

    if integration:

        integration_metadata[
            "integration_id"
        ] = str(
            integration.id
        )

    if metadata:

        integration_metadata.update(
            metadata
        )

    return create_audit_log(
        company=company,
        action=action,
        action_by=action_by,
        message=message,
        metadata=integration_metadata,
    )