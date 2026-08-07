from django.contrib.auth.models import User
from rest_framework import serializers
import uuid

from .media_utils import profile_picture_url
from .models import (
    Company,
    CompanyExchangeRate,
    Department,
    UserProfile,
    CompanyRole,
    ExternalDatabaseConfig,
    CompanyPolicy,
    PolicyCategoryRule,
    ReimbursementEmailConfig,
    CompanySMTPConfig,
)
from .models import PolicyVersion


class DepartmentSerializer(serializers.ModelSerializer):
    manager_name = serializers.SerializerMethodField()

    def get_manager_name(self, obj):
        if not obj.manager:
            return None
        user = obj.manager.user
        name = f"{user.first_name} {user.last_name}".strip()
        return name or user.email

    def validate_name(self, value):
        name = value.strip()

        request = self.context.get("request")

        if request:
            company = request.user.profile.company

            queryset = Department.objects.filter(
                company=company,
                name__iexact=name
            )

            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)

            if queryset.exists():
                raise serializers.ValidationError(
                    "Department with this name already exists."
                )

        return name

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "manager",
            "manager_name",
            "is_active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class CompanyRoleSerializer(serializers.ModelSerializer):

    class Meta:
        model = CompanyRole
        fields = [
            "id",
            "name",
            "can_upload_receipt",
            "can_submit_expense",
            "can_approve_expense",
            "can_mark_paid",
            "is_active",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]

    def validate_name(self, value):
        name = value.strip()

        request = self.context.get("request")

        if request:
            company = request.user.profile.company

            queryset = CompanyRole.objects.filter(
                company=company,
                name__iexact=name
            )

            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)

            if queryset.exists():
                raise serializers.ValidationError(
                    "Role with this name already exists."
                )

        return name


class UserProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        source="user.email",
        read_only=True
    )

    first_name = serializers.CharField(
        source="user.first_name",
        read_only=True
    )

    last_name = serializers.CharField(
        source="user.last_name",
        read_only=True
    )

    is_active = serializers.BooleanField(
        source="user.is_active",
        read_only=True
    )

    department_name = serializers.CharField(
        source="department.name",
        read_only=True
    )

    company_role_name = serializers.CharField(
        source="company_role.name",
        read_only=True
    )

    profile_picture = serializers.SerializerMethodField()

    def get_profile_picture(self, obj):
        return profile_picture_url(obj, self.context.get("request"))

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "company",
            "department",
            "department_name",
            "role",
            "company_role",
            "company_role_name",
            "phone_number",
            "address",
            "profile_picture",
            "is_active",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "company",
            "created_at",
        ]


class EmployeeCreateSerializer(serializers.Serializer):
    ROLE_CHOICES = (
        ("MANAGER", "Manager"),
        ("ACCOUNTS", "Accounts"),
        ("EMPLOYEE", "Employee"),
        ("COMPANY_ADMIN", "Company Admin"),
    )

    first_name = serializers.CharField(
        max_length=150
    )

    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True
    )

    email = serializers.EmailField()

    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )

    role = serializers.ChoiceField(
        choices=ROLE_CHOICES
    )

    department_id = serializers.UUIDField(
        required=False,
        allow_null=True
    )

    company_role_id = serializers.IntegerField(
        required=False,
        allow_null=True
    )

    def validate_email(self, value):
        email = value.lower().strip()

        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "User with this email already exists."
            )

        return email

    def validate(self, attrs):
        request = self.context.get("request")

        if not request:
            return attrs

        company = request.user.profile.company

        role = attrs.get("role")
        department_id = attrs.get("department_id")
        company_role_id = attrs.get("company_role_id")

        if role in ["EMPLOYEE", "MANAGER"] and not department_id:
            raise serializers.ValidationError({
                "department_id": "Department is required for Employee and Manager."
            })

        if department_id:
            try:
                Department.objects.get(
                    id=department_id,
                    company=company,
                    is_active=True
                )
            except Department.DoesNotExist:
                raise serializers.ValidationError({
                    "department_id": "Department not found for this company."
                })

        if company_role_id:
            try:
                CompanyRole.objects.get(
                    id=company_role_id,
                    company=company,
                    is_active=True
                )
            except CompanyRole.DoesNotExist:
                raise serializers.ValidationError({
                    "company_role_id": "Company role not found for this company."
                })

        return attrs


class CompanyUserUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    last_name = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    email = serializers.EmailField(
        required=False
    )

    role = serializers.ChoiceField(
        choices=["EMPLOYEE", "MANAGER", "ACCOUNTS", "COMPANY_ADMIN"],
        required=False
    )

    department_id = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    company_role_id = serializers.IntegerField(
        required=False,
        allow_null=True
    )

    phone_number = serializers.CharField(
        required=False,
        allow_blank=True
    )

    address = serializers.CharField(
        required=False,
        allow_blank=True
    )

    def validate_department_id(self, value):
        if value in (None, ""):
            return None
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            raise serializers.ValidationError("Must be a valid UUID.")

    def validate_email(self, value):
        email = value.lower().strip()
        user_id = self.context.get("user_id")

        existing = User.objects.filter(email__iexact=email)
        if user_id:
            existing = existing.exclude(id=user_id)

        if existing.exists():
            raise serializers.ValidationError(
                "User with this email already exists."
            )

        return email

    def validate(self, attrs):
        request = self.context.get("request")

        if not request:
            return attrs

        company = request.user.profile.company

        role = attrs.get("role") or self.context.get("profile_role")
        department_id = attrs.get("department_id")
        company_role_id = attrs.get("company_role_id")

        if role in ["EMPLOYEE", "MANAGER"] and not department_id:
            raise serializers.ValidationError({
                "department_id": "Department is required for Employee and Manager."
            })

        if department_id:
            try:
                Department.objects.get(
                    id=department_id,
                    company=company,
                    is_active=True
                )
            except Department.DoesNotExist:
                raise serializers.ValidationError({
                    "department_id": "Department not found for this company."
                })

        if company_role_id:
            try:
                CompanyRole.objects.get(
                    id=company_role_id,
                    company=company,
                    is_active=True
                )
            except CompanyRole.DoesNotExist:
                raise serializers.ValidationError({
                    "company_role_id": "Company role not found for this company."
                })

        return attrs


class DepartmentUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(
        required=False
    )

    manager_id = serializers.IntegerField(
        required=False,
        allow_null=True
    )


class ExternalDatabaseConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalDatabaseConfig
        fields = [
            "id",
            "db_engine",
            "db_host",
            "db_port",
            "db_name",
            "db_user",
            "db_password",
            "last_synced_at",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "last_synced_at",
            "created_at",
        ]

        extra_kwargs = {
            "db_password": {
                "write_only": True
            }
        }


from rest_framework import serializers
from .models import PolicyCategoryRule


