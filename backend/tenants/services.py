# tenants/services.py

from rest_framework import status

from django.utils import timezone
from django.contrib.auth.models import User

from tenants.models import (
    ExternalDatabaseConfig,
    DatabaseSyncLog,
    Department,
    CompanyRole,
    UserProfile,
    CompanyPolicy,
    PolicyCategoryRule,
)

from audit_logs.utils import create_audit_log

from tenants.db_utils import get_external_db_connection


def sync_company_external_database(company, action_by=None):

    sync_log = DatabaseSyncLog.objects.create(
        company=company,
        status=DatabaseSyncLog.STATUS_FAILED
    )

    department_created_count = 0
    department_updated_count = 0

    role_created_count = 0
    role_updated_count = 0

    employees_created_count = 0
    employees_updated_count = 0

    policy_created_count = 0
    policy_updated_count = 0

    try:

        config = ExternalDatabaseConfig.objects.get(
            company=company
        )

        conn = get_external_db_connection(config)

        cursor = conn.cursor()

        # ==========================================
        # PASTE EVERYTHING FROM YOUR CURRENT
        # sync_external_database()
        #
        # START FROM:
        #
        # try:
        #     cursor.execute(...)
        #
        # END BEFORE:
        #
        # return Response(...)
        # ==========================================

        cursor.close()
        conn.close()

        config.last_synced_at = timezone.now()

        config.save(
            update_fields=["last_synced_at"]
        )

        sync_log.status = DatabaseSyncLog.STATUS_SUCCESS

        sync_log.records_created = (
            employees_created_count
        )

        sync_log.records_updated = (
            employees_updated_count
        )

        sync_log.completed_at = timezone.now()

        sync_log.save(
            update_fields=[
                "status",
                "records_created",
                "records_updated",
                "completed_at",
            ]
        )

        create_audit_log(
            company=company,
            action="SYNC_COMPLETED",
            action_by=action_by,
            message="External database sync completed.",
            metadata={
                "departments_created": department_created_count,
                "departments_updated": department_updated_count,
                "roles_created": role_created_count,
                "roles_updated": role_updated_count,
                "employees_created": employees_created_count,
                "employees_updated": employees_updated_count,
                "policy_rules_created": policy_created_count,
                "policy_rules_updated": policy_updated_count,
                "db_engine": config.db_engine,
            }
        )

        return {
            "success": True,
            "message": "Database sync completed successfully.",
            "departments_created": department_created_count,
            "departments_updated": department_updated_count,
            "roles_created": role_created_count,
            "roles_updated": role_updated_count,
            "employees_created": employees_created_count,
            "employees_updated": employees_updated_count,
            "policy_rules_created": policy_created_count,
            "policy_rules_updated": policy_updated_count,
        }

    except Exception as e:

        sync_log.status = DatabaseSyncLog.STATUS_FAILED

        sync_log.error_message = str(e)

        sync_log.completed_at = timezone.now()

        sync_log.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
            ]
        )

        create_audit_log(
            company=company,
            action="SYNC_FAILED",
            action_by=action_by,
            message="External database sync failed.",
            metadata={
                "error": str(e)
            }
        )

        return {
            "success": False,
            "error": str(e)
        }