import json
from pathlib import Path

from django.db import migrations


def seed_currencies(apps, schema_editor):
    Currency = apps.get_model("tenants", "Currency")
    file_path = Path(__file__).resolve().parents[1] / "seed_data" / "currencies.json"

    if not file_path.exists():
        return

    with open(file_path, "r", encoding="utf-8") as file:
        currencies = json.load(file)

    rows = [
        {
            "code": currency["code"].upper(),
            "name": currency["name"],
            "symbol": currency.get("symbol", ""),
            "country": currency.get("country", ""),
            "flag": currency.get("flag", ""),
            "is_active": True,
        }
        for currency in currencies
    ]
    codes = [row["code"] for row in rows]
    existing_by_code = {
        obj.code: obj
        for obj in Currency.objects.filter(code__in=codes)
    }

    to_create = []
    to_update = []
    for row in rows:
        existing = existing_by_code.get(row["code"])
        if existing is None:
            to_create.append(Currency(**row))
            continue

        existing.name = row["name"]
        existing.symbol = row["symbol"]
        existing.country = row["country"]
        existing.flag = row["flag"]
        existing.is_active = True
        to_update.append(existing)

    if to_create:
        Currency.objects.bulk_create(to_create, batch_size=100)

    if to_update:
        Currency.objects.bulk_update(
            to_update,
            ["name", "symbol", "country", "flag", "is_active"],
            batch_size=100,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0033_alter_policycategoryrule_options_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_currencies, migrations.RunPython.noop),
    ]
