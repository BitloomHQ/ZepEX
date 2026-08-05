from django.urls import path
from .views import login_api,change_password_api,forgot_password_api,reset_password_api,profile_detail_api, edit_profile_api

urlpatterns = [
    path("login/", login_api, name="login-api"),
    path("change-password/", change_password_api, name="change-password-api"),
   path(
    "forgot-password/",
    forgot_password_api,
),

path(
    "reset-password/",
    reset_password_api,
),
    path("profile/", profile_detail_api, name="profile-detail"),
    path("edit-profile/", edit_profile_api, name="edit-profile"),
]