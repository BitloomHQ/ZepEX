from django.contrib import admin

# Register your models here.
from django.contrib import admin

from .models import (
    Company,
    Department,
    UserProfile,
    ExternalDatabaseConfig,
    CompanyPolicy,
    PolicyCategoryRule,
    CompanyFinanceSettings,
)

from .models import CompanyEmailIntegration
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "domain",
        "is_verified",
        "created_at"
    )

    search_fields = (
        "name",
        "domain"
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "company",
        "manager"
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "company",
        "department",
        "role"
    )

    list_filter = (
        "company",
        "role"
    )


@admin.register(ExternalDatabaseConfig)
class ExternalDatabaseConfigAdmin(admin.ModelAdmin):

    list_display = (
        "company",
        "db_engine",
        "db_host",
        "last_synced_at"
    )


class PolicyCategoryRuleInline(admin.TabularInline):
    model = PolicyCategoryRule
    extra = 1


@admin.register(CompanyPolicy)
class CompanyPolicyAdmin(admin.ModelAdmin):

    list_display = (
        "company",
        "updated_at"
    )

    inlines = [
        PolicyCategoryRuleInline
    ]

from .models import ReimbursementEmailConfig
@admin.register(ReimbursementEmailConfig)
class ReimbursementEmailConfigAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "email_address",
        "imap_host",
        "imap_port",
        "is_active",
        "last_checked_at",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("company__name", "email_address")    


from .models import Currency

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "country",
        "symbol",
        "is_active",
    )

    search_fields = (
        "code",
        "name",
        "country",
    )

    list_filter = (
        "is_active",
    )

    ordering = (
        "code",
    )

@admin.register(CompanyFinanceSettings)
class CompanyFinanceSettingsAdmin(admin.ModelAdmin):

    list_display = (
        "company",
        "base_currency",
        "exchange_rate_source",
        "exchange_rate_provider",
        "auto_currency_conversion",
        "allow_manual_exchange_rate",
    )

    list_filter = (
        "exchange_rate_source",
        "auto_currency_conversion",
        "allow_manual_exchange_rate",
    )

    search_fields = (
        "company__name",
    )

@admin.register(CompanyEmailIntegration)
class CompanyEmailIntegrationAdmin(admin.ModelAdmin):

    list_display = (
        "company",
        "reimbursement_email",
        "imap_host",
        "imap_port",
        "is_active",
        "last_sync_at",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "company__name",
        "reimbursement_email",
        "imap_username",
    )