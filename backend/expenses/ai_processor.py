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
        receipt = ExpenseReceipt.objects.select_related(
            "company",
            "employee",
            "report",
        ).get(id=receipt_id)

    except ExpenseReceipt.DoesNotExist:
        return {
            "success": False,
            "error": "Receipt not found.",
        }

    logger.info(
        "Starting AI processing for receipt %s",
        receipt.id,
    )

    result = extract_receipt_with_gemini(receipt)

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
            "has_policy_violation": receipt.has_any_violation,
            "policy_reason": receipt.policy_violation_reason,
            "result": result,
        }

    logger.error(
        "Receipt %s processing failed.",
        receipt.id,
    )

    return {
        "success": False,
        "receipt_id": str(receipt.id),
        "ai_status": receipt.ai_status,
        "error": result.get("error"),
        "retry_allowed": result.get("retry_allowed", False),
    }