from django.db import models

# Create your models here.
import uuid

from django.db import models
from django.utils import timezone

from tenants.models import Company


class Integration(models.Model):

    # --------------------------------------------------
    # Categories
    # --------------------------------------------------

    CATEGORY_HRMS = "HRMS"
    CATEGORY_PAYROLL = "PAYROLL"
    CATEGORY_ACCOUNTING = "ACCOUNTING"
    CATEGORY_IT = "IT"
    CATEGORY_ERP = "ERP"

    CATEGORY_CHOICES = (
        (CATEGORY_HRMS, "HR & Employee"),
        (CATEGORY_PAYROLL, "Payroll"),
        (CATEGORY_ACCOUNTING, "Accounting"),
        (CATEGORY_IT, "IT & Identity"),
        (CATEGORY_ERP, "ERP"),
    )

    # --------------------------------------------------
    # Providers
    # --------------------------------------------------

    # HRMS
    PROVIDER_BAMBOOHR = "BAMBOOHR"
    PROVIDER_RIPPLING = "RIPPLING"
    PROVIDER_WORKDAY = "WORKDAY"
    PROVIDER_HIBOB = "HIBOB"
    PROVIDER_DEEL = "DEEL"
    PROVIDER_ZOHO_PEOPLE = "ZOHO_PEOPLE"

    # Payroll
    PROVIDER_ADP = "ADP"
    PROVIDER_GUSTO = "GUSTO"
    PROVIDER_PAYCHEX = "PAYCHEX"
    PROVIDER_UKG = "UKG"
    PROVIDER_PAYLOCITY = "PAYLOCITY"

    # Accounting
    PROVIDER_QUICKBOOKS = "QUICKBOOKS"
    PROVIDER_XERO = "XERO"
    PROVIDER_SAGE = "SAGE"
    PROVIDER_ZOHO_BOOKS = "ZOHO_BOOKS"
    PROVIDER_FRESHBOOKS = "FRESHBOOKS"
    PROVIDER_NETSUITE = "NETSUITE"

    # IT / Identity
    PROVIDER_MICROSOFT_ENTRA = "MICROSOFT_ENTRA"
    PROVIDER_OKTA = "OKTA"
    PROVIDER_GOOGLE_WORKSPACE = "GOOGLE_WORKSPACE"
    PROVIDER_ONELOGIN = "ONELOGIN"
    PROVIDER_JUMPCLOUD = "JUMPCLOUD"
    PROVIDER_PING_IDENTITY = "PING_IDENTITY"

    # ERP
    PROVIDER_SAP = "SAP"
    PROVIDER_ORACLE = "ORACLE"
    PROVIDER_MICROSOFT_DYNAMICS = "MICROSOFT_DYNAMICS"
    PROVIDER_ODOO = "ODOO"
    PROVIDER_ACUMATICA = "ACUMATICA"

    # Development
    PROVIDER_MOCK = "MOCK"

    PROVIDER_CHOICES = (
        # HRMS
        (PROVIDER_BAMBOOHR, "BambooHR"),
        (PROVIDER_RIPPLING, "Rippling"),
        (PROVIDER_WORKDAY, "Workday"),
        (PROVIDER_HIBOB, "HiBob"),
        (PROVIDER_DEEL, "Deel"),
        (PROVIDER_ZOHO_PEOPLE, "Zoho People"),

        # Payroll
        (PROVIDER_ADP, "ADP"),
        (PROVIDER_GUSTO, "Gusto"),
        (PROVIDER_PAYCHEX, "Paychex"),
        (PROVIDER_UKG, "UKG"),
        (PROVIDER_PAYLOCITY, "Paylocity"),

        # Accounting
        (PROVIDER_QUICKBOOKS, "QuickBooks"),
        (PROVIDER_XERO, "Xero"),
        (PROVIDER_SAGE, "Sage"),
        (PROVIDER_ZOHO_BOOKS, "Zoho Books"),
        (PROVIDER_FRESHBOOKS, "FreshBooks"),
        (PROVIDER_NETSUITE, "NetSuite"),

        # IT
        (PROVIDER_MICROSOFT_ENTRA, "Microsoft Entra ID"),
        (PROVIDER_OKTA, "Okta"),
        (PROVIDER_GOOGLE_WORKSPACE, "Google Workspace"),
        (PROVIDER_ONELOGIN, "OneLogin"),
        (PROVIDER_JUMPCLOUD, "JumpCloud"),
        (PROVIDER_PING_IDENTITY, "Ping Identity"),

        # ERP
        (PROVIDER_SAP, "SAP"),
        (PROVIDER_ORACLE, "Oracle"),
        (PROVIDER_MICROSOFT_DYNAMICS, "Microsoft Dynamics 365"),
        (PROVIDER_ODOO, "Odoo"),
        (PROVIDER_ACUMATICA, "Acumatica"),

        # Development
        (PROVIDER_MOCK, "Mock Provider"),
    )

    # --------------------------------------------------
    # Connection Status
    # --------------------------------------------------

    STATUS_DISCONNECTED = "DISCONNECTED"
    STATUS_CONNECTED = "CONNECTED"
    STATUS_ERROR = "ERROR"
    STATUS_EXPIRED = "EXPIRED"

    STATUS_CHOICES = (
        (STATUS_DISCONNECTED, "Disconnected"),
        (STATUS_CONNECTED, "Connected"),
        (STATUS_ERROR, "Error"),
        (STATUS_EXPIRED, "Expired"),
    )

    # --------------------------------------------------
    # Model fields
    # --------------------------------------------------

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="integrations",
    )

    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
    )

    provider = models.CharField(
        max_length=50,
        choices=PROVIDER_CHOICES,
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_DISCONNECTED,
    )

    # --------------------------------------------------
    # OAuth / API credentials
    # --------------------------------------------------

    access_token = models.TextField(
        blank=True,
        null=True,
    )

    refresh_token = models.TextField(
        blank=True,
        null=True,
    )

    token_expires_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    scope = models.TextField(
        blank=True,
        default="",
    )

    # Provider-specific identifier
    external_account_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    bamboohr_domain = models.CharField(
    max_length=255,
    blank=True,
    default="",
)
    # --------------------------------------------------
    # Connection information
    # --------------------------------------------------

    connected_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    last_synced_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    last_error = models.TextField(
        blank=True,
        null=True,
    )

    # --------------------------------------------------
    # Timestamps
    # --------------------------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["category", "provider"]

        constraints = [
            models.UniqueConstraint(
                fields=["company", "provider"],
                name="unique_company_provider_integration",
            )
        ]

    def __str__(self):
        return (
            f"{self.company.name} - "
            f"{self.get_provider_display()}"
        )

    @property
    def is_token_expired(self):
        if not self.token_expires_at:
            return False

        return timezone.now() >= self.token_expires_at


class ExternalEmployee(models.Model):

    integration = models.ForeignKey(
        Integration,
        on_delete=models.CASCADE,
        related_name="employees",
    )

    external_id = models.CharField(
        max_length=255,
    )

    first_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
    )

    last_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
    )

    email = models.EmailField(
        blank=True,
        default="",
    )

    job_title = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    department = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    status = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    raw_data = models.JSONField(
        default=dict,
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
                    "external_id",
                ],
                name="unique_integration_external_employee",
            )
        ]

    def __str__(self):
        return (
            f"{self.first_name} "
            f"{self.last_name} "
            f"({self.email})"
        )