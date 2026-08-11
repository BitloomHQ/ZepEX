from rest_framework import serializers

from .models import Integration


class IntegrationSerializer(serializers.ModelSerializer):

    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )

    provider_display = serializers.CharField(
        source="get_provider_display",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    is_token_expired = serializers.BooleanField(
        read_only=True,
    )

    class Meta:
        model = Integration

        fields = [
            "id",
            "category",
            "category_display",
            "provider",
            "provider_display",
            "status",
            "status_display",
            "external_account_id",
            "scope",
            "connected_at",
            "last_synced_at",
            "last_error",
            "is_token_expired",
            "bamboohr_domain",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "status",
            "external_account_id",
            "scope",
            "connected_at",
            "last_synced_at",
            "last_error",
            "is_token_expired",
            "bamboohr_domain",
            "created_at",
            "updated_at",
        ]