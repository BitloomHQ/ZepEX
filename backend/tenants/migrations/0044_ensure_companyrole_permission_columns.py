from django.db import migrations


OPTIONAL_ROLE_COLUMNS = (
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


def add_missing_company_role_columns(apps, schema_editor):
    table = "tenants_companyrole"
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        existing = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                table,
            )
        }

    for column in OPTIONAL_ROLE_COLUMNS:
        if column in existing:
            continue
        schema_editor.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} boolean DEFAULT false NOT NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0043_companyrole_can_manage_integrations_and_more"),
    ]

    operations = [
        migrations.RunPython(
            add_missing_company_role_columns,
            migrations.RunPython.noop,
        ),
    ]
