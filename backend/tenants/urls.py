from django.urls import path

from .views import (
    company_imap_config,
    company_policy_settings,
    create_department,
    list_departments,
    create_employee,
    list_employees,
    assign_missing_company_roles_view,
    assign_manager,
    get_database_config,
    save_database_config,
    create_company_policy,
    create_policy_rule,
    list_policy_rules,
    get_reimbursement_email_config,
    save_reimbursement_email_config,
    get_smtp_config,
    
    edit_company_user,
    deactivate_company_user,
    activate_company_user,
    test_company_imap_connection,
    update_department,
    deactivate_department,
    activate_department,
    update_employee,
    update_policy_rule,
    deactivate_policy_rule,
    activate_policy_rule,
    delete_company_user,
    delete_department,
    create_company_role,
    company_roles,
    update_company_role,
    deactivate_company_role,
    test_database_connection,
    sync_external_database,
    database_sync_status,
    database_sync_logs,
    database_sync_dashboard,
    import_departments,
    import_company_roles,
    import_employees,
    import_policy_rules,
    download_department_template,
    download_roles_template,
    download_employees_template,
    download_policy_rules_template,
    department_template_info,
    roles_template_info,
    employees_template_info,
    policy_rules_template_info,
    send_employee_invites,
    company_finance_settings,
    currency_list,
    currency_detail,
    preview_role_policy,
    simulate_policy_rule,
    copy_role_policy,
    upload_policy_document,
    confirm_policy_document_import,
    get_policy_document_preview,
    update_policy_document_preview,
    revalidate_policy_document_preview,
    create_policy_version_api,
    list_policy_versions,
    get_policy_version,
    activate_policy_version_api,
    archive_policy_version_api,
    duplicate_policy_version_api,
    rollback_policy_version_api,
    delete_draft_policy_version_api,
    compare_policy_versions_api,
    company_language_preferences,
    company_exchange_rates,
    update_company_exchange_rate,
    delete_company_exchange_rate,
    get_company_workflows,
    update_company_workflow,
    create_workflow_step,
    update_workflow_step,
    delete_workflow_step,
    
    


)

