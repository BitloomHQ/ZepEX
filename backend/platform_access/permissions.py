from .models import PlatformAdmin


def is_legacy_platform_owner(user) -> bool:
    """True for PlatformOwner records and Django superusers (no UserProfile)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "platform_owner", None) or user.is_superuser)


def get_user_profile(user):
    return getattr(user, "profile", None)


def has_platform_permission(
    *,
    permission_code,
    profile=None,
    user=None,
):
    if user is None and profile is not None:
        user = getattr(profile, "user", None)

    if is_legacy_platform_owner(user):
        return True

    if profile is None and user is not None:
        profile = get_user_profile(user)

    if profile is None:
        return False

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
