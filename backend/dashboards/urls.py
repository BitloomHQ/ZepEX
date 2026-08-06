from django.urls import path

from .views import (
    employee_dashboard,
    approver_dashboard,
    payment_dashboard,
    company_admin_dashboard,
    platform_dashboard,
    dashboard_router,
)

urlpatterns = [

    path(
        "employee/",
        employee_dashboard,
        name="employee-dashboard"
    ),

    path(
    "approver/",
    approver_dashboard,
    name="approver-dashboard"
),

   path(
    "payments/",
    payment_dashboard,
    name="payment-dashboard"
),

    path(
        "company-admin/",
        company_admin_dashboard,
        name="company-admin-dashboard"
    ),

    path(
    "platform-owner/",
    platform_dashboard,
    name="platform-owner-dashboard"
),

    path(
    "",
    dashboard_router,
    name="dashboard-router"
),

]