urlpatterns = [
    path("departments/", create_department, name="create-department"),
    path("departments/list/", list_departments, name="list-departments"),
    path("departments/<uuid:department_id>/update/", update_department, name="update-department"),
    path("departments/<uuid:department_id>/deactivate/", deactivate_department, name="deactivate-department"),
    path("departments/<uuid:department_id>/activate/", activate_department, name="activate-department"),
    path("departments/<uuid:department_id>/delete/", delete_department, name="delete-department"),

    path("employees/", create_employee, name="create-employee"),
    path("employees/list/", list_employees, name="list-employees"),
    path(
        "employees/assign-missing-roles/",
        assign_missing_company_roles_view,
        name="assign-missing-company-roles",
    ),

    path("users/<int:user_id>/edit/", edit_company_user, name="edit-company-user"),
    path("users/<int:user_id>/deactivate/", deactivate_company_user, name="deactivate-company-user"),
    path("users/<int:user_id>/activate/", activate_company_user, name="activate-company-user"),
    path("users/<int:user_id>/delete/", delete_company_user, name="delete-company-user"),

    path("assign-manager/", assign_manager, name="assign-manager"),

    path("roles/create/", create_company_role, name="create-company-role"),
    path("roles/", company_roles, name="company-roles"),
    path("roles/<int:role_id>/update/", update_company_role, name="update-company-role"),
    path("roles/<int:role_id>/deactivate/", deactivate_company_role, name="deactivate-company-role"),

    path("database-config/", get_database_config, name="database-config"),
    path("database-config/save/", save_database_config, name="save-database-config"),
    path("database/test-connection/", test_database_connection, name="test-database-connection"),
    path("database/sync/", sync_external_database, name="sync-external-database"),
    path("database/status/", database_sync_status, name="database-sync-status"),

    path("policy/", create_company_policy, name="company-policy"),
    path("policy/rules/create/", create_policy_rule, name="create-policy-rule"),
    path("policy/rules/", list_policy_rules, name="list-policy-rules"),
    path("policy/rules/<uuid:rule_id>/update/", update_policy_rule, name="update-policy-rule"),
    path("policy/rules/<uuid:rule_id>/deactivate/", deactivate_policy_rule, name="deactivate-policy-rule"),
    path("policy/rules/<uuid:rule_id>/activate/", activate_policy_rule, name="activate-policy-rule"),

    path("reimbursement-email/", get_reimbursement_email_config, name="get-reimbursement-email-config"),
    path("reimbursement-email/save/", save_reimbursement_email_config, name="save-reimbursement-email-config"),

    path("smtp-config/", get_smtp_config, name="get-smtp-config"),
    
    path("database/sync-logs/",database_sync_logs,name="database-sync-logs"),
    path(
    "database/sync-dashboard/",
    database_sync_dashboard,
    name="database-sync-dashboard"
),
path(
    "departments/import/",
    import_departments,
    name="import-departments"
),
path(
    "roles/import/",
    import_company_roles,
    name="import-company-roles"
),
path(
    "employees/import/",
    import_employees,
    name="import-employees"
),
path(
    "policy-rules/import/",
    import_policy_rules,
    name="import-policy-rules"
),
path("departments/template/", download_department_template, name="department-template"),
path("roles/template/", download_roles_template, name="roles-template"),
path("employees/template/", download_employees_template, name="employees-template"),
path("policy-rules/template/", download_policy_rules_template, name="policy-rules-template"),
path("departments/template/", department_template_info, name="department-template-info"),
path("departments/template/download/", download_department_template, name="department-template-download"),

path("roles/template/", roles_template_info, name="roles-template-info"),
path("roles/template/download/", download_roles_template, name="roles-template-download"),

path("employees/template/", employees_template_info, name="employees-template-info"),
path("employees/template/download/", download_employees_template, name="employees-template-download"),

path("policy-rules/template/", policy_rules_template_info, name="policy-rules-template-info"),
path("policy-rules/template/download/", download_policy_rules_template, name="policy-rules-template-download"),
path(
    "employees/send-invites/",
    send_employee_invites,
    name="send-employee-invites"
),

path(
    "company/finance-settings/",
    company_finance_settings,
    name="company-finance-settings"
),
path(
    "currencies/",
    currency_list,
    name="currency-list"
),

path(
    "currencies/<str:code>/",
    currency_detail,
    name="currency-detail"
),
path(
    "policy/preview/",
    preview_role_policy,
    name="preview-role-policy"
),
path(
    "policy/simulate/",
    simulate_policy_rule,
    name="simulate-policy-rule"
),
path(
    "policy/copy/",
    copy_role_policy,
    name="copy-role-policy"
),

path(
    "policy/document/upload/",
    upload_policy_document,
    name="upload-policy-document",
),

path(
    "policy/document/<uuid:import_id>/confirm/",
    confirm_policy_document_import,
    name="confirm-policy-document-import",
),
path(
    "policy/document/<uuid:import_id>/preview/",
    get_policy_document_preview,
    name="get-policy-document-preview",
),

path(
    "policy/document/<uuid:import_id>/preview/update/",
    update_policy_document_preview,
    name="update-policy-document-preview",
),

path(
    "policy/document/<uuid:import_id>/preview/revalidate/",
    revalidate_policy_document_preview,
    name="revalidate-policy-document-preview",
),

path(
    "policy/versions/create/",
    create_policy_version_api,
    name="create-policy-version",
),

path(
    "policy/versions/",
    list_policy_versions,
    name="list-policy-versions",
),

path(
    "policy/versions/<uuid:version_id>/",
    get_policy_version,
    name="get-policy-version",
),

path(
    "policy/versions/<uuid:version_id>/activate/",
    activate_policy_version_api,
    name="activate-policy-version",
),

path(
    "policy/versions/<uuid:version_id>/archive/",
    archive_policy_version_api,
    name="archive-policy-version",
),

path(
    "policy/versions/<uuid:version_id>/duplicate/",
    duplicate_policy_version_api,
    name="duplicate-policy-version",
),

path(
    "policy/versions/<uuid:version_id>/rollback/",
    rollback_policy_version_api,
    name="rollback-policy-version",
),

path(
    "policy/versions/<uuid:version_id>/delete/",
    delete_draft_policy_version_api,
    name="delete-draft-policy-version",
),
path(
    "policy/versions/compare/",
    compare_policy_versions_api,
    name="compare-policy-versions",
),
path(
    "company/language-preferences/",
    company_language_preferences,
    name="company-language-preferences",
),
path(
    "company/exchange-rates/",
    company_exchange_rates,
    name="company-exchange-rates",
),

path(
    "company/exchange-rates/<int:rate_id>/",
    update_company_exchange_rate,
    name="update-company-exchange-rate",
),

path(
    "company/exchange-rates/<int:rate_id>/delete/",
    delete_company_exchange_rate,
    name="delete-company-exchange-rate",
),
path(
    "company/imap-config/",
    company_imap_config,
    name="company-imap-config",
),
path(
    "company/imap-config/test/",
    test_company_imap_connection,
    name="test-company-imap-connection",
),
path(
    "company/imap-config/",
    company_imap_config,
    name="company-imap-config",
),
path(
    "roles/<uuid:role_id>/",
    update_company_role,
    name="update-company-role",
),
path(
    "employees/<uuid:employee_id>/",
    update_employee,
    name="update-employee",
),
path(
    "departments/<uuid:department_id>/",
    update_department,
    name="update-department",
),
path(
    "company/policy/",
    company_policy_settings,
    name="company-policy-settings",
),
path(
    "workflows/",
    get_company_workflows,
    name="get-company-workflows",
),

path(
    "workflows/<int:workflow_id>/",
    update_company_workflow,
    name="update-company-workflow",
),

path(
    "workflows/<int:workflow_id>/steps/",
    create_workflow_step,
    name="create-workflow-step",
),

path(
    "workflow-steps/<int:step_id>/",
    update_workflow_step,
    name="update-workflow-step",
),

path(
    "workflow-steps/<int:step_id>/delete/",
    delete_workflow_step,
    name="delete-workflow-step",
),
]