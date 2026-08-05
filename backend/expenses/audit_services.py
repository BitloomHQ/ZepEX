from .models import ExpenseAuditTrail


def create_audit_log(
    *,
    receipt,
    action,
    performed_by=None,
    remarks="",
    metadata=None,
):
    """
    Creates an audit log entry for a receipt.
    """

    ExpenseAuditTrail.objects.create(
        receipt=receipt,
        action=action,
        performed_by=performed_by,
        remarks=remarks,
        metadata=metadata or {},
    )