from django.urls import path

from .views import (
    upload_receipt,
    retry_receipt_ai,
    email_ingest_receipt,
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

)

urlpatterns = [
    path("upload/", upload_receipt, name="upload-receipt"),
    path(
        "receipts/<uuid:receipt_id>/retry-ai/",
        retry_receipt_ai,
        name="retry-receipt-ai",
    ),
    path("email-ingest/", email_ingest_receipt, name="email-ingest-receipt"),
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

]