import logging

from .models import ExpenseReceipt
from .services import extract_receipt_with_gemini

logger = logging.getLogger(__name__)


def process_receipt(receipt_id):
    """
    Universal AI processor.

    Works for:
    - Web Upload
    - Email Upload
    - Future API Upload
    """

    try:
        receipt = (
            ExpenseReceipt.objects
            .select_related(
                "company",
                "employee",
                "report",
            )
            .get(id=receipt_id)
        )

    except ExpenseReceipt.DoesNotExist:
        return {
            "success": False,
            "error": "Receipt not found.",
            "retry_allowed": False,
        }

    logger.info(
        "Starting AI processing for receipt %s",
        receipt.id,
    )

    try:
        result = extract_receipt_with_gemini(receipt)

    except Exception as exc:
        logger.exception(
            "AI extraction raised an exception for receipt %s.",
            receipt.id,
        )

        receipt.refresh_from_db()

        return {
            "success": False,
            "receipt_id": str(receipt.id),
            "ai_status": receipt.ai_status,
            "error": str(exc),
            "retry_allowed": True,
        }

    # --------------------------------------------------
    # SAFETY CHECK
    # --------------------------------------------------
    # extract_receipt_with_gemini() must return a dict.
    # Prevent:
    #
    # AttributeError:
    # 'NoneType' object has no attribute 'get'
    # --------------------------------------------------

    if result is None:
        logger.error(
            (
                "extract_receipt_with_gemini returned None "
                "for receipt %s."
            ),
            receipt.id,
        )

        receipt.refresh_from_db()

        return {
            "success": False,
            "receipt_id": str(receipt.id),
            "ai_status": receipt.ai_status,
            "error": (
                "AI extraction completed without returning "
                "a result."
            ),
            "retry_allowed": False,
        }

    if not isinstance(result, dict):
        logger.error(
            (
                "extract_receipt_with_gemini returned invalid "
                "result type %s for receipt %s."
            ),
            type(result).__name__,
            receipt.id,
        )

        receipt.refresh_from_db()

        return {
            "success": False,
            "receipt_id": str(receipt.id),
            "ai_status": receipt.ai_status,
            "error": (
                "AI extraction returned an invalid result."
            ),
            "retry_allowed": False,
        }

    receipt.refresh_from_db()

    if result.get("success"):

        logger.info(
            "Receipt %s processed successfully.",
            receipt.id,
        )

        return {
            "success": True,
            "receipt_id": str(receipt.id),
            "receipt_status": receipt.status,
            "ai_status": receipt.ai_status,
            "has_policy_violation": (
                receipt.has_any_violation
            ),
            "policy_reason": (
                receipt.policy_violation_reason
            ),
            "result": result,
        }

    logger.error(
        "Receipt %s processing failed: %s",
        receipt.id,
        result.get("error"),
    )

    return {
        "success": False,
        "receipt_id": str(receipt.id),
        "ai_status": receipt.ai_status,
        "error": (
            result.get("error")
            or "AI processing failed."
        ),
        "retry_allowed": result.get(
            "retry_allowed",
            False,
        ),
    }