import uuid

from django.db import models

from tenants.models import (
    Company,
    UserProfile,
)


class AuditLog(models.Model):

    ACTION_CHOICES = (

        # ======================================================
        # EXPENSE / RECEIPT
        # ======================================================

        (
            "RECEIPT_UPLOADED",
            "Receipt Uploaded",
        ),

        (
            "EMAIL_RECEIPT_RECEIVED",
            "Email Receipt Received",
        ),

        (
            "AI_PROCESSING_STARTED",
            "AI Processing Started",
        ),

        (
            "AI_PROCESSED",
            "AI Processed",
        ),

        (
            "LINE_ITEM_DELETED",
            "Line Item Deleted",
        ),

        (
            "RECEIPT_DELETED",
            "Receipt Deleted",
        ),

        # ======================================================
        # REPORT / APPROVAL
        # ======================================================

        (
            "REPORT_SUBMITTED",
            "Report Submitted",
        ),

        (
            "STEP_APPROVED",
            "Step Approved",
        ),

        (
            "STEP_REJECTED",
            "Step Rejected",
        ),

        (
            "MARKED_PAID",
            "Marked Paid",
        ),

        # ======================================================
        # WORKFLOW
        # ======================================================

        (
            "WORKFLOW_CONFIGURED",
            "Workflow Configured",
        ),

        (
            "WORKFLOW_STEP_CREATED",
            "Workflow Step Created",
        ),

        # ======================================================
        # EMAIL / IMAP
        # ======================================================

        (
            "EMAIL_FETCH_TRIGGERED",
            "Email Fetch Triggered",
        ),

        # ======================================================
        # COMPANY / USERS / DEPARTMENTS
        # ======================================================

        (
            "USER_UPDATED",
            "User Updated",
        ),

        (
            "USER_DEACTIVATED",
            "User Deactivated",
        ),

        (
            "USER_ACTIVATED",
            "User Activated",
        ),

        (
            "USER_DELETED",
            "User Deleted",
        ),

        (
            "DEPARTMENT_CREATED",
            "Department Created",
        ),

        (
            "DEPARTMENT_UPDATED",
            "Department Updated",
        ),

        (
            "DEPARTMENT_DEACTIVATED",
            "Department Deactivated",
        ),

        (
            "DEPARTMENT_ACTIVATED",
            "Department Activated",
        ),

        (
            "DEPARTMENT_DELETED",
            "Department Deleted",
        ),

        (
            "COMPANY_DEACTIVATED",
            "Company Deactivated",
        ),

        (
            "COMPANY_ACTIVATED",
            "Company Activated",
        ),

        # ======================================================
        # POLICY
        # ======================================================

        (
            "POLICY_UPDATED",
            "Policy Updated",
        ),

        (
            "POLICY_RULE_UPDATED",
            "Policy Rule Updated",
        ),

        (
            "POLICY_RULE_DEACTIVATED",
            "Policy Rule Deactivated",
        ),

        (
            "POLICY_RULE_ACTIVATED",
            "Policy Rule Activated",
        ),

        (
            "POLICY_RULE_DELETED",
            "Policy Rule Deleted",
        ),

        # ======================================================
        # DATABASE / GENERIC SYNC
        # ======================================================

        (
            "DATABASE_CONNECTED",
            "Database Connected",
        ),

        (
            "DATABASE_CONNECTION_FAILED",
            "Database Connection Failed",
        ),

        (
            "SYNC_STARTED",
            "Sync Started",
        ),

        (
            "SYNC_COMPLETED",
            "Sync Completed",
        ),

        (
            "SYNC_FAILED",
            "Sync Failed",
        ),

        # ======================================================
        # BAMBOOHR INTEGRATION
        # ======================================================

        (
            "BAMBOOHR_CONNECTED",
            "BambooHR Connected",
        ),

        (
            "BAMBOOHR_CONNECTION_FAILED",
            "BambooHR Connection Failed",
        ),

        (
            "BAMBOOHR_SYNC_STARTED",
            "BambooHR Sync Started",
        ),

        (
            "BAMBOOHR_SYNC_COMPLETED",
            "BambooHR Sync Completed",
        ),

        (
            "BAMBOOHR_SYNC_FAILED",
            "BambooHR Sync Failed",
        ),

        (
            "BAMBOOHR_DISCONNECTED",
            "BambooHR Disconnected",
        ),

        # ======================================================
        # QUICKBOOKS CONNECTION
        # ======================================================

        (
            "QUICKBOOKS_CONNECTED",
            "QuickBooks Connected",
        ),

        (
            "QUICKBOOKS_CONNECTION_FAILED",
            "QuickBooks Connection Failed",
        ),

        (
            "QUICKBOOKS_DISCONNECTED",
            "QuickBooks Disconnected",
        ),

        # ======================================================
        # QUICKBOOKS CATEGORY MAPPING
        # ======================================================

        (
            "QUICKBOOKS_MAPPING_CREATED",
            "QuickBooks Mapping Created",
        ),

        (
            "QUICKBOOKS_MAPPING_UPDATED",
            "QuickBooks Mapping Updated",
        ),

        (
            "QUICKBOOKS_MAPPING_DELETED",
            "QuickBooks Mapping Deleted",
        ),

        # ======================================================
        # QUICKBOOKS EXPORT
        # ======================================================

        (
            "QUICKBOOKS_EXPORT_QUEUED",
            "QuickBooks Export Queued",
        ),

        (
            "QUICKBOOKS_EXPORT_STARTED",
            "QuickBooks Export Started",
        ),

        (
            "QUICKBOOKS_EXPORT_SUCCESS",
            "QuickBooks Export Successful",
        ),

        (
            "QUICKBOOKS_EXPORT_FAILED",
            "QuickBooks Export Failed",
        ),

        (
            "QUICKBOOKS_EXPORT_RETRIED",
            "QuickBooks Export Retried",
        ),
    )

    # ==========================================================
    # ID
    # ==========================================================

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # ==========================================================
    # COMPANY
    # ==========================================================

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )

    # ==========================================================
    # USER WHO PERFORMED ACTION
    # ==========================================================

    action_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actions",
    )

    # ==========================================================
    # ACTION
    # ==========================================================

    action = models.CharField(
        max_length=60,
        choices=ACTION_CHOICES,
    )

    # ==========================================================
    # MESSAGE
    # ==========================================================

    message = models.TextField(
        blank=True,
        null=True,
    )

    # ==========================================================
    # METADATA
    # ==========================================================
    #
    # Examples:
    #
    # {
    #     "provider": "QUICKBOOKS",
    #     "report_id": "...",
    #     "transaction_id": "...",
    #     "amount": "23000.00"
    # }
    #
    # or:
    #
    # {
    #     "provider": "BAMBOOHR",
    #     "received": 50,
    #     "created": 10,
    #     "updated": 35,
    #     "deactivated": 2
    # }
    # ==========================================================

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    # ==========================================================
    # CREATED
    # ==========================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=[
                    "company",
                    "action",
                ],
            ),

            models.Index(
                fields=[
                    "company",
                    "created_at",
                ],
            ),
        ]

    def __str__(self):
        return (
            f"{self.company.name} - "
            f"{self.action}"
        )