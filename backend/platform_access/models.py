from django.db import models

from tenants.models import UserProfile
from tenants.models import Company


class PlatformPermission(models.Model):

    name = models.CharField(
        max_length=150,
        unique=True,
    )

    code = models.CharField(
        max_length=150,
        unique=True,
        db_index=True,
    )

    description = models.TextField(
        blank=True,
    )

    module = models.CharField(
        max_length=100,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "module",
            "name",
        ]

    def __str__(self):
        return self.name


class PlatformAdmin(models.Model):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="platform_admins",
    )

    user = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="platform_admin",
    )

    is_owner = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_by = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_platform_admins",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return self.user.user.email


class PlatformAdminPermission(models.Model):

    platform_admin = models.ForeignKey(
        PlatformAdmin,
        on_delete=models.CASCADE,
        related_name="permissions",
    )

    permission = models.ForeignKey(
        PlatformPermission,
        on_delete=models.CASCADE,
        related_name="platform_admins",
    )

    class Meta:
        unique_together = (
            "platform_admin",
            "permission",
        )

    def __str__(self):
        return (
            f"{self.platform_admin.user.user.email} - "
            f"{self.permission.code}"
        )