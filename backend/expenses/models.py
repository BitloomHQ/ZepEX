import uuid

from django.db import models

from tenants.models import Company, Department, UserProfile


class ExpenseReport(models.Model):

    STATUS_DRAFT = "DRAFT"
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_PAID = "PAID"

    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_PAID, "Paid"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="expense_reports"
    )

    employee = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="expense_reports"
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="expense_reports"
    )

    month = models.DateField()

    status = models.CharField(
        max_length=40,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT
    )

    # ⭐ NEW
    is_auto_approved = models.BooleanField(
        default=False
    )

    # ⭐ NEW
    auto_approved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    submitted_at = models.DateTimeField(
        null=True,
        blank=True
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    paid_notes = models.TextField(
        blank=True,
        null=True
    )

    current_workflow_step = models.ForeignKey(
        "ApprovalWorkflowStep",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_reports"
    )

    workflow_completed = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )
    current_approver = models.ForeignKey(
    UserProfile,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="pending_expense_reports"
)

    class Meta:
        unique_together = (
            "company",
            "employee",
            "month",
        )

        ordering = [
            "-month",
            "-created_at",
        ]

    def __str__(self):
        return f"{self.employee.user.email} - {self.month}"


class ExpenseSubmission(models.Model):
    SOURCE_EMAIL = "EMAIL"
    SOURCE_WEB = "WEB_UPLOAD"

    SOURCE_CHOICES = (
        (SOURCE_EMAIL, "Email"),
        (SOURCE_WEB, "Web Upload"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    report = models.ForeignKey(
        ExpenseReport,
        on_delete=models.CASCADE,
        related_name="submissions",
        null=True,
        blank=True
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="expense_submissions"
    )

    employee = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="expense_submissions"
    )

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES
    )

    email_subject = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.employee.user.email} - {self.source}"


