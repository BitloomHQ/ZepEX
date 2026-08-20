from django.db import migrations, models


def backfill_email_verified_via(apps, schema_editor):
    Request = apps.get_model("platform_management", "CompanyRegistrationRequest")
    Request.objects.filter(is_email_verified=True, email_verified_via="").update(
        email_verified_via="EMAIL"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("platform_management", "0005_companyregistrationrequest_reject_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyregistrationrequest",
            name="email_verified_via",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Not verified"),
                    ("EMAIL", "Verified through email"),
                    ("ADMIN", "Verified by admin"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.RunPython(backfill_email_verified_via, migrations.RunPython.noop),
    ]
