from rest_framework import serializers

from .models import CompanyIntegration


class CompanyIntegrationSerializer(
    serializers.ModelSerializer
):

    provider_name = serializers.CharField(
        source="get_provider_display",
        read_only=True,
    )

    configured = serializers.SerializerMethodField()

    class Meta:
        model = CompanyIntegration

        fields = [
            "id",
            "provider",
            "provider_name",

            "is_connected",
            "is_active",

            "configured",

            "last_synced_at",
            "last_sync_status",
            "last_sync_error",

            "created_at",
            "updated_at",
        ]

        read_only_fields = fields

    def get_configured(self, obj):

        try:
            credential = obj.credential
        except Exception:
            return False

        return bool(
            credential
            and credential.encrypted_config
        )


from rest_framework import serializers

from .models import (
    CompanyIntegration,
    IntegrationSyncLog,
)


class BambooHRStatusSerializer(
    serializers.ModelSerializer
):
    provider_name = serializers.CharField(
        source="get_provider_display",
        read_only=True,
    )

    configured = serializers.SerializerMethodField()

    class Meta:
        model = CompanyIntegration

        fields = [
            "id",
            "provider",
            "provider_name",
            "is_connected",
            "is_active",
            "configured",
            "last_synced_at",
            "last_sync_status",
            "last_sync_error",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields

    def get_configured(self, obj):
        try:
            credential = obj.credential
        except Exception:
            return False

        return bool(
            credential
            and credential.encrypted_config
        )


class IntegrationSyncLogSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = IntegrationSyncLog

        fields = [
            "id",
            "status",
            "trigger",
            "records_received",
            "records_created",
            "records_updated",
            "records_skipped",
            "error_message",
            "stats",
            "errors",
            "started_at",
            "completed_at",
        ]

        read_only_fields = fields

from .models import QuickBooksCategoryMapping


class QuickBooksCategoryMappingSerializer(
    serializers.ModelSerializer
):

    class Meta:

        model = QuickBooksCategoryMapping

        fields = [
            "id",
            "zepex_category",
            "quickbooks_account_id",
            "quickbooks_account_name",
            "quickbooks_account_type",
            "quickbooks_account_sub_type",
            "is_active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]