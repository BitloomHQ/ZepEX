from django.db import migrations


def seed_platform_permissions(apps, schema_editor):
    PlatformPermission = apps.get_model(
        "platform_access",
        "PlatformPermission",
    )

    permissions = [
        # Dashboard
        ("View Dashboard", "view_dashboard", "Dashboard"),

        # Company
        ("View Companies", "view_companies", "Company"),
        ("Approve Company", "approve_company", "Company"),
        ("Reject Company", "reject_company", "Company"),
        ("Edit Company", "edit_company", "Company"),
        ("Delete Company", "delete_company", "Company"),

        # Platform Users
        ("View Platform Users", "view_platform_users", "Platform Users"),
        ("Create Platform User", "create_platform_user", "Platform Users"),
        ("Edit Platform User", "edit_platform_user", "Platform Users"),
        ("Delete Platform User", "delete_platform_user", "Platform Users"),

        # Company Users
        ("View Company Users", "view_company_users", "Company Users"),
        ("Create Company User", "create_company_user", "Company Users"),
        ("Edit Company User", "edit_company_user", "Company Users"),
        ("Delete Company User", "delete_company_user", "Company Users"),

        # Departments
        ("Manage Departments", "manage_departments", "Departments"),

        # Policies
        ("Manage Policies", "manage_policies", "Policies"),

        # Workflow
        ("Manage Workflow", "manage_workflow", "Workflow"),

        # Reports
        ("View Reports", "view_reports", "Reports"),
        ("Export Reports", "export_reports", "Reports"),

        # Audit
        ("View Audit Logs", "view_audit_logs", "Audit"),

        # Billing
        ("Manage Billing", "manage_billing", "Billing"),

        # Settings
        ("Manage Settings", "manage_settings", "Settings"),
    ]

    for name, code, module in permissions:
        PlatformPermission.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
            },
        )


def remove_platform_permissions(apps, schema_editor):
    PlatformPermission = apps.get_model(
        "platform_access",
        "PlatformPermission",
    )

    PlatformPermission.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("platform_access", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_platform_permissions,
            remove_platform_permissions,
        ),
    ]