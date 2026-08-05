from .models import PlatformAdmin


def has_platform_permission(
    *,
    profile,
    permission_code,
):

    try:
        admin = PlatformAdmin.objects.get(
            user=profile,
            is_active=True,
        )
    except PlatformAdmin.DoesNotExist:
        return False

    if admin.is_owner:
        return True

    return admin.permissions.filter(
        permission__code=permission_code,
    ).exists()