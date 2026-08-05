from .models import ExpenseReceipt
from django.db.models import Q


def link_receipt(receipt):
    """
    Automatically link related receipts.

    Matching priority:
    1. linked_reference_number -> reference_number
    2. reference_number -> linked_reference_number
    3. reference_number -> reference_number
    """

    reference_number = (
        receipt.reference_number or ""
    ).strip()

    linked_reference = (
        receipt.linked_reference_number or ""
    ).strip()

    if not reference_number and not linked_reference:
        return

    queryset = ExpenseReceipt.objects.filter(
        company=receipt.company,
    ).exclude(
        id=receipt.id,
    )

    linked_receipt = None

    # -------------------------------------------------
    # linked_reference -> reference_number
    # -------------------------------------------------

    if linked_reference:

        linked_receipt = queryset.filter(
            reference_number=linked_reference
        ).first()

    # -------------------------------------------------
    # reference_number -> linked_reference
    # -------------------------------------------------

    if (
        not linked_receipt
        and reference_number
    ):

        linked_receipt = queryset.filter(
            linked_reference_number=reference_number
        ).first()

    # -------------------------------------------------
    # reference_number -> reference_number
    # -------------------------------------------------

    if (
        not linked_receipt
        and reference_number
    ):

        linked_receipt = queryset.filter(
            reference_number=reference_number
        ).first()

    # -------------------------------------------------
    # Create two-way link
    # -------------------------------------------------

    if linked_receipt:

        receipt.linked_receipt = linked_receipt

        receipt.save(
            update_fields=["linked_receipt"]
        )

        if linked_receipt.linked_receipt_id != receipt.id:

            linked_receipt.linked_receipt = receipt

            linked_receipt.save(
                update_fields=["linked_receipt"]
            )