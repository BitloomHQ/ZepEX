from functools import lru_cache

from django.db.utils import OperationalError, ProgrammingError

from .models import CompanyIntegration

OPTIONAL_COMPANY_INTEGRATION_COLUMNS = (
    "last_synced_at",
    "last_sync_status",
    "last_sync_error",
    "quickbooks_payment_account_id",
    "quickbooks_payment_account_name",
    "quickbooks_payment_account_type",
)


@lru_cache(maxsize=1)
def missing_company_integration_columns():
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(
                cursor,
                CompanyIntegration._meta.db_table,
            )
    except (ProgrammingError, OperationalError):
        return OPTIONAL_COMPANY_INTEGRATION_COLUMNS

    existing = {column.name for column in description}
    return tuple(
        name
        for name in OPTIONAL_COMPANY_INTEGRATION_COLUMNS
        if name not in existing
    )


def defer_missing_integration_fields(queryset):
    missing = missing_company_integration_columns()
    if not missing:
        return queryset
    return queryset.defer(*missing)


def list_company_integrations(company, **filters):
    """Fetch integrations without crashing if tables/columns are missing."""
    if not company:
        return []
    try:
        queryset = defer_missing_integration_fields(
            CompanyIntegration.objects.filter(company=company, **filters)
        )
        return list(queryset)
    except (ProgrammingError, OperationalError):
        return []


def get_company_integration(company, **filters):
    integrations = list_company_integrations(company, **filters)
    return integrations[0] if integrations else None


def integration_has_credentials(integration):
    if not integration:
        return False
    try:
        credential = integration.credential
    except Exception:
        return False
    return bool(credential and credential.encrypted_config)
