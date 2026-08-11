from django.utils import timezone

from .models import Integration
from .providers.registry import get_provider


class IntegrationSyncService:

    @staticmethod
    def sync_integration(integration):

        if integration.status != Integration.STATUS_CONNECTED:
            raise ValueError(
                "Integration is not connected."
            )

        provider = get_provider(
            integration.provider,
            integration,
        )

        try:
            result = provider.sync()

            integration.last_synced_at = timezone.now()
            integration.last_error = None
            integration.status = (
                Integration.STATUS_CONNECTED
            )

            integration.save(
                update_fields=[
                    "last_synced_at",
                    "last_error",
                    "status",
                    "updated_at",
                ]
            )

            return {
                "success": True,
                "provider": integration.provider,
                "result": result,
            }

        except Exception as exc:

            integration.status = (
                Integration.STATUS_ERROR
            )

            integration.last_error = str(exc)

            integration.save(
                update_fields=[
                    "status",
                    "last_error",
                    "updated_at",
                ]
            )

            raise