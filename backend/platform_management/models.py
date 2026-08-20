from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User

class PlatformOwner(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="platform_owner"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.email
    
class CompanyRegistrationRequest(models.Model):

    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    )

    company_name = models.CharField(
        max_length=255
    )

    company_domain = models.CharField(
        max_length=255,
        unique=True
    )

    admin_name = models.CharField(
        max_length=255
    )

    admin_email = models.EmailField()

    reimbursement_email = models.EmailField()

    expected_employee_count = models.PositiveIntegerField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    otp = models.CharField(
        max_length=6,
        blank=True,
        null=True
    )

    otp_expires_at = models.DateTimeField(
        blank=True,
        null=True
    )

    is_email_verified = models.BooleanField(
        default=False
    )

    EMAIL_VERIFIED_VIA_EMAIL = "EMAIL"
    EMAIL_VERIFIED_VIA_ADMIN = "ADMIN"
    EMAIL_VERIFIED_VIA_CHOICES = (
        ("", "Not verified"),
        (EMAIL_VERIFIED_VIA_EMAIL, "Verified through email"),
        (EMAIL_VERIFIED_VIA_ADMIN, "Verified by admin"),
    )

    email_verified_via = models.CharField(
        max_length=16,
        choices=EMAIL_VERIFIED_VIA_CHOICES,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    reject_reason = models.TextField(
    blank=True,
    null=True
)

    def __str__(self):
        return self.company_name


class PlatformSettings(models.Model):

    platform_receipt_email = models.EmailField(
        default="receipts@zepex.ai"
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.platform_receipt_email  


