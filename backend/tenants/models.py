import uuid

from django.db import models
from django.contrib.auth.models import User


from platform_management.models import PlatformOwner
from django.db import models
from django.db.models import Q

class Company(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    owner = models.ForeignKey(
        PlatformOwner,
        on_delete=models.PROTECT,
        related_name="companies"
    )

    name = models.CharField(
        max_length=255
    )

    domain = models.CharField(
        max_length=255,
        unique=True
    )

    # --------------------------------------------------
    # Reimbursement Email
    # --------------------------------------------------

    reimbursement_email_prefix = models.SlugField(
        max_length=100,
        unique=True,
        null=True,
        blank=True
    )

    reimbursement_email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        default=None,
    )

    # --------------------------------------------------
    # COMPANY-SPECIFIC IMAP CONFIGURATION
    # --------------------------------------------------

    imap_host = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    imap_port = models.PositiveIntegerField(
        default=993,
    )

    imap_username = models.EmailField(
        blank=True,
        null=True,
    )

    imap_password = models.CharField(
        max_length=500,
        blank=True,
        null=True,
    )

    # --------------------------------------------------
    # Company Status
    # --------------------------------------------------

    is_verified = models.BooleanField(
        default=False
    )

    is_active = models.BooleanField(
        default=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def save(self, *args, **kwargs):

        # Normalize company domain
        if self.domain:
            self.domain = (
                self.domain
                .strip()
                .lower()
            )

        # Normalize reimbursement email
        if self.reimbursement_email:
            self.reimbursement_email = (
                self.reimbursement_email
                .strip()
                .lower()
            )
        else:
            self.reimbursement_email = None

        # Normalize IMAP host
        if self.imap_host:
            self.imap_host = (
                self.imap_host
                .strip()
                .lower()
            )
        else:
            self.imap_host = None

        # Normalize IMAP username
        if self.imap_username:
            self.imap_username = (
                self.imap_username
                .strip()
                .lower()
            )
        else:
            self.imap_username = None

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Department(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="departments"
    )

    name = models.CharField(max_length=100)

    manager = models.ForeignKey(
        'UserProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_departments'
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    is_active = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.company.name} - {self.name}"

class CompanyRole(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="roles"
    )

    name = models.CharField(max_length=100)

    can_upload_receipt = models.BooleanField(default=False)
    can_submit_expense = models.BooleanField(default=False)
    can_approve_expense = models.BooleanField(default=False)
    can_mark_paid = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    can_manage_company = models.BooleanField(
    default=False
)

    can_manage_roles = models.BooleanField(
    default=False
)

    can_manage_employees = models.BooleanField(
    default=False
)

    can_manage_departments = models.BooleanField(
    default=False
)

    can_manage_policy = models.BooleanField(
    default=False
)

    can_manage_workflow = models.BooleanField(
    default=False
)

    can_view_company_reports = models.BooleanField(
    default=False
)
    can_manage_integrations = models.BooleanField(
    default=False
)

    can_view_integrations = models.BooleanField(
    default=False
)

    class Meta:
        unique_together = ("company", "name")

    def __str__(self):
        return f"{self.company.name} - {self.name}"
    
class UserProfile(models.Model):

    ROLE_CHOICES = (
        ("COMPANY_ADMIN", "Company Admin"),
        ("MANAGER", "Manager"),
        ("ACCOUNTS", "Accounts"),
        ("EMPLOYEE", "Employee"),
        ("PLATFORM_ADMIN", "Platform Admin"),
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees"
    )

    # Existing system role (keep it)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES
    )

    job_title = models.CharField(
    max_length=255,
    null=True,
    blank=True,
)

    # NEW dynamic company role
    company_role = models.ForeignKey(
        "CompanyRole",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )

    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True
    )

    profile_picture = models.ImageField(
        upload_to="profile_pictures/",
        blank=True,
        null=True
    )

    address = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    invite_email_sent = models.BooleanField(default=False)

    invite_email_sent_at = models.DateTimeField(
    null=True,
    blank=True
)
    temporary_password = models.CharField(
    max_length=255,
    blank=True,
    null=True
)

    force_password_change = models.BooleanField(
    default=True
)
    reporting_manager = models.ForeignKey(
    "self",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="team_members"
)

    def __str__(self):
        role_name = (
            self.company_role.name
            if self.company_role
            else self.role
        )

        return f"{self.user.email} - {role_name}"


