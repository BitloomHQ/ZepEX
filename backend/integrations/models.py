from django.db import models

from tenants.models import Company


class CompanyIntegration(models.Model):

    # ==========================================================
    # PROVIDERS
    # ==========================================================

    PROVIDER_BAMBOOHR = "BAMBOOHR"
    PROVIDER_RIPPLING = "RIPPLING"
    PROVIDER_WORKDAY = "WORKDAY"
    PROVIDER_ADP = "ADP"
    PROVIDER_QUICKBOOKS = "QUICKBOOKS"

    PROVIDER_CHOICES = (
        (
            PROVIDER_BAMBOOHR,
            "BambooHR",
        ),
        (
            PROVIDER_RIPPLING,
            "Rippling",
        ),
        (
            PROVIDER_WORKDAY,
            "Workday",
        ),
        (
            PROVIDER_ADP,
            "ADP",
        ),
        (
            PROVIDER_QUICKBOOKS,
            "QuickBooks",
        ),
    )

    # ==========================================================
    # COMPANY
    # ==========================================================

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="integrations",
    )

    # ==========================================================
    # PROVIDER
    # ==========================================================

    provider = models.CharField(
        max_length=30,
        choices=PROVIDER_CHOICES,
    )

    # ==========================================================
    # CONNECTION STATUS
    # ==========================================================

    is_connected = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    # ==========================================================
    # QUICKBOOKS PAYMENT ACCOUNT
    # ==========================================================

    quickbooks_payment_account_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    quickbooks_payment_account_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    quickbooks_payment_account_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    # ==========================================================
    # SYNC INFORMATION
    # ==========================================================

    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_sync_status = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    last_sync_error = models.TextField(
        null=True,
        blank=True,
    )

    # ==========================================================
    # TIMESTAMPS
    # ==========================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )
    bamboohr_webhook_id = models.CharField(
    max_length=255,
    null=True,
    blank=True,
)

    bamboohr_webhook_enabled = models.BooleanField(
    default=False,
)

    bamboohr_webhook_created_at = models.DateTimeField(
    null=True,
    blank=True,
)

    quickbooks_auto_export = models.BooleanField(
    default=False,
    help_text=(
        "Automatically export PAID expense reports "
        "to QuickBooks."
    ),
)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "company",
                    "provider",
                ],
                name=(
                    "unique_company_integration_provider"
                ),
            ),
        ]

    def __str__(self):
        return (
            f"{self.company.name} - "
            f"{self.get_provider_display()}"
        )


class IntegrationCredential(models.Model):
    """
    Stores encrypted provider credentials/configuration.

    Plain API keys, client secrets, refresh tokens,
    passwords, etc. should never be stored directly.
    """

    integration = models.OneToOneField(
        CompanyIntegration,
        on_delete=models.CASCADE,
        related_name="credential",
    )

    encrypted_config = models.TextField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return (
            f"Credentials - "
            f"{self.integration.company.name} - "
            f"{self.integration.get_provider_display()}"
        )

class IntegrationEmployeeMapping(models.Model):
    """
    Maps an employee in an external HRMS such as BambooHR
    to the corresponding ZepEx UserProfile.
    """

    integration = models.ForeignKey(
        CompanyIntegration,
        on_delete=models.CASCADE,
        related_name="employee_mappings",
    )

    user_profile = models.ForeignKey(
        "tenants.UserProfile",
        on_delete=models.CASCADE,
        related_name="integration_mappings",
    )

    external_employee_id = models.CharField(
        max_length=255,
    )

    external_email = models.EmailField(
        null=True,
        blank=True,
    )

    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "integration",
                    "external_employee_id",
                ],
                name="unique_integration_external_employee",
            ),
            models.UniqueConstraint(
                fields=[
                    "integration",
                    "user_profile",
                ],
                name="unique_integration_user_profile",
            ),
        ]

    def __str__(self):
        return (
            f"{self.integration.provider} - "
            f"{self.external_employee_id}"
        )

