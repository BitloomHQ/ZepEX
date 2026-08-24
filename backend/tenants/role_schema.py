from functools import lru_cache

from django.db.utils import OperationalError, ProgrammingError

from .models import CompanyRole

OPTIONAL_COMPANY_ROLE_COLUMNS = (
    "can_manage_company",
    "can_manage_roles",
    "can_manage_employees",
    "can_manage_departments",
    "can_manage_policy",
    "can_manage_workflow",
    "can_view_company_reports",
    "can_manage_integrations",
    "can_view_integrations",
)


@lru_cache(maxsize=1)
def missing_company_role_columns():
    """Return optional CompanyRole columns that are not in the live database.

    Production 500s happen when the app model/serializer includes flags
    from migrations 0042/0043 that were never applied on Render.
    """
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(
                cursor,
                CompanyRole._meta.db_table,
            )
    except (ProgrammingError, OperationalError):
        return ()

    existing = {column.name for column in description}
    return tuple(
        name
        for name in OPTIONAL_COMPANY_ROLE_COLUMNS
        if name not in existing
    )


def defer_missing_company_role_fields(queryset, prefix=""):
    missing = missing_company_role_columns()
    if not missing:
        return queryset
    return queryset.defer(
        *[f"{prefix}{name}" if prefix else name for name in missing]
    )


def company_role_flag(role, name, default=False):
    if not role or name in missing_company_role_columns():
        return default
    return bool(getattr(role, name, default))
