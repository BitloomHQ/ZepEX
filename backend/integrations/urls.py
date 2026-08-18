from django.urls import path

from .views import (
    integration_list,
    integration_provider_catalog,

    # BambooHR
    test_bamboohr_connection,
    connect_bamboohr,
    preview_bamboohr_employees,
    sync_bamboohr,
    bamboohr_status,
    bamboohr_sync_history,
    disconnect_bamboohr,

    # QuickBooks
    connect_quickbooks,
    quickbooks_callback,
    quickbooks_status,
    quickbooks_accounts,
    quickbooks_category_mappings,
    save_quickbooks_category_mapping,
    delete_quickbooks_category_mapping,
    export_report_quickbooks,
    quickbooks_report_export_status,
    quickbooks_export_history,
    retry_quickbooks_export,
    disconnect_quickbooks,

    # Integration dashboard/activity
    integration_activity,
    integration_dashboard_summary,
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
    # BAMBOOHR
    # ==========================================================

    path(
        "bamboohr/test/",
        test_bamboohr_connection,
        name="test-bamboohr-connection",
    ),

    path(
        "bamboohr/connect/",
        connect_bamboohr,
        name="connect-bamboohr",
    ),

    path(
        "bamboohr/employees/preview/",
        preview_bamboohr_employees,
        name="preview-bamboohr-employees",
    ),

    path(
        "bamboohr/sync/",
        sync_bamboohr,
        name="sync-bamboohr",
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
        "bamboohr/disconnect/",
        disconnect_bamboohr,
        name="disconnect-bamboohr",
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

    # ==========================================================
    # QUICKBOOKS ACCOUNTS / CATEGORY MAPPING
    # ==========================================================

    path(
        "quickbooks/accounts/",
        quickbooks_accounts,
        name="quickbooks-accounts",
    ),

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
    # QUICKBOOKS EXPORTS
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
        "quickbooks/disconnect/",
        disconnect_quickbooks,
        name="disconnect-quickbooks",
    ),
]