class IntegrationSyncLog(models.Model):

    STATUS_RUNNING = "RUNNING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = (
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    )

    TRIGGER_MANUAL = "MANUAL"
    TRIGGER_SCHEDULED = "SCHEDULED"
    TRIGGER_WEBHOOK = "WEBHOOK"

    TRIGGER_CHOICES = (
        (TRIGGER_MANUAL, "Manual"),
        (TRIGGER_SCHEDULED, "Scheduled"),
        (TRIGGER_WEBHOOK, "Webhook"),
    )

    integration = models.ForeignKey(
        CompanyIntegration,
        on_delete=models.CASCADE,
        related_name="sync_logs",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RUNNING,
    )

    trigger = models.CharField(
        max_length=20,
        choices=TRIGGER_CHOICES,
        default=TRIGGER_MANUAL,
    )

    records_received = models.PositiveIntegerField(
        default=0,
    )

    records_created = models.PositiveIntegerField(
        default=0,
    )

    records_updated = models.PositiveIntegerField(
        default=0,
    )

    records_skipped = models.PositiveIntegerField(
        default=0,
    )

    error_message = models.TextField(
        null=True,
        blank=True,
    )

    stats = models.JSONField(
        default=dict,
        blank=True,
    )

    errors = models.JSONField(
        default=list,
        blank=True,
    )

    started_at = models.DateTimeField(
        auto_now_add=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = [
            "-started_at",
        ]

    def __str__(self):
        return (
            f"{self.integration.company.name} - "
            f"{self.integration.provider} - "
            f"{self.status}"
        )

class IntegrationChangeLog(models.Model):
    """
    Stores individual changes made in ZepEx because of an
    external integration such as BambooHR.

    Examples:

        Employee created
        Department created
        Department changed
        Manager changed
        Employee activated
        Employee deactivated
        Name changed
        Email changed

    IntegrationSyncLog answers:
        "Did the synchronization succeed?"

    IntegrationChangeLog answers:
        "What exactly changed?"
    """

    # ==========================================================
    # RESOURCE TYPES
    # ==========================================================

    RESOURCE_EMPLOYEE = "EMPLOYEE"
    RESOURCE_DEPARTMENT = "DEPARTMENT"

    RESOURCE_CHOICES = (
        (
            RESOURCE_EMPLOYEE,
            "Employee",
        ),
        (
            RESOURCE_DEPARTMENT,
            "Department",
        ),
    )

    # ==========================================================
    # CHANGE TYPES
    # ==========================================================

    CHANGE_CREATED = "CREATED"
    CHANGE_UPDATED = "UPDATED"
    CHANGE_ACTIVATED = "ACTIVATED"
    CHANGE_DEACTIVATED = "DEACTIVATED"
    CHANGE_MANAGER_CHANGED = "MANAGER_CHANGED"
    CHANGE_DEPARTMENT_CHANGED = "DEPARTMENT_CHANGED"

    CHANGE_CHOICES = (
        (
            CHANGE_CREATED,
            "Created",
        ),
        (
            CHANGE_UPDATED,
            "Updated",
        ),
        (
            CHANGE_ACTIVATED,
            "Activated",
        ),
        (
            CHANGE_DEACTIVATED,
            "Deactivated",
        ),
        (
            CHANGE_MANAGER_CHANGED,
            "Manager Changed",
        ),
        (
            CHANGE_DEPARTMENT_CHANGED,
            "Department Changed",
        ),
    )

    # ==========================================================
    # INTEGRATION
    # ==========================================================

    integration = models.ForeignKey(
        CompanyIntegration,
        on_delete=models.CASCADE,
        related_name="change_logs",
    )

    # ==========================================================
    # SYNC LOG
    # ==========================================================

    sync_log = models.ForeignKey(
        IntegrationSyncLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="change_logs",
    )

    # ==========================================================
    # RESOURCE
    # ==========================================================

    resource_type = models.CharField(
        max_length=30,
        choices=RESOURCE_CHOICES,
    )

    external_resource_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
    )

    # ==========================================================
    # DISPLAY INFORMATION
    # ==========================================================

    resource_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    # ==========================================================
    # CHANGE INFORMATION
    # ==========================================================

    change_type = models.CharField(
        max_length=50,
        choices=CHANGE_CHOICES,
    )

    field_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    old_value = models.TextField(
        null=True,
        blank=True,
    )

    new_value = models.TextField(
        null=True,
        blank=True,
    )

    # ==========================================================
    # OPTIONAL DETAILS
    # ==========================================================

    details = models.JSONField(
        default=dict,
        blank=True,
    )

    # ==========================================================
    # TIMESTAMP
    # ==========================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=[
                    "integration",
                    "created_at",
                ],
            ),
            models.Index(
                fields=[
                    "integration",
                    "resource_type",
                ],
            ),
            models.Index(
                fields=[
                    "integration",
                    "change_type",
                ],
            ),
        ]

    def __str__(self):
        return (
            f"{self.integration.provider} | "
            f"{self.resource_type} | "
            f"{self.resource_name or self.external_resource_id} | "
            f"{self.change_type}"
        )
    

import uuid
from django.db import models
from django.utils import timezone


