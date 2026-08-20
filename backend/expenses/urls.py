from django.urls import path

from .views import (
    company_policy_settings,
    mark_all_notifications_read,
    mark_notification_read,
    upload_receipt,
    retry_receipt_ai,
  
    submit_current_month_report,
    
    current_month_report,
   
    accounts_mark_paid,
    delete_expense_line_item,
 
    my_uploaded_expenses,
    admin_employee_expenses,
    
    create_or_update_workflow,
    add_workflow_step,
    view_workflow,
    deactivate_workflow_step,
    my_pending_approval_reports,
    my_approved_approval_reports,
    approve_report_step,
    reject_report_step,
    duplicate_receipts,
    admin_reports_list,
    update_workflow_step,
    delete_workflow,
    simulate_workflow_api,
    delete_receipt,
    approval_remove_line_item,
    approval_restore_line_item,
    approve_receipt_api,
    reject_receipt_api,
    remove_receipt_line_item_api,
    restore_receipt_line_item_api,
    get_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    get_unread_notification_count,
    payment_monthly_expense_history,
    payment_monthly_expense_detail,
    payment_employee_summary,
    payment_employee_history,
    payment_monthly_summary,
    payment_department_summary,
    payment_category_summary,
    

)

urlpatterns = [
    path("upload/", upload_receipt, name="upload-receipt"),
    path("upload-receipt/", upload_receipt, name="upload-receipt-v2"),
    path(
        "receipts/<uuid:receipt_id>/retry-ai/",
        retry_receipt_ai,
        name="retry-receipt-ai",
    ),
    
    path("reports/submit/", submit_current_month_report, name="submit-current-month-report"),
    
    path("reports/current/",current_month_report,name="current-month-report"),
    
    path("accounts/reports/<uuid:report_id>/paid/", accounts_mark_paid, name="accounts-mark-paid"),
    path("line-items/<uuid:line_item_id>/delete/",delete_expense_line_item,name="delete-expense-line-item"),
   
    path("my-uploaded-expenses/",my_uploaded_expenses,name="my-uploaded-expenses"),
    path("admin/employee/<uuid:employee_id>/expenses/",admin_employee_expenses,name="admin-employee-expenses"),
    
    path("workflow/save/", create_or_update_workflow, name="save-workflow"),
    path("workflow/steps/add/", add_workflow_step, name="add-workflow-step"),
    path("workflow/", view_workflow, name="view-workflow"),
    path("workflow/steps/<int:step_id>/deactivate/", deactivate_workflow_step, name="deactivate-workflow-step"),
    path(
    "approvals/my-pending/",
    my_pending_approval_reports,
    name="my-pending-approval-reports"
),
    path(
    "approvals/my-approved/",
    my_approved_approval_reports,
    name="my-approved-approval-reports"
),
    path(
    "reports/<uuid:report_id>/approve/",
    approve_report_step,
    name="approve-report-step"
),

path(
    "reports/<uuid:report_id>/reject/",
    reject_report_step,
    name="reject-report-step"
),
path(
    "duplicates/",
    duplicate_receipts,
    name="duplicate-receipts"
),    
path("duplicates/", duplicate_receipts, name="duplicate-receipts"),
path("admin/reports/",admin_reports_list,name="admin-reports-list"
),
path("workflow/steps/<int:step_id>/update/", update_workflow_step, name="update-workflow-step"),
path("workflow/<int:workflow_id>/", delete_workflow, name="delete-workflow"),
path(
    "workflow/simulate/",
    simulate_workflow_api,
    name="simulate-workflow",
),
path(
    "receipt/<uuid:receipt_id>/delete/",
    delete_receipt,
    name="delete-receipt",
),
path(
    "approvals/line-items/<uuid:line_item_id>/remove/",
    approval_remove_line_item,
    name="approval-remove-line-item",
),

path(
    "approvals/line-items/<uuid:line_item_id>/restore/",
    approval_restore_line_item,
    name="approval-restore-line-item",
),
path(
    "reports/<uuid:report_id>/receipts/<uuid:receipt_id>/approve/",
    approve_receipt_api,
    name="approve-receipt",
),

path(
    "reports/<uuid:report_id>/receipts/<uuid:receipt_id>/reject/",
    reject_receipt_api,
    name="reject-receipt",
),

path(
    "reports/<uuid:report_id>/line-items/<uuid:line_item_id>/remove/",
    remove_receipt_line_item_api,
    name="remove-receipt-line-item",
),

path(
    "reports/<uuid:report_id>/line-items/<uuid:line_item_id>/restore/",
    restore_receipt_line_item_api,
    name="restore-receipt-line-item",
),
path(
    "company/policy/settings/",
    company_policy_settings,
    name="company-policy-settings",
),
path(
    "notifications/",
    get_notifications,
    name="get-notifications",
),

path(
    "notifications/<uuid:notification_id>/read/",
    mark_notification_read,
    name="mark-notification-read",
),

path(
    "notifications/read-all/",
    mark_all_notifications_read,
    name="mark-all-notifications-read",
),
path(
    "notifications/unread-count/",
    get_unread_notification_count,
    name="get-unread-notification-count",
),

path(
    "payments/monthly-expenses/",
    payment_monthly_expense_history,
    name="payment-monthly-expense-history",
),
path(
    "payments/monthly-expenses/",
    payment_monthly_expense_history,
    name="payment-monthly-expense-history",
),

path(
    "payments/monthly-expenses/<uuid:report_id>/",
    payment_monthly_expense_detail,
    name="payment-monthly-expense-detail",
),

path(
    "payments/employees/",
    payment_employee_summary,
    name="payment-employee-summary",
),

path(
    "payments/employees/<int:employee_id>/history/",
    payment_employee_history,
    name="payment-employee-history",
),

path(
    "payments/summary/",
    payment_monthly_summary,
    name="payment-monthly-summary",
),

path(
    "payments/department-summary/",
    payment_department_summary,
    name="payment-department-summary",
),

path(
    "payments/category-summary/",
    payment_category_summary,
    name="payment-category-summary",
),
]