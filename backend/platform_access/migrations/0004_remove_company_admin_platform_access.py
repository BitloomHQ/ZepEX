from django.db import migrations


def remove_company_admin_platform_access(apps, schema_editor):
    PlatformAdmin = apps.get_model("platform_access", "PlatformAdmin")
    PlatformAdmin.objects.filter(user__role="COMPANY_ADMIN").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("platform_access", "0003_platformadmin_nullable_company"),
        ("tenants", "0038_userprofile_platform_admin_nullable_company"),
    ]

    operations = [
        migrations.RunPython(
            remove_company_admin_platform_access,
            migrations.RunPython.noop,
        ),
    ]