class ExpenseReceipt(models.Model):

    STATUS_DRAFT = "DRAFT"
    STATUS_AI_PROCESSING = "AI_PROCESSING"
    STATUS_AI_PROCESSED = "AI_PROCESSED"
    STATUS_VALID = "VALID"
    STATUS_POLICY_VIOLATION = "POLICY_VIOLATION"
    STATUS_PENDING_APPROVAL = "PENDING_APPROVAL"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_PAID = "PAID"

    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_AI_PROCESSING, "AI Processing"),
        (STATUS_AI_PROCESSED, "AI Processed"),
        (STATUS_VALID, "Valid"),
        (STATUS_POLICY_VIOLATION, "Policy Violation"),
        (STATUS_PENDING_APPROVAL, "Pending Approval"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_PAID, "Paid"),
    )

    # -----------------------------
    # AI Processing Status
    # -----------------------------

    AI_PENDING = "AI_PENDING"
    AI_PROCESSING = "AI_PROCESSING"
    AI_COMPLETED = "AI_COMPLETED"
    AI_RETRY_REQUIRED = "AI_RETRY_REQUIRED"
    AI_FAILED = "AI_FAILED"

    AI_STATUS_CHOICES = (
        (AI_PENDING, "AI Pending"),
        (AI_PROCESSING, "AI Processing"),
        (AI_COMPLETED, "AI Completed"),
        (AI_RETRY_REQUIRED, "AI Retry Required"),
        (AI_FAILED, "AI Failed"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    report = models.ForeignKey(
        ExpenseReport,
        on_delete=models.CASCADE,
        related_name="receipts",
        null=True,
        blank=True
    )

    submission = models.ForeignKey(
        ExpenseSubmission,
        on_delete=models.CASCADE,
        related_name="receipts"
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="expense_receipts"
    )

    employee = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="expense_receipts"
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="expense_receipts"
    )

    receipt_file = models.FileField(
        upload_to="receipts/%Y/%m/%d/"
    )

    vendor_name = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    invoice_date = models.DateField(
        blank=True,
        null=True
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    currency = models.CharField(
        max_length=10,
        default="INR"
    )

    status = models.CharField(
        max_length=40,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT
    )

    ai_status = models.CharField(
        max_length=40,
        choices=AI_STATUS_CHOICES,
        default=AI_PENDING
    )

    ai_error_message = models.TextField(
        blank=True,
        null=True
    )

    ai_retry_count = models.IntegerField(
        default=0
    )
    ai_confidence = models.DecimalField(
    max_digits=4,
    decimal_places=2,
    default=0,
    )

    policy_violation_reason = models.TextField(
        blank=True,
        null=True
    )

    has_duplicate_violation = models.BooleanField(
        default=False
    )

    has_old_bill_violation = models.BooleanField(
        default=False
    )

    has_amount_violation = models.BooleanField(
        default=False
    )

    has_any_violation = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    # -----------------------------
    # Original Receipt Currency
    # -----------------------------

    original_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    original_currency = models.CharField(
        max_length=3,
        default="INR"
    )


    # -----------------------------
    # Company Reimbursement Currency
    # -----------------------------

    company_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    company_currency = models.CharField(
        max_length=3,
        default="INR"
    )

    receipt_fingerprint = models.JSONField(
    default=dict,
    blank=True,
)

    fingerprint_hash = models.CharField(
    max_length=255,
    blank=True,
    db_index=True,
)

    # -----------------------------
    # Exchange Information
    # -----------------------------

    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True
    )

    exchange_rate_date = models.DateTimeField(
        null=True,
        blank=True
    )
    ai_extracted_data = models.JSONField(
    default=dict,
    blank=True,
    )

    original_language = models.CharField(
    max_length=100,
    null=True,
    blank=True,
)

    original_language_code = models.CharField(
    max_length=20,
    null=True,
    blank=True,
)

    output_language = models.CharField(
    max_length=100,
    null=True,
    blank=True,
)

    output_language_code = models.CharField(
    max_length=20,
    null=True,
    blank=True,
)

    exchange_rate_provider = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    linked_receipt = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="related_receipts",
    )

    reference_number = models.CharField(
        max_length=150,
        blank=True,
        default="",
        db_index=True,
    )

    reference_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    linked_reference_number = models.CharField(
        max_length=150,
        blank=True,
        default="",
        db_index=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

    def __str__(self):
        return (
            f"{self.employee.user.email} - "
            f"{self.vendor_name or 'Receipt'} - "
            f"{self.total_amount}"
        )

class ExpenseLineItem(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    receipt = models.ForeignKey(
        ExpenseReceipt,
        on_delete=models.CASCADE,
        related_name="line_items"
    )

    description = models.TextField(
        blank=True,
        default="",
    )

    category = models.CharField(
        max_length=100
    )

    vendor = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    bill_date = models.DateField(
        blank=True,
        null=True
    )

    is_violating = models.BooleanField(
        default=False
    )

    violation_reason = models.TextField(
        blank=True,
        null=True
    )

    subcategory = models.CharField(
        max_length=100,
        blank=True,
    )

    # ---------------------------------
    # Approval-stage removal / restore
    # ---------------------------------

    is_removed = models.BooleanField(
        default=False
    )

    removed_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="removed_expense_line_items"
    )

    removed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    removal_reason = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.category} - {self.amount}"

