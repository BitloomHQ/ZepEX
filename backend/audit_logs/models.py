from django.db import models

# Create your models here.
import uuid

from django.db import models

from tenants.models import Company, UserProfile


class AuditLog(models.Model):
    ACTION_CHOICES = (
    ("RECEIPT_UPLOADED", "Receipt Uploaded"),
    ("EMAIL_RECEIPT_RECEIVED", "Email Receipt Received"),
    ("AI_PROCESSING_STARTED", "AI Processing Started"),
    ("AI_PROCESSED", "AI Processed"),

    ("REPORT_SUBMITTED", "Report Submitted"),
    ("STEP_APPROVED", "Step Approved"),
    ("STEP_REJECTED", "Step Rejected"),
    ("MARKED_PAID", "Marked Paid"),

    ("WORKFLOW_CONFIGURED", "Workflow Configured"),
    ("WORKFLOW_STEP_CREATED", "Workflow Step Created"),
    ("EMAIL_FETCH_TRIGGERED", "Email Fetch Triggered"),

    ("LINE_ITEM_DELETED", "Line Item Deleted"),
    ("RECEIPT_DELETED", "Receipt Deleted"),
    ("POLICY_UPDATED", "Policy Updated"),
    ("USER_UPDATED", "User Updated"),
    ("USER_DEACTIVATED", "User Deactivated"),
    ("USER_ACTIVATED", "User Activated"),
    ("DEPARTMENT_CREATED", "Department Created"),
    ("DEPARTMENT_UPDATED", "Department Updated"),
    ("DEPARTMENT_DEACTIVATED", "Department Deactivated"),
    ("DEPARTMENT_ACTIVATED", "Department Activated"),
    ("POLICY_RULE_UPDATED", "Policy Rule Updated"),
    ("POLICY_RULE_DEACTIVATED", "Policy Rule Deactivated"),
    ("POLICY_RULE_ACTIVATED", "Policy Rule Activated"),
    ("POLICY_RULE_DELETED", "Policy Rule Deleted"),
    ("COMPANY_DEACTIVATED", "Company Deactivated"),
    ("COMPANY_ACTIVATED", "Company Activated"),
    ("USER_DELETED", "User Deleted"),
    ("DEPARTMENT_DELETED", "Department Deleted"),
    ("DATABASE_CONNECTED", "Database Connected"),
    ("DATABASE_CONNECTION_FAILED", "Database Connection Failed"),
    ("SYNC_STARTED", "Sync Started"),
    ("SYNC_COMPLETED", "Sync Completed"),
    ("SYNC_FAILED", "Sync Failed"),
)

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="audit_logs"
    )

    action_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actions"
    )

    action = models.CharField(
        max_length=60,
        choices=ACTION_CHOICES
    )

    message = models.TextField(
        blank=True,
        null=True
    )

    metadata = models.JSONField(
        default=dict,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company.name} - {self.action}"