class ExternalDatabaseConfig(models.Model):

    DB_ENGINE_CHOICES = (
    ("postgresql", "PostgreSQL"),
    ("mysql", "MySQL"),
    ("mssql", "Microsoft SQL Server"),
    ("oracle", "Oracle"),
)

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name='db_config'
    )

    db_engine = models.CharField(
        max_length=20,
        choices=DB_ENGINE_CHOICES
    )

    db_host = models.CharField(max_length=255)
    db_port = models.IntegerField()

    db_name = models.CharField(max_length=255)

    db_user = models.CharField(max_length=255)

    db_password = models.CharField(
        max_length=255
    )

    last_synced_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Database Config - {self.company.name}"


class CompanyPolicy(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="policy"
    )

    old_bill_limit_days = models.PositiveIntegerField(
    default=90,
    help_text="Maximum number of days old a receipt can be for reimbursement."
)

    updated_at = models.DateTimeField(
        auto_now=True
    )

    auto_approve_if_no_violation = models.BooleanField(
        default=True
    )

    def __str__(self):
        return f"Policy - {self.company.name}"


    

class PolicyCategoryRule(models.Model):

    SCOPE_ALL = "ALL"
    SCOPE_ROLE = "ROLE"

    SCOPE_CHOICES = [
        (SCOPE_ALL, "All Employees"),
        (SCOPE_ROLE, "Specific Role"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    policy = models.ForeignKey(
        CompanyPolicy,
        on_delete=models.CASCADE,
        related_name="category_rules",
    )

    policy_version = models.ForeignKey(
        "PolicyVersion",
        on_delete=models.CASCADE,
        related_name="rules",
        null=True,
        blank=True,
    )

    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default=SCOPE_ROLE,
    )

    company_role = models.ForeignKey(
        CompanyRole,
        on_delete=models.CASCADE,
        related_name="policy_category_rules",
        null=True,
        blank=True,
    )

    category_name = models.CharField(
        max_length=100,
    )

    max_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    currency = models.CharField(
        max_length=3,
        default="INR",
    )

    is_unlimited = models.BooleanField(
        default=False,
    )

    category_description = models.TextField(
        null=True,
        blank=True,
    )

    policy_reason = models.TextField(
        null=True,
        blank=True,
    )

    source_text = models.TextField(
        null=True,
        blank=True,
    )

    ai_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
    )

    is_ai_generated = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "scope",
            "company_role__name",
            "category_name",
        ]

        constraints = [
            # --------------------------------------------------
            # Versioned role-specific rules
            # --------------------------------------------------
            models.UniqueConstraint(
                fields=[
                    "policy_version",
                    "company_role",
                    "category_name",
                ],
                condition=(
                    Q(
                        policy_version__isnull=False,
                        scope="ROLE",
                    )
                ),
                name=(
                    "unique_role_rule_per_policy_version"
                ),
            ),

            # --------------------------------------------------
            # Versioned rules applying to all employees
            # --------------------------------------------------
            models.UniqueConstraint(
                fields=[
                    "policy_version",
                    "category_name",
                ],
                condition=(
                    Q(
                        policy_version__isnull=False,
                        scope="ALL",
                    )
                ),
                name=(
                    "unique_all_rule_per_policy_version"
                ),
            ),

            # --------------------------------------------------
            # Legacy role-specific rules
            # --------------------------------------------------
            models.UniqueConstraint(
                fields=[
                    "policy",
                    "company_role",
                    "category_name",
                ],
                condition=(
                    Q(
                        policy_version__isnull=True,
                        scope="ROLE",
                    )
                ),
                name=(
                    "unique_legacy_role_policy_rule"
                ),
            ),

            # --------------------------------------------------
            # Legacy rules applying to all employees
            # --------------------------------------------------
            models.UniqueConstraint(
                fields=[
                    "policy",
                    "category_name",
                ],
                condition=(
                    Q(
                        policy_version__isnull=True,
                        scope="ALL",
                    )
                ),
                name=(
                    "unique_legacy_all_policy_rule"
                ),
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}

        # --------------------------------------------------
        # Normalize values
        # --------------------------------------------------

        self.category_name = (
            self.category_name.strip().lower()
            if self.category_name
            else self.category_name
        )

        self.currency = (
            self.currency.strip().upper()
            if self.currency
            else self.currency
        )

        self.scope = (
            self.scope.strip().upper()
            if self.scope
            else self.scope
        )

        # --------------------------------------------------
        # Category validation
        # --------------------------------------------------

        if not self.category_name:
            errors["category_name"] = (
                "Category name is required."
            )

        # --------------------------------------------------
        # Scope validation
        # --------------------------------------------------

        if self.scope not in {
            self.SCOPE_ALL,
            self.SCOPE_ROLE,
        }:
            errors["scope"] = (
                "Scope must be ALL or ROLE."
            )

        elif self.scope == self.SCOPE_ALL:
            # Global policy rule must not belong to one role.
            self.company_role = None

        elif (
            self.scope == self.SCOPE_ROLE
            and not self.company_role_id
        ):
            errors["company_role"] = (
                "company_role is required when scope is ROLE."
            )

        # --------------------------------------------------
        # Company-role validation
        # --------------------------------------------------

        if (
            self.scope == self.SCOPE_ROLE
            and self.company_role_id
            and self.policy_id
        ):
            if (
                self.company_role.company_id
                != self.policy.company_id
            ):
                errors["company_role"] = (
                    "Company role belongs to another company."
                )

        # --------------------------------------------------
        # Policy-version validation
        # --------------------------------------------------

        if self.policy_version_id and self.policy_id:
            if (
                self.policy_version.policy_id
                != self.policy_id
            ):
                errors["policy_version"] = (
                    "Policy version does not belong to this policy."
                )

        # --------------------------------------------------
        # Amount validation
        # --------------------------------------------------

        if self.is_unlimited:
            self.max_amount = None

        if (
            not self.is_unlimited
            and self.max_amount is None
        ):
            errors["max_amount"] = (
                "max_amount is required when the policy "
                "is not unlimited."
            )

        if (
            self.max_amount is not None
            and self.max_amount < 0
        ):
            errors["max_amount"] = (
                "max_amount cannot be negative."
            )

        # --------------------------------------------------
        # Currency validation
        # --------------------------------------------------

        if not self.currency:
            errors["currency"] = (
                "Currency is required."
            )

        elif len(self.currency) != 3:
            errors["currency"] = (
                "Use a three-letter currency code "
                "such as INR or USD."
            )

        # --------------------------------------------------
        # AI confidence validation
        # --------------------------------------------------

        if self.ai_confidence is not None:
            if (
                self.ai_confidence < 0
                or self.ai_confidence > 1
            ):
                errors["ai_confidence"] = (
                    "AI confidence must be between 0 and 1."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        limit = (
            "Unlimited"
            if self.is_unlimited
            else f"{self.max_amount} {self.currency}"
        )

        version = (
            f"v{self.policy_version.version_number}"
            if self.policy_version_id
            else "Legacy"
        )

        scope_display = (
            "All Employees"
            if self.scope == self.SCOPE_ALL
            else (
                self.company_role.name
                if self.company_role_id
                else "Role Not Assigned"
            )
        )

        return (
            f"{self.policy.company.name} - "
            f"{version} - "
            f"{scope_display} - "
            f"{self.category_name} - "
            f"{limit}"
        )
class ReimbursementEmailConfig(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="email_config"
    )

    email_address = models.EmailField(
        help_text="Company reimbursement email, e.g. expenses@bitloom.com"
    )

    imap_host = models.CharField(
        max_length=255,
        help_text="Example: imap.gmail.com"
    )

    imap_port = models.IntegerField(
        default=993
    )

    imap_username = models.CharField(
        max_length=255
    )

    imap_password = models.CharField(
        max_length=255,
        help_text="Use app password, not normal email password"
    )

    is_active = models.BooleanField(
        default=True
    )

    last_checked_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.company.name} - {self.email_address}"       



class CompanySMTPConfig(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="smtp_config"
    )

    smtp_host = models.CharField(max_length=255)

    smtp_port = models.IntegerField(default=587)

    smtp_email = models.EmailField()

    smtp_password = models.CharField(max_length=255)

    use_tls = models.BooleanField(default=True)

    from_email_name = models.CharField(
        max_length=100,
        default="Zepex"
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.company.name} SMTP"     
    


class DatabaseSyncLog(models.Model):
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="database_sync_logs"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES
    )

    records_created = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)

    error_message = models.TextField(
        blank=True,
        null=True
    )

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.company.name} - {self.status}"    
    