class ApprovalHistory(models.Model):

    ACTION_REPORT_SUBMITTED = "REPORT_SUBMITTED"

    ACTION_STEP_APPROVED = "STEP_APPROVED"
    ACTION_STEP_REJECTED = "STEP_REJECTED"

    ACTION_RECEIPT_APPROVED = "RECEIPT_APPROVED"
    ACTION_RECEIPT_REJECTED = "RECEIPT_REJECTED"

    ACTION_LINE_ITEM_UPDATED = "LINE_ITEM_UPDATED"
    ACTION_LINE_ITEM_REMOVED = "LINE_ITEM_REMOVED"
    ACTION_LINE_ITEM_RESTORED = "LINE_ITEM_RESTORED"

    ACTION_PAID = "PAID"

    ACTION_CHOICES = (
        (ACTION_REPORT_SUBMITTED, "Report Submitted"),
        (ACTION_STEP_APPROVED, "Step Approved"),
        (ACTION_STEP_REJECTED, "Step Rejected"),
        (ACTION_RECEIPT_APPROVED, "Receipt Approved"),
        (ACTION_RECEIPT_REJECTED, "Receipt Rejected"),
        (ACTION_LINE_ITEM_UPDATED, "Line Item Updated"),
        (ACTION_LINE_ITEM_REMOVED, "Line Item Removed"),
        (ACTION_LINE_ITEM_RESTORED, "Line Item Restored"),
        (ACTION_PAID, "Paid"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    report = models.ForeignKey(
        ExpenseReport,
        on_delete=models.CASCADE,
        related_name="approval_history",
        null=True,
        blank=True
    )

    receipt = models.ForeignKey(
        ExpenseReceipt,
        on_delete=models.CASCADE,
        related_name="approval_history",
        null=True,
        blank=True
    )

    line_item = models.ForeignKey(
        ExpenseLineItem,
        on_delete=models.SET_NULL,
        related_name="approval_history",
        null=True,
        blank=True
    )

    action_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_actions"
    )

    action = models.CharField(
        max_length=40,
        choices=ACTION_CHOICES
    )

    comments = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        target = (
            self.line_item_id
            or self.receipt_id
            or self.report_id
        )
        return f"{target} - {self.action}"
    
from tenants.models import CompanyRole
class ApprovalWorkflow(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="approval_workflows"
    )

    name = models.CharField(
        max_length=100,
        default="Workflow"
    )

    start_role = models.ForeignKey(
        CompanyRole,
        on_delete=models.CASCADE,
        related_name="starting_workflows",
        null=True,
        blank=True
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        unique_together = (
            "company",
            "start_role",
        )

    def __str__(self):
        return (
            f"{self.company.name} - "
            f"{self.start_role.name if self.start_role else 'No Start Role'}"
        )


class ApprovalWorkflowStep(models.Model):

    ROUTING_DEPARTMENT = "DEPARTMENT"
    ROUTING_COMPANY = "COMPANY"

    ROUTING_CHOICES = (
        (ROUTING_DEPARTMENT, "Department Based"),
        (ROUTING_COMPANY, "Company Wide"),
    )

    APPROVER_REPORTING_MANAGER = "REPORTING_MANAGER"
    APPROVER_DEPARTMENT_MANAGER = "DEPARTMENT_MANAGER"
    APPROVER_COMPANY_ROLE = "COMPANY_ROLE"
    APPROVER_SPECIFIC_USER = "SPECIFIC_USER"

    APPROVER_TYPE_CHOICES = (
        (APPROVER_REPORTING_MANAGER, "Reporting Manager"),
        (APPROVER_DEPARTMENT_MANAGER, "Department Manager"),
        (APPROVER_COMPANY_ROLE, "Company Role"),
        (APPROVER_SPECIFIC_USER, "Specific User"),
    )

    workflow = models.ForeignKey(
        ApprovalWorkflow,
        on_delete=models.CASCADE,
        related_name="steps"
    )

    step_order = models.PositiveIntegerField()

    approver_type = models.CharField(
        max_length=30,
        choices=APPROVER_TYPE_CHOICES,
        default=APPROVER_COMPANY_ROLE
    )

    approver_role = models.ForeignKey(
        "tenants.CompanyRole",
        on_delete=models.PROTECT,
        related_name="workflow_steps",
        null=True,
        blank=True
    )

    specific_user = models.ForeignKey(
        "tenants.UserProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="specific_workflow_steps"
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workflow_steps"
    )

    routing_type = models.CharField(
        max_length=20,
        choices=ROUTING_CHOICES,
        default=ROUTING_COMPANY
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["step_order"]

        unique_together = (
            "workflow",
            "step_order"
        )

    def __str__(self):
        return (
            f"{self.workflow.company.name} | "
            f"{self.workflow.start_role.name} | "
            f"Step {self.step_order}"
        )

class DuplicateReceiptLog(models.Model):

    DUPLICATE_SAME_EMPLOYEE = "SAME_EMPLOYEE"
    DUPLICATE_CROSS_EMPLOYEE = "CROSS_EMPLOYEE"

    DUPLICATE_TYPE_CHOICES = (
        (DUPLICATE_SAME_EMPLOYEE, "Same Employee"),
        (DUPLICATE_CROSS_EMPLOYEE, "Cross Employee"),
    )

    original_receipt = models.ForeignKey(
        ExpenseReceipt,
        on_delete=models.CASCADE,
        related_name="original_duplicate_logs"
    )

    duplicate_receipt = models.ForeignKey(
        ExpenseReceipt,
        on_delete=models.CASCADE,
        related_name="duplicate_logs"
    )

    duplicate_type = models.CharField(
        max_length=30,
        choices=DUPLICATE_TYPE_CHOICES,
        default=DUPLICATE_SAME_EMPLOYEE
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.duplicate_type}: {self.original_receipt.id} -> {self.duplicate_receipt.id}"    



class IncomingEmail(models.Model):
    message_id = models.CharField(
        max_length=500,
        unique=True
    )

    sender_email = models.EmailField()

    recipient_email = models.EmailField()

    subject = models.CharField(
        max_length=500
    )

    processed = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.subject

class ExpenseAttachment(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    line_item = models.ForeignKey(
        ExpenseLineItem,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    receipt = models.ForeignKey(
        ExpenseReceipt,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    file = models.FileField(
        upload_to="expense_attachments/%Y/%m/%d/",
    )

    attachment_type = models.CharField(
        max_length=50,
        default="receipt",
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-uploaded_at",
        ]

    def __str__(self):
        return (
            f"{self.attachment_type} - "
            f"{self.line_item.description}"
        )

class ExpenseAuditTrail(models.Model):

    ACTION_RECEIPT_UPLOADED = "RECEIPT_UPLOADED"
    ACTION_AI_STARTED = "AI_STARTED"
    ACTION_AI_COMPLETED = "AI_COMPLETED"
    ACTION_LINE_ITEMS_CREATED = "LINE_ITEMS_CREATED"
    ACTION_DUPLICATE_CHECK = "DUPLICATE_CHECK"
    ACTION_RECEIPT_LINKED = "RECEIPT_LINKED"
    ACTION_POLICY_VALIDATED = "POLICY_VALIDATED"
    ACTION_APPROVAL_STARTED = "APPROVAL_STARTED"
    ACTION_APPROVED = "APPROVED"
    ACTION_REJECTED = "REJECTED"
    ACTION_PAID = "PAID"

    ACTION_CHOICES = (
        (ACTION_RECEIPT_UPLOADED, "Receipt Uploaded"),
        (ACTION_AI_STARTED, "AI Started"),
        (ACTION_AI_COMPLETED, "AI Completed"),
        (ACTION_LINE_ITEMS_CREATED, "Line Items Created"),
        (ACTION_DUPLICATE_CHECK, "Duplicate Check"),
        (ACTION_RECEIPT_LINKED, "Receipt Linked"),
        (ACTION_POLICY_VALIDATED, "Policy Validated"),
        (ACTION_APPROVAL_STARTED, "Approval Started"),
        (ACTION_APPROVED, "Approved"),
        (ACTION_REJECTED, "Rejected"),
        (ACTION_PAID, "Paid"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    receipt = models.ForeignKey(
        ExpenseReceipt,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )

    action = models.CharField(
        max_length=100,
        choices=ACTION_CHOICES,
    )

    performed_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    remarks = models.TextField(
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

    def __str__(self):
        return f"{self.receipt.id} - {self.action}"