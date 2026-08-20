from django.urls import path

from .views import (
    create_company_request,
    list_company_requests,
    approve_company_request,
    reject_company_request,
    company_list,
    pending_company_list,
    update_platform_company,
    deactivate_company,
    activate_company,
    delete_company,
    platform_company_details,
    verify_company_registration_otp,
    request_company_registration_otp,
    platform_settings,
    update_platform_settings
)

urlpatterns = [

    path(
        "register-company/",
        create_company_request,
        name="register-company"
    ),

    path(
        "requests/",
        list_company_requests,
        name="list-company-requests"
    ),

    path(
        "approve/<int:request_id>/",
        approve_company_request,
        name="approve-company-request"
    ),

    path(
        "reject/<int:request_id>/",
        reject_company_request,
        name="reject-company-request"
    ),
    path(
    "companies/",
    company_list,
    name="company-list"
),

path(
    "pending-companies/",
    pending_company_list,
    name="pending-company-list"
),
path(
    "companies/<uuid:company_id>/deactivate/",
    deactivate_company,
    name="deactivate-company"
),

path("companies/<uuid:company_id>/activate/", activate_company,name="activate-company"),
path(
    "companies/<uuid:company_id>/",
    update_platform_company,
    name="update-platform-company",
),
path("companies/<uuid:company_id>/delete/",delete_company,name="delete-company"
),
path(
    "companies/<uuid:company_id>/details/",
    platform_company_details,
    name="platform-company-details"
),
path(
    "company-registration/verify-otp/",
    verify_company_registration_otp,
    name="verify-company-registration-otp"
),
path(
    "company-requests/request-otp/",
    request_company_registration_otp,
    name="request-company-registration-otp"
),

path(
    "settings/",
    platform_settings,
    name="platform-settings"
),

path(
    "settings/update/",
    update_platform_settings,
    name="update-platform-settings"
),



]