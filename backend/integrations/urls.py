from django.urls import path

from .views import (
    integration_list,
    integration_detail,
    integration_delete,
    connect_integration,
    integration_provider_config,
    integration_authorize,
    integration_oauth_callback,
    sync_integration,
)

urlpatterns = [

    # -----------------------------------------
    # Integration list
    # -----------------------------------------

    path(
        "",
        integration_list,
        name="integration-list",
    ),

    # -----------------------------------------
    # Create / connect integration
    # -----------------------------------------

    path(
        "connect/",
        connect_integration,
        name="integration-connect",
    ),

    # -----------------------------------------
    # Provider configuration
    # -----------------------------------------

    path(
        "providers/<str:provider>/config/",
        integration_provider_config,
        name="integration-provider-config",
    ),

    # -----------------------------------------
    # OAuth authorization
    # -----------------------------------------

    path(
        "providers/<str:provider>/authorize/",
        integration_authorize,
        name="integration-authorize",
    ),

    # -----------------------------------------
    # OAuth callback
    # -----------------------------------------

    path(
        "providers/<str:provider>/callback/",
        integration_oauth_callback,
        name="integration-oauth-callback",
    ),

    # -----------------------------------------
    # Integration detail
    # -----------------------------------------

    path(
        "<uuid:integration_id>/",
        integration_detail,
        name="integration-detail",
    ),

    # -----------------------------------------
    # Delete integration
    # -----------------------------------------

    path(
        "<uuid:integration_id>/delete/",
        integration_delete,
        name="integration-delete",
    ),
    path(
    "<uuid:integration_id>/sync/",
    sync_integration,
    name="integration-sync",
),
]