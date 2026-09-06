from django.urls import path

from .views import (
    # Common integrations
    integration_list,
    integration_provider_catalog,
    integration_activity,
    integration_dashboard_summary,

    # BambooHR
    bamboohr_callback,
    bamboohr_change_history,
    bamboohr_health,
    bamboohr_status,
    bamboohr_sync_history,
    bamboohr_webhook,
    connect_bamboohr,
    preview_bamboohr_employees,
    sync_bamboohr_all_view,
    sync_bamboohr_departments_view,
    sync_bamboohr_employees_view,
    sync_bamboohr_managers_view,

    # QuickBooks
    connect_quickbooks,
    delete_quickbooks_category_mapping,
    disconnect_quickbooks,
    export_report_quickbooks,
    quickbooks_accounts,
    quickbooks_callback,
    quickbooks_category_mappings,
    quickbooks_export_history,
    quickbooks_health,
    quickbooks_payment_accounts,
    quickbooks_report_export_status,
    quickbooks_settings,
    quickbooks_status,
    reconcile_quickbooks_report,
    retry_quickbooks_export,
    save_quickbooks_category_mapping,
    save_quickbooks_payment_account,
)

from .payroll_views import (
    bamboohr_payroll_add_report,
    bamboohr_payroll_batch_detail,
    bamboohr_payroll_batches,
    bamboohr_payroll_confirm,
    bamboohr_payroll_csv,
    bamboohr_payroll_eligible_reports,
    bamboohr_payroll_mark_ready,
    bamboohr_payroll_remove_report,
)