class Currency(models.Model):
    code = models.CharField(
        max_length=3,
        unique=True
    )

    name = models.CharField(
        max_length=100
    )

    symbol = models.CharField(
        max_length=10
    )

    country = models.CharField(
        max_length=100
    )

    flag = models.CharField(
        max_length=10,
        blank=True,
        null=True
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"   


class CompanyFinanceSettings(models.Model):

    EXCHANGE_RATE_PROVIDER_CHOICES = [
        ("ExchangeRate API", "ExchangeRate API"),
        ("Open Exchange Rates", "Open Exchange Rates"),
        ("Fixer", "Fixer"),
    ]

    DATE_FORMAT_CHOICES = [
        ("DD/MM/YYYY", "DD/MM/YYYY"),
        ("MM/DD/YYYY", "MM/DD/YYYY"),
        ("YYYY-MM-DD", "YYYY-MM-DD"),
    ]

    EXCHANGE_RATE_SOURCE = [
        ("GLOBAL", "Global Exchange Rate"),
        ("CUSTOM", "Company Custom Rate"),
    ]

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="finance_settings"
    )

    base_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="company_finance_settings"
    )

    auto_currency_conversion = models.BooleanField(
        default=True
    )

    exchange_rate_source = models.CharField(
        max_length=20,
        choices=EXCHANGE_RATE_SOURCE,
        default="GLOBAL"
    )

    exchange_rate_provider = models.CharField(
        max_length=100,
        choices=EXCHANGE_RATE_PROVIDER_CHOICES,
        default="ExchangeRate API"
    )

    allow_manual_exchange_rate = models.BooleanField(
        default=False
    )

    decimal_places = models.PositiveSmallIntegerField(
        default=2
    )

    rounding_enabled = models.BooleanField(
        default=True
    )

    timezone = models.CharField(
        max_length=100,
        default="UTC"
    )

    date_format = models.CharField(
        max_length=20,
        choices=DATE_FORMAT_CHOICES,
        default="DD/MM/YYYY"
    )

    last_exchange_sync = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.company.name} Finance Settings"