class PolicyCategoryRuleSerializer(serializers.ModelSerializer):
    company_role_name = serializers.CharField(
        source="company_role.name",
        read_only=True
    )

    effective_limit = serializers.SerializerMethodField()

    class Meta:
        model = PolicyCategoryRule

        fields = [
            "id",
            "policy",
            "company_role",
            "company_role_name",
            "category_name",
            "max_amount",
            "currency",
            "is_unlimited",
            "effective_limit",
            "category_description",
            "policy_reason",
            "source_text",
            "ai_confidence",
            "is_ai_generated",
            "is_active",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "policy",
            "company_role_name",
            "effective_limit",
            "updated_at",
        ]

    def get_effective_limit(self, obj):
        if obj.is_unlimited:
            return "Unlimited"

        return f"{obj.max_amount} {obj.currency}"

    def validate_currency(self, value):
        value = value.strip().upper()

        if len(value) != 3:
            raise serializers.ValidationError(
                "Use a three-letter currency code such as INR or USD."
            )

        return value

    def validate_category_name(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        instance = getattr(self, "instance", None)

        policy = (
            instance.policy
            if instance
            else self.context.get("policy")
        )

        company_role = attrs.get(
            "company_role",
            instance.company_role if instance else None
        )

        category_name = attrs.get(
            "category_name",
            instance.category_name if instance else None
        )

        is_unlimited = attrs.get(
            "is_unlimited",
            instance.is_unlimited if instance else False
        )

        max_amount = attrs.get(
            "max_amount",
            instance.max_amount if instance else None
        )

        # Setting a concrete amount exits unlimited mode.
        if "max_amount" in attrs and max_amount is not None:
            attrs["is_unlimited"] = False
            is_unlimited = False

        if not company_role:
            raise serializers.ValidationError({
                "company_role": "Company role is required."
            })

        if not is_unlimited and max_amount is None:
            raise serializers.ValidationError({
                "max_amount": (
                    "max_amount is required when is_unlimited is false."
                )
            })

        if is_unlimited:
            attrs["max_amount"] = None

        policy_version = attrs.get("policy_version")
        if "policy_version" not in attrs:
            if instance is not None:
                policy_version = instance.policy_version
            else:
                policy_version = self.context.get("policy_version")

        duplicate = PolicyCategoryRule.objects.filter(
            policy=policy,
            company_role=company_role,
            category_name__iexact=category_name,
        )
        if policy_version is not None:
            duplicate = duplicate.filter(policy_version=policy_version)
        else:
            duplicate = duplicate.filter(policy_version__isnull=True)

        if instance:
            duplicate = duplicate.exclude(id=instance.id)

        if duplicate.exists():
            raise serializers.ValidationError({
                "category_name": (
                    f"A policy rule already exists for "
                    f"'{company_role.name}' and '{category_name}'."
                )
            })

        return attrs


class CompanyPolicySerializer(serializers.ModelSerializer):
    category_rules = PolicyCategoryRuleSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = CompanyPolicy
        fields = [
            "id",
            "company",
            "updated_at",
            "category_rules",
        ]

        read_only_fields = [
            "id",
            "company",
            "updated_at",
        ]


class ReimbursementEmailConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReimbursementEmailConfig
        fields = "__all__"

        read_only_fields = [
            "id",
            "company",
            "last_checked_at",
            "created_at",
        ]

        extra_kwargs = {
            "imap_password": {
                "write_only": True
            }
        }


class CompanySMTPConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanySMTPConfig
        fields = "__all__"

        read_only_fields = [
            "id",
            "company",
            "created_at",
            "updated_at",
        ]

        extra_kwargs = {
            "smtp_password": {
                "write_only": True
            }
        }


class CompanySerializer(serializers.ModelSerializer):

    class Meta:
        model = Company

        fields = [
            "id",
            "name",
            "domain",
            "reimbursement_email_prefix",
            "is_verified",
            "created_at",
            "reimbursement_email",
            "inbound_forwarding_email",
        ]


from .models import DatabaseSyncLog,CompanyFinanceSettings,Currency


class DatabaseSyncLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatabaseSyncLog
        fields = [
            "id",
            "company",
            "status",
            "records_created",
            "records_updated",
            "error_message",
            "started_at",
            "completed_at",
        ]        

class CompanyFinanceSettingsSerializer(serializers.ModelSerializer):

    base_currency_code = serializers.CharField(
        source="base_currency.code",
        read_only=True
    )

    base_currency_name = serializers.CharField(
        source="base_currency.name",
        read_only=True
    )

    base_currency_symbol = serializers.CharField(
        source="base_currency.symbol",
        read_only=True
    )

    base_currency_flag = serializers.CharField(
        source="base_currency.flag",
        read_only=True
    )

    class Meta:
        model = CompanyFinanceSettings

        fields = [
            "id",
            "company",

            "base_currency",
            "base_currency_code",
            "base_currency_name",
            "base_currency_symbol",
            "base_currency_flag",

            "auto_currency_conversion",

            # NEW FIELD
            "exchange_rate_source",

            "exchange_rate_provider",

            "allow_manual_exchange_rate",

            "decimal_places",
            "rounding_enabled",

            "timezone",
            "date_format",

            "last_exchange_sync",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "company",

            "base_currency_code",
            "base_currency_name",
            "base_currency_symbol",
            "base_currency_flag",

            "last_exchange_sync",

            "created_at",
            "updated_at",
        ]

class CurrencySerializer(serializers.ModelSerializer):

    class Meta:
        model = Currency
        fields = [
            "id",
            "code",
            "name",
            "symbol",
            "country",
            "flag",
            "is_active",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]        


class PolicyVersionSerializer(serializers.ModelSerializer):

    created_by_name = serializers.SerializerMethodField()
    activated_by_name = serializers.SerializerMethodField()
    total_rules = serializers.SerializerMethodField()

    class Meta:
        model = PolicyVersion

        fields = [
            "id",
            "version_number",
            "title",
            "description",
            "status",
            "is_active",

            "created_by",
            "created_by_name",

            "activated_by",
            "activated_by_name",

            "activated_at",

            "created_at",
            "updated_at",

            "total_rules",
        ]

    def get_created_by_name(self, obj):

        if obj.created_by:
            return obj.created_by.user.get_full_name()

        return None

    def get_activated_by_name(self, obj):

        if obj.activated_by:
            return obj.activated_by.user.get_full_name()

        return None

    def get_total_rules(self, obj):
        return obj.rules.count()
    

from .models import CompanyPreferences

class CompanyPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyPreferences

        fields = [
            "output_language_code",
            "output_language_name",
            "preserve_original_text",
            "updated_at",
        ]

        read_only_fields = [
            "updated_at",
        ]

    def validate_output_language_code(self, value):
        value = value.strip().lower()

        if not value:
            raise serializers.ValidationError(
                "Language code is required."
            )

        return value

    def validate_output_language_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Language name is required."
            )

        return value


class CompanyExchangeRateSerializer(serializers.ModelSerializer):

    from_currency = serializers.SlugRelatedField(
        slug_field="code",
        queryset=Currency.objects.all(),
    )

    to_currency = serializers.SlugRelatedField(
        slug_field="code",
        queryset=Currency.objects.all(),
    )

    class Meta:
        model = CompanyExchangeRate

        fields = (
            "id",
            "from_currency",
            "to_currency",
            "exchange_rate",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "updated_at",
        )

    def validate(self, attrs):
        from_currency = attrs.get(
            "from_currency",
            getattr(self.instance, "from_currency", None),
        )
        to_currency = attrs.get(
            "to_currency",
            getattr(self.instance, "to_currency", None),
        )
        exchange_rate = attrs.get(
            "exchange_rate",
            getattr(self.instance, "exchange_rate", None),
        )

        if from_currency and to_currency and from_currency == to_currency:
            raise serializers.ValidationError(
                "From and to currency must be different."
            )

        if exchange_rate is not None and exchange_rate <= 0:
            raise serializers.ValidationError(
                {"exchange_rate": "Exchange rate must be greater than zero."}
            )

        return attrs