urlpatterns = [

    # ==========================================================
    # COMMON INTEGRATION APIs
    # ==========================================================

    path(
        "",
        integration_list,
        name="integration-list",
    ),

    path(
        "providers/",
        integration_provider_catalog,
        name="integration-provider-catalog",
    ),

    path(
        "activity/",
        integration_activity,
        name="integration-activity",
    ),

    path(
        "dashboard/",
        integration_dashboard_summary,
        name="integration-dashboard-summary",
    ),

    # ==========================================================
    # BAMBOOHR CONNECTION AND WEBHOOK
    # ==========================================================

    path(
        "bamboohr/connect/",
        connect_bamboohr,
        name="connect-bamboohr",
    ),

    path(
        "bamboohr/callback/",
        bamboohr_callback,
        name="bamboohr-callback",
    ),

    path(
        "bamboohr/webhook/<int:integration_id>/",
        bamboohr_webhook,
        name="bamboohr-webhook",
    ),

    # ==========================================================
    # BAMBOOHR SYNC
    # ==========================================================

    path(
        "bamboohr/sync/departments/",
        sync_bamboohr_departments_view,
        name="sync-bamboohr-departments",
    ),

    path(
        "bamboohr/sync/employees/",
        sync_bamboohr_employees_view,
        name="sync-bamboohr-employees",
    ),

    path(
        "bamboohr/sync/managers/",
        sync_bamboohr_managers_view,
        name="sync-bamboohr-managers",
    ),

    path(
        "bamboohr/sync/all/",
        sync_bamboohr_all_view,
        name="sync-bamboohr-all",
    ),

    # ==========================================================
    # BAMBOOHR STATUS, HISTORY, AND HEALTH
    # ==========================================================

    path(
        "bamboohr/employees/preview/",
        preview_bamboohr_employees,
        name="preview-bamboohr-employees",
    ),

    path(
        "bamboohr/status/",
        bamboohr_status,
        name="bamboohr-status",
    ),

    path(
        "bamboohr/sync-history/",
        bamboohr_sync_history,
        name="bamboohr-sync-history",
    ),

    path(
        "bamboohr/changes/",
        bamboohr_change_history,
        name="bamboohr-change-history",
    ),

    path(
        "bamboohr/health/",
        bamboohr_health,
        name="bamboohr-health",
    ),

    # ==========================================================
    # BAMBOOHR PAYROLL REIMBURSEMENT BATCHES
    # ==========================================================

    path(
        "bamboohr/payroll/eligible-reports/",
        bamboohr_payroll_eligible_reports,
        name="bamboohr-payroll-eligible-reports",
    ),

    path(
        "bamboohr/payroll/batches/",
        bamboohr_payroll_batches,
        name="bamboohr-payroll-batches",
    ),

    path(
        "bamboohr/payroll/batches/<uuid:batch_id>/",
        bamboohr_payroll_batch_detail,
        name="bamboohr-payroll-batch-detail",
    ),

    path(
        "bamboohr/payroll/batches/<uuid:batch_id>/reports/",
        bamboohr_payroll_add_report,
        name="bamboohr-payroll-add-report",
    ),

    path(
        "bamboohr/payroll/batches/<uuid:batch_id>/reports/<uuid:report_id>/",
        bamboohr_payroll_remove_report,
        name="bamboohr-payroll-remove-report",
    ),

    path(
        "bamboohr/payroll/batches/<uuid:batch_id>/ready/",
        bamboohr_payroll_mark_ready,
        name="bamboohr-payroll-mark-ready",
    ),

    path(
        "bamboohr/payroll/batches/<uuid:batch_id>/csv/",
        bamboohr_payroll_csv,
        name="bamboohr-payroll-csv",
    ),

    path(
        "bamboohr/payroll/batches/<uuid:batch_id>/confirm/",
        bamboohr_payroll_confirm,
        name="bamboohr-payroll-confirm",
    ),

    # ==========================================================
    # QUICKBOOKS CONNECTION
    # ==========================================================

    path(
        "quickbooks/connect/",
        connect_quickbooks,
        name="connect-quickbooks",
    ),

    path(
        "quickbooks/callback/",
        quickbooks_callback,
        name="quickbooks-callback",
    ),

    path(
        "quickbooks/status/",
        quickbooks_status,
        name="quickbooks-status",
    ),

    path(
        "quickbooks/health/",
        quickbooks_health,
        name="quickbooks-health",
    ),

    path(
        "quickbooks/disconnect/",
        disconnect_quickbooks,
        name="disconnect-quickbooks",
    ),

    # ==========================================================
    # QUICKBOOKS ACCOUNTS AND SETTINGS
    # ==========================================================

    path(
        "quickbooks/accounts/",
        quickbooks_accounts,
        name="quickbooks-accounts",
    ),

    path(
        "quickbooks/payment-accounts/",
        quickbooks_payment_accounts,
        name="quickbooks-payment-accounts",
    ),

    path(
        "quickbooks/payment-account/",
        save_quickbooks_payment_account,
        name="save-quickbooks-payment-account",
    ),

    path(
        "quickbooks/settings/",
        quickbooks_settings,
        name="quickbooks-settings",
    ),

    # ==========================================================
    # QUICKBOOKS CATEGORY MAPPINGS
    # ==========================================================

    path(
        "quickbooks/category-mappings/",
        quickbooks_category_mappings,
        name="quickbooks-category-mappings",
    ),

    path(
        "quickbooks/category-mappings/save/",
        save_quickbooks_category_mapping,
        name="save-quickbooks-category-mapping",
    ),

    path(
        "quickbooks/category-mappings/<int:mapping_id>/",
        delete_quickbooks_category_mapping,
        name="delete-quickbooks-category-mapping",
    ),

    # ==========================================================
    # QUICKBOOKS EXPORTS AND RECONCILIATION
    # ==========================================================

    path(
        "quickbooks/export-report/<uuid:report_id>/",
        export_report_quickbooks,
        name="quickbooks-export-report",
    ),

    path(
        "quickbooks/export-report/<uuid:report_id>/retry/",
        retry_quickbooks_export,
        name="retry-quickbooks-export",
    ),

    path(
        "quickbooks/export-status/<uuid:report_id>/",
        quickbooks_report_export_status,
        name="quickbooks-report-export-status",
    ),

    path(
        "quickbooks/export-history/",
        quickbooks_export_history,
        name="quickbooks-export-history",
    ),

    path(
        "quickbooks/reconcile/<uuid:report_id>/",
        reconcile_quickbooks_report,
        name="quickbooks-reconcile-report",
    ),
]