class CompanyExchangeRate(models.Model):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="custom_exchange_rates",
    )

    from_currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name="company_from_rates",
    )

    to_currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name="company_to_rates",
    )

    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=8,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        unique_together = (
            "company",
            "from_currency",
            "to_currency",
        )

    def __str__(self):
        return (
            f"{self.company.name}: "
            f"1 {self.from_currency.code} = "
            f"{self.exchange_rate} {self.to_currency.code}"
        )
    

class PolicyDocumentImport(models.Model):
    STATUS_UPLOADED = "UPLOADED"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
    STATUS_IMPORTED = "IMPORTED"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = (
        (STATUS_UPLOADED, "Uploaded"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_REVIEW_REQUIRED, "Review Required"),
        (STATUS_IMPORTED, "Imported"),
        (STATUS_FAILED, "Failed"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="policy_document_imports"
    )

    uploaded_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="policy_document_imports"
    )

    document = models.FileField(
        upload_to="policy_documents/"
    )

    original_filename = models.CharField(
        max_length=255
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_UPLOADED
    )

    extracted_json = models.JSONField(
        default=dict,
        blank=True
    )

    warnings = models.JSONField(
        default=list,
        blank=True
    )

    conflicts = models.JSONField(
        default=list,
        blank=True
    )

    error_message = models.TextField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )
    ai_model = models.CharField(
    max_length=100,
    blank=True,
    null=True,
)

    prompt_version = models.CharField(
    max_length=50,
    default="v2.0",
)

    document_language = models.CharField(
    max_length=100,
    blank=True,
    null=True,
)

    document_language_code = models.CharField(
    max_length=20,
    blank=True,
    null=True,
)

    output_language = models.CharField(
    max_length=100,
    blank=True,
    null=True,
)

    output_language_code = models.CharField(
    max_length=20,
    blank=True,
    null=True,
)

    document_type = models.CharField(
    max_length=100,
    blank=True,
    null=True,
)

    document_quality = models.JSONField(
    default=dict,
    blank=True,
)

    ai_metadata = models.JSONField(
    default=dict,
    blank=True,
)

    def __str__(self):
        return (
            f"{self.company.name} - "
            f"{self.original_filename} - "
            f"{self.status}"
        )    


