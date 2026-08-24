from django.db import migrations


OPTIONAL_COLUMNS = (
    ("quickbooks_payment_account_id", "varchar(100)"),
    ("quickbooks_payment_account_name", "varchar(255)"),
    ("quickbooks_payment_account_type", "varchar(100)"),
)


def add_missing_payment_account_columns(apps, schema_editor):
    table = "integrations_companyintegration"
    connection = schema_editor.connection
    try:
        with connection.cursor() as cursor:
            existing = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor,
                    table,
                )
            }
    except Exception:
        return

    for column, sql_type in OPTIONAL_COLUMNS:
        if column in existing:
            continue
        schema_editor.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {sql_type} NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0012_companyintegration_quickbooks_payment_account_id_and_more"),
    ]

    operations = [
        migrations.RunPython(
            add_missing_payment_account_columns,
            migrations.RunPython.noop,
        ),
    ]
