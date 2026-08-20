from rest_framework import serializers

from .models import CompanyRegistrationRequest
from rest_framework import serializers
from .models import CompanyRegistrationRequest, PlatformSettings





class CompanyRegistrationRequestSerializer(serializers.ModelSerializer):

    class Meta:
        model = CompanyRegistrationRequest
        fields = [
            "id",
            "company_name",
            "company_domain",
            "admin_name",
            "admin_email",
            "status",
            "created_at",
            "expected_employee_count",
            "otp",
            "is_email_verified",
            "email_verified_via",
            "reject_reason",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_at",
            "otp",
            "is_email_verified",
            "email_verified_via",
        ]

class PlatformSettingsSerializer(serializers.ModelSerializer):

    class Meta:
        model = PlatformSettings

        fields = [
            "id",
            "platform_receipt_email",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "updated_at",
        ]        