class PolicyVersion(models.Model):

    STATUS_DRAFT = "DRAFT"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_ARCHIVED = "ARCHIVED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    policy = models.ForeignKey(
        CompanyPolicy,
        on_delete=models.CASCADE,
        related_name="versions",
    )

    version_number = models.PositiveIntegerField()

    title = models.CharField(
        max_length=255,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    imported_from_document = models.ForeignKey(
        "PolicyDocumentImport",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="policy_versions",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )

    is_active = models.BooleanField(
        default=False,
    )

    created_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_policy_versions",
    )

    activated_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activated_policy_versions",
    )

    activated_at = models.DateTimeField(
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
        ordering = [
            "-version_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "policy",
                    "version_number",
                ],
                name="unique_policy_version_number",
            ),

            # Only one active version is allowed per company policy.
            models.UniqueConstraint(
                fields=["policy"],
                condition=Q(is_active=True),
                name="unique_active_version_per_policy",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}

        if self.version_number < 1:
            errors["version_number"] = (
                "Version number must be greater than zero."
            )

        if self.is_active and self.status != self.STATUS_ACTIVE:
            errors["status"] = (
                "An active policy version must have ACTIVE status."
            )

        if self.status == self.STATUS_ACTIVE and not self.is_active:
            errors["is_active"] = (
                "A policy version with ACTIVE status must be active."
            )

        if self.status == self.STATUS_ARCHIVED and self.is_active:
            errors["is_active"] = (
                "An archived policy version cannot remain active."
            )

        if (
            self.imported_from_document
            and self.imported_from_document.company_id
            != self.policy.company_id
        ):
            errors["imported_from_document"] = (
                "The imported document belongs to another company."
            )

        if (
            self.created_by
            and self.created_by.company_id
            != self.policy.company_id
        ):
            errors["created_by"] = (
                "The version creator belongs to another company."
            )

        if (
            self.activated_by
            and self.activated_by.company_id
            != self.policy.company_id
        ):
            errors["activated_by"] = (
                "The activating user belongs to another company."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.policy.company.name} - "
            f"{self.title} - "
            f"v{self.version_number}"
        )       
    
class CompanyPreferences(models.Model):
    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="preferences",
    )

    output_language_code = models.CharField(
        max_length=20,
        default="en",
    )

    output_language_name = models.CharField(
        max_length=100,
        default="English",
    )

    preserve_original_text = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return (
            f"{self.company.name} - "
            f"{self.output_language_name}"
        )


    
class PolicyVersionComparison(models.Model):

    GENERATED_BY_GEMINI = "GEMINI"
    GENERATED_BY_FALLBACK = "DETERMINISTIC_FALLBACK"

    GENERATED_BY_CHOICES = [
        (
            GENERATED_BY_GEMINI,
            "Gemini",
        ),
        (
            GENERATED_BY_FALLBACK,
            "Deterministic fallback",
        ),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    policy = models.ForeignKey(
        CompanyPolicy,
        on_delete=models.CASCADE,
        related_name="version_comparisons",
    )

    old_version = models.ForeignKey(
        PolicyVersion,
        on_delete=models.CASCADE,
        related_name="comparisons_as_old_version",
    )

    new_version = models.ForeignKey(
        PolicyVersion,
        on_delete=models.CASCADE,
        related_name="comparisons_as_new_version",
    )

    comparison_data = models.JSONField(
        default=dict,
        blank=True,
    )

    ai_summary = models.JSONField(
        default=dict,
        blank=True,
    )

    ai_summary_generated = models.BooleanField(
        default=False,
    )

    generated_by = models.CharField(
        max_length=40,
        choices=GENERATED_BY_CHOICES,
        null=True,
        blank=True,
    )

    ai_model = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    output_language = models.CharField(
        max_length=100,
        default="English",
    )

    output_language_code = models.CharField(
        max_length=20,
        default="en",
    )

    include_unchanged = models.BooleanField(
        default=False,
    )

    created_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_policy_comparisons",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-updated_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "old_version",
                    "new_version",
                    "include_unchanged",
                    "output_language_code",
                ],
                name=(
                    "unique_policy_version_comparison"
                ),
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}

        if self.old_version_id == self.new_version_id:
            errors["new_version"] = (
                "Old and new policy versions must be different."
            )

        if (
            self.old_version_id
            and self.old_version.policy_id
            != self.policy_id
        ):
            errors["old_version"] = (
                "Old version does not belong to this policy."
            )

        if (
            self.new_version_id
            and self.new_version.policy_id
            != self.policy_id
        ):
            errors["new_version"] = (
                "New version does not belong to this policy."
            )

        if (
            self.created_by_id
            and self.created_by.company_id
            != self.policy.company_id
        ):
            errors["created_by"] = (
                "Comparison creator belongs to another company."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.policy.company.name}: "
            f"v{self.old_version.version_number} → "
            f"v{self.new_version.version_number}"
        )

class CompanyEmailIntegration(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="email_integration",
    )

    reimbursement_email = models.EmailField()

    imap_host = models.CharField(
        max_length=255
    )

    imap_port = models.PositiveIntegerField(
        default=993
    )

    imap_username = models.EmailField()

    imap_password = models.CharField(
        max_length=500
    )

    use_ssl = models.BooleanField(
        default=True
    )

    is_active = models.BooleanField(
        default=True
    )

    last_sync_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"{self.company.name} - "
            f"{self.reimbursement_email}"
        )

