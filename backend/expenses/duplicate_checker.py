from .models import ExpenseReceipt


def find_duplicate_receipt(
    *,
    receipt,
):
    """
    Finds an existing duplicate receipt.

    Priority:
    1. Fingerprint hash
    2. Reference number
    3. Vendor + Date + Amount
    """

    # ----------------------------------
    # 1. Fingerprint Match
    # ----------------------------------

    if receipt.fingerprint_hash:

        duplicate = (
            ExpenseReceipt.objects.filter(
                company=receipt.company,
                fingerprint_hash=receipt.fingerprint_hash,
            )
            .exclude(id=receipt.id)
            .first()
        )

        if duplicate:
            return duplicate

    # ----------------------------------
    # 2. Reference Number Match
    # ----------------------------------

    if receipt.reference_number:

        duplicate = (
            ExpenseReceipt.objects.filter(
                company=receipt.company,
                reference_number=receipt.reference_number,
            )
            .exclude(id=receipt.id)
            .first()
        )

        if duplicate:
            return duplicate

    # ----------------------------------
    # 3. Vendor + Date + Amount
    # ----------------------------------

    if (
        receipt.vendor_name
        and receipt.invoice_date
        and receipt.original_amount
    ):

        duplicate = (
            ExpenseReceipt.objects.filter(
                company=receipt.company,
                vendor_name__iexact=receipt.vendor_name,
                invoice_date=receipt.invoice_date,
                original_amount=receipt.original_amount,
            )
            .exclude(id=receipt.id)
            .first()
        )

        if duplicate:
            return duplicate

    return None