from django.urls import path

from .views import (
    create_platform_admin,
    create_platform_user,
    list_platform_permissions,
    list_platform_admins,
    update_platform_admin,
    toggle_platform_admin,
    delete_platform_admin,
)

urlpatterns = [

    path(
        "create/",
        create_platform_admin,
        name="create-platform-admin",
    ),

    path(
        "users/create/",
        create_platform_user,
        name="create-platform-user",
    ),

    path(
        "permissions/",
        list_platform_permissions,
        name="platform-permissions",
    ),

    path(
        "list/",
        list_platform_admins,
        name="platform-admin-list",
    ),

    path(
        "<int:admin_id>/update/",
        update_platform_admin,
        name="update-platform-admin",
    ),

    path(
        "<int:admin_id>/toggle/",
        toggle_platform_admin,
        name="toggle-platform-admin",
    ),

    path(
        "<int:admin_id>/delete/",
        delete_platform_admin,
        name="delete-platform-admin",
    ),
]