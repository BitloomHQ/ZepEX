from .models import (
    PlatformAdmin,
    PlatformAdminPermission,
    PlatformPermission,
)


def assign_permissions(
    *,
    platform_admin,
    permission_codes,
):
    PlatformAdminPermission.objects.filter(
        platform_admin=platform_admin,
    ).delete()

    permissions = PlatformPermission.objects.filter(
        code__in=permission_codes,
        is_active=True,
    )

    PlatformAdminPermission.objects.bulk_create(
        [
            PlatformAdminPermission(
                platform_admin=platform_admin,
                permission=permission,
            )
            for permission in permissions
        ]
    )