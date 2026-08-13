import logging

from django.db import transaction

from audit_logs.utils import create_audit_log

from .models import ExpenseReceipt


logger = logging.getLogger(__name__)


def queue_receipt_ai_processing(
    receipt_id,
    company,
    action_by,
    report_id,
):
    """
    Queue receipt AI extraction using Celery.

    Used by:
    - Web receipt upload
    - Email receipt upload

    The Celery task is imported lazily inside
    queue_after_commit() to avoid circular imports.
    """

    receipt_id = str(receipt_id)

    report_id = (
        str(report_id)
        if report_id
        else None
    )

    # ==========================================================
    # 1. MAKE SURE RECEIPT EXISTS
    # ==========================================================

    try:
        receipt = (
            ExpenseReceipt.objects
            .select_related(
                "submission",
                "report",
                "company",
                "employee",
            )
            .get(
                id=receipt_id
            )
        )

    except ExpenseReceipt.DoesNotExist:
        return {
            "success": False,
            "queued": False,
            "error": "Receipt not found.",
        }

    # ==========================================================
    # 2. QUEUE CELERY TASK AFTER DATABASE COMMIT
    # ==========================================================

    def queue_after_commit():

        try:

            # --------------------------------------------------
            # LAZY IMPORT
            #
            # Important:
            # Do NOT import this at the top of ai_queue.py.
            # This prevents the circular import:
            #
            # ai_queue
            #   -> tasks
            #   -> email_fetch_runner
            #   -> email_processor
            #   -> ai_queue
            # --------------------------------------------------

            from .tasks import process_receipt_task

            task = process_receipt_task.delay(
                receipt_id
            )

            logger.info(
                "AI processing queued. "
                "receipt=%s task_id=%s",
                receipt_id,
                task.id,
            )

            # ==================================================
            # AUDIT LOG — QUEUED
            # ==================================================

            try:

                create_audit_log(
                    company=company,
                    action="AI_PROCESSING_QUEUED",
                    action_by=action_by,
                    message=(
                        "Receipt queued for AI extraction."
                    ),
                    metadata={
                        "receipt_id": receipt_id,
                        "report_id": report_id,
                        "task_id": task.id,
                        "ai_status": receipt.ai_status,
                        "source": (
                            receipt.submission.source
                            if receipt.submission
                            else None
                        ),
                    },
                )

            except Exception:

                logger.exception(
                    "Unable to create "
                    "AI_PROCESSING_QUEUED audit log."
                )

        except Exception as exc:

            logger.exception(
                "Unable to queue AI processing "
                "for receipt %s.",
                receipt_id,
            )

            # ==================================================
            # AUDIT LOG — QUEUE FAILED
            # ==================================================

            try:

                create_audit_log(
                    company=company,
                    action="AI_PROCESSING_QUEUE_FAILED",
                    action_by=action_by,
                    message=str(exc),
                    metadata={
                        "receipt_id": receipt_id,
                        "report_id": report_id,
                        "error": str(exc),
                    },
                )

            except Exception:

                logger.exception(
                    "Unable to create "
                    "AI_PROCESSING_QUEUE_FAILED audit log."
                )

    # ==========================================================
    # 3. RUN ONLY AFTER DB COMMIT
    # ==========================================================

    transaction.on_commit(
        queue_after_commit
    )

    # ==========================================================
    # 4. RESPONSE
    # ==========================================================

    return {
        "success": True,
        "queued": True,
        "receipt_id": receipt_id,
    }