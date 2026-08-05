from rest_framework import serializers

from .models import (
    PlatformAdmin,
    PlatformPermission,
)


class PlatformPermissionSerializer(serializers.ModelSerializer):

    class Meta:
        model = PlatformPermission
        fields = [
            "id",
            "name",
            "code",
            "module",
        ]


class PlatformAdminSerializer(serializers.ModelSerializer):

    permissions = serializers.SerializerMethodField()
    user_name = serializers.CharField(
        source="user.user.get_full_name",
        read_only=True,
    )
    user_email = serializers.CharField(
        source="user.user.email",
        read_only=True,
    )

    class Meta:
        model = PlatformAdmin
        fields = [
            "id",
            "company",
            "user",
            "user_name",
            "user_email",
            "is_owner",
            "is_active",
            "permissions",
            "created_at",
        ]

    def get_permissions(self, obj):
        return list(
            obj.permissions.values_list(
                "permission__code",
                flat=True,
            )
        )