class QuickBooksOAuthState(models.Model):
    """
    Temporary OAuth state used while connecting
    a ZepEx company to QuickBooks.

    Prevents OAuth CSRF attacks and identifies
    which ZepEx company started the connection.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    company = models.ForeignKey(
        "tenants.Company",
        on_delete=models.CASCADE,
        related_name="quickbooks_oauth_states",
    )

    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="quickbooks_oauth_states",
    )

    state = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
    )

    is_used = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def __str__(self):
        return (
            f"{self.company.name} - "
            f"{self.user.email}"
        )


class QuickBooksCategoryMapping(models.Model):
    """
    Maps a ZepEx expense category to a QuickBooks
    accounting account for a specific company.

    Example:

        hotel -> Travel
        food -> Meals and Entertainment
        fuel -> Automobile Expense
    """

    integration = models.ForeignKey(
        CompanyIntegration,
        on_delete=models.CASCADE,
        related_name="quickbooks_category_mappings",
    )

    zepex_category = models.CharField(
        max_length=50,
    )

    quickbooks_account_id = models.CharField(
        max_length=100,
    )

    quickbooks_account_name = models.CharField(
        max_length=255,
    )

    quickbooks_account_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    quickbooks_account_sub_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "integration",
                    "zepex_category",
                ],
                name=(
                    "unique_quickbooks_category_mapping"
                ),
            ),
        ]

        ordering = [
            "zepex_category",
        ]

    def __str__(self):
        return (
            f"{self.integration.company.name} | "
            f"{self.zepex_category} -> "
            f"{self.quickbooks_account_name}"
        )

class QuickBooksExportRecord(models.Model):
    """
    Tracks a ZepEx expense report exported to QuickBooks.

    Prevents duplicate QuickBooks transactions and stores
    QuickBooks transaction and reconciliation information.
    """

    # ==========================================================
    # EXPORT STATUS
    # ==========================================================

    STATUS_PENDING = "PENDING"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = (
        (
            STATUS_PENDING,
            "Pending",
        ),
        (
            STATUS_PROCESSING,
            "Processing",
        ),
        (
            STATUS_SUCCESS,
            "Success",
        ),
        (
            STATUS_FAILED,
            "Failed",
        ),
    )

    # ==========================================================
    # RECONCILIATION STATUS
    # ==========================================================

    RECONCILIATION_NOT_CHECKED = "NOT_CHECKED"
    RECONCILIATION_VERIFIED = "VERIFIED"
    RECONCILIATION_MISMATCH = "MISMATCH"
    RECONCILIATION_MISSING = "MISSING"
    RECONCILIATION_ERROR = "ERROR"

    RECONCILIATION_CHOICES = (
        (
            RECONCILIATION_NOT_CHECKED,
            "Not Checked",
        ),
        (
            RECONCILIATION_VERIFIED,
            "Verified",
        ),
        (
            RECONCILIATION_MISMATCH,
            "Mismatch",
        ),
        (
            RECONCILIATION_MISSING,
            "Missing",
        ),
        (
            RECONCILIATION_ERROR,
            "Error",
        ),
    )

    # ==========================================================
    # INTEGRATION
    # ==========================================================

    integration = models.ForeignKey(
        CompanyIntegration,
        on_delete=models.CASCADE,
        related_name="quickbooks_exports",
    )

    # ==========================================================
    # EXPENSE REPORT
    # ==========================================================

    report = models.ForeignKey(
        "expenses.ExpenseReport",
        on_delete=models.PROTECT,
        related_name="quickbooks_exports",
    )

    # ==========================================================
    # QUICKBOOKS TRANSACTION
    # ==========================================================

    quickbooks_transaction_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    # ==========================================================
    # EXTERNAL REFERENCE
    # ==========================================================

    external_reference = models.CharField(
        max_length=100,
        unique=True,
    )

    # ==========================================================
    # EXPORT STATUS
    # ==========================================================

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    # ==========================================================
    # EXPORTED AMOUNT
    # ==========================================================

    exported_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # ==========================================================
    # EXPORT ERROR
    # ==========================================================

    error_message = models.TextField(
        null=True,
        blank=True,
    )

    # ==========================================================
    # QUICKBOOKS EXPORT RESPONSE
    # ==========================================================

    response_data = models.JSONField(
        default=dict,
        blank=True,
    )

    # ==========================================================
    # RECONCILIATION
    # ==========================================================

    reconciliation_status = models.CharField(
        max_length=20,
        choices=RECONCILIATION_CHOICES,
        default=RECONCILIATION_NOT_CHECKED,
    )

    reconciled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    reconciliation_error = models.TextField(
        null=True,
        blank=True,
    )

    reconciliation_data = models.JSONField(
        default=dict,
        blank=True,
    )

    # ==========================================================
    # TIMESTAMPS
    # ==========================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    exported_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # ==========================================================
    # META
    # ==========================================================

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "integration",
                    "report",
                ],
                name=(
                    "unique_quickbooks_report_export"
                ),
            ),
        ]

        ordering = [
            "-created_at",
        ]

    # ==========================================================
    # STRING REPRESENTATION
    # ==========================================================

    def __str__(self):
        return (
            f"{self.integration.company.name} | "
            f"{self.report_id} | "
            f"{self.status} | "
            f"{self.reconciliation_status}"
        )
