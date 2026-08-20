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
from expenses.models import (
    ApprovalWorkflow,
    ApprovalWorkflowStep,
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
            "can_manage_company",
            "can_manage_roles",
            "can_manage_employees",
            "can_manage_departments",
            "can_manage_policy",
            "can_manage_workflow",
            "can_view_company_reports",
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
            "is_active",
            "created_at",
            "reimbursement_email",
            "imap_host",
            "imap_port",
            "imap_username",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "reimbursement_email_prefix",
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


from rest_framework import serializers

from .models import Company
from .encryption_services import (
    encrypt_imap_password,
)

class CompanyImapConfigSerializer(serializers.ModelSerializer):

    imap_configured = serializers.SerializerMethodField()

    class Meta:
        model = Company

        fields = [
            "reimbursement_email",
            "imap_host",
            "imap_port",
            "imap_username",
            "imap_password",
            "imap_configured",
        ]

        extra_kwargs = {
            "imap_password": {
                "write_only": True,
                "required": False,
            },
        }

    def get_imap_configured(self, obj):

        return bool(
            obj.reimbursement_email
            and obj.imap_host
            and obj.imap_port
            and obj.imap_username
            and obj.imap_password
        )

    def validate_imap_port(self, value):

        if value < 1 or value > 65535:
            raise serializers.ValidationError(
                "IMAP port must be between 1 and 65535."
            )

        return value

    def update(self, instance, validated_data):

        # Plain app password coming from frontend
        password = validated_data.pop(
            "imap_password",
            None,
        )

        # Update normal fields
        for field, value in validated_data.items():
            setattr(
                instance,
                field,
                value,
            )

        # Encrypt app password before database storage
        if password:

            instance.imap_password = (
                encrypt_imap_password(
                    password
                )
            )

        instance.save()

        return instance
    

class CompanySettingsSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = Company

        fields = [
            "id",
            "name",
            "domain",
            "reimbursement_email",
            "is_verified",
            "is_active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "is_verified",
            "is_active",
            "created_at",
            "updated_at",
        ]

class CompanyRoleUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = CompanyRole

        fields = [
            "id",
            "name",

            # Expense permissions
            "can_upload_receipt",
            "can_submit_expense",
            "can_approve_expense",
            "can_mark_paid",

            # Management permissions
            "can_manage_company",
            "can_manage_roles",
            "can_manage_employees",
            "can_manage_departments",
            "can_manage_policy",
            "can_manage_workflow",
            "can_view_company_reports",
        ]

        read_only_fields = [
            "id",
        ]

class EmployeeUpdateSerializer(serializers.ModelSerializer):

    email = serializers.EmailField(
        source="user.email",
        required=False,
    )

    first_name = serializers.CharField(
        source="user.first_name",
        required=False,
        allow_blank=True,
    )

    last_name = serializers.CharField(
        source="user.last_name",
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = UserProfile

        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "department",
            "company_role",
            "manager",
        ]

        read_only_fields = [
            "id",
        ]

    def validate_department(self, department):

        profile = self.context["request"].user.profile

        if department.company_id != profile.company_id:
            raise serializers.ValidationError(
                "Department does not belong to your company."
            )

        return department

    def validate_company_role(self, company_role):

        profile = self.context["request"].user.profile

        if company_role.company_id != profile.company_id:
            raise serializers.ValidationError(
                "Company role does not belong to your company."
            )

        return company_role

    def validate_manager(self, manager):

        profile = self.context["request"].user.profile

        if manager.company_id != profile.company_id:
            raise serializers.ValidationError(
                "Manager does not belong to your company."
            )

        return manager

    def update(self, instance, validated_data):

        user_data = validated_data.pop(
            "user",
            {}
        )

        user = instance.user

        for attr, value in user_data.items():
            setattr(
                user,
                attr,
                value,
            )

        user.save()

        for attr, value in validated_data.items():
            setattr(
                instance,
                attr,
                value,
            )

        instance.save()

        return instance


class DepartmentUpdateSerializer(serializers.ModelSerializer):

    manager_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Department

        fields = [
            "id",
            "name",
            "manager_id",
        ]

        read_only_fields = [
            "id",
        ]

    def update(self, instance, validated_data):
        manager_id = validated_data.pop("manager_id", "__omit__")
        instance = super().update(instance, validated_data)

        if manager_id == "__omit__":
            return instance

        request = self.context.get("request")
        company = request.user.profile.company if request else instance.company

        if manager_id is None:
            instance.manager = None
        else:
            manager = UserProfile.objects.get(
                id=manager_id,
                company=company,
                user__is_active=True,
            )
            instance.manager = manager

        instance.save(update_fields=["manager", "updated_at"])
        return instance

class CompanyPolicyUpdateSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = CompanyPolicy

        fields = [
            "old_bill_limit_days",
            "auto_approve_if_no_violation",
        ]

class ApprovalWorkflowStepSerializer(
    serializers.ModelSerializer
):

    approver_role_name = serializers.CharField(
        source="approver_role.name",
        read_only=True,
    )

    specific_user_name = serializers.SerializerMethodField()

    specific_user_email = serializers.EmailField(
        source="specific_user.user.email",
        read_only=True,
    )

    department_name = serializers.CharField(
        source="department.name",
        read_only=True,
    )

    approver_type_display = serializers.CharField(
        source="get_approver_type_display",
        read_only=True,
    )

    routing_type_display = serializers.CharField(
        source="get_routing_type_display",
        read_only=True,
    )

    class Meta:
        model = ApprovalWorkflowStep

        fields = [
            "id",

            "step_order",

            "approver_type",
            "approver_type_display",

            "approver_role",
            "approver_role_name",

            "specific_user",
            "specific_user_name",
            "specific_user_email",

            "department",
            "department_name",

            "routing_type",
            "routing_type_display",

            "is_active",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "approver_role_name",
            "specific_user_name",
            "specific_user_email",
            "department_name",
            "approver_type_display",
            "routing_type_display",
            "created_at",
        ]

    def get_specific_user_name(self, obj):

        if not obj.specific_user:
            return None

        user = obj.specific_user.user

        return (
            user.get_full_name()
            or user.email
        )


class ApprovalWorkflowSerializer(
    serializers.ModelSerializer
):

    start_role_name = serializers.CharField(
        source="start_role.name",
        read_only=True,
    )

    steps = ApprovalWorkflowStepSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = ApprovalWorkflow

        fields = [
            "id",
            "name",

            "start_role",
            "start_role_name",

            "is_active",

            "steps",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "start_role_name",
            "steps",
            "created_at",
            "updated_at",
        ]

class ApprovalWorkflowUpdateSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = ApprovalWorkflow

        fields = [
            "name",
            "start_role",
            "is_active",
        ]

    def validate_start_role(self, role):

        profile = self.context["request"].user.profile

        if role.company_id != profile.company_id:
            raise serializers.ValidationError(
                "Start role does not belong to your company."
            )

        return role

class ApprovalWorkflowStepWriteSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = ApprovalWorkflowStep

        fields = [
            "step_order",
            "approver_type",
            "approver_role",
            "specific_user",
            "department",
            "routing_type",
            "is_active",
        ]

    def validate(self, attrs):

        request = self.context["request"]

        profile = request.user.profile

        company = profile.company

        # --------------------------------------------------
        # Existing values for PATCH
        # --------------------------------------------------

        approver_type = attrs.get(
            "approver_type",
            getattr(
                self.instance,
                "approver_type",
                None,
            ),
        )

        approver_role = attrs.get(
            "approver_role",
            getattr(
                self.instance,
                "approver_role",
                None,
            ),
        )

        specific_user = attrs.get(
            "specific_user",
            getattr(
                self.instance,
                "specific_user",
                None,
            ),
        )

        department = attrs.get(
            "department",
            getattr(
                self.instance,
                "department",
                None,
            ),
        )

        routing_type = attrs.get(
            "routing_type",
            getattr(
                self.instance,
                "routing_type",
                None,
            ),
        )

        # --------------------------------------------------
        # Company isolation
        # --------------------------------------------------

        if (
            approver_role
            and approver_role.company_id != company.id
        ):
            raise serializers.ValidationError(
                {
                    "approver_role": (
                        "Approver role does not belong "
                        "to your company."
                    )
                }
            )

        if (
            specific_user
            and specific_user.company_id != company.id
        ):
            raise serializers.ValidationError(
                {
                    "specific_user": (
                        "Specific user does not belong "
                        "to your company."
                    )
                }
            )

        if (
            department
            and department.company_id != company.id
        ):
            raise serializers.ValidationError(
                {
                    "department": (
                        "Department does not belong "
                        "to your company."
                    )
                }
            )

        # --------------------------------------------------
        # APPROVER TYPE validation
        # --------------------------------------------------

        if (
            approver_type
            == ApprovalWorkflowStep.APPROVER_COMPANY_ROLE
        ):

            if not approver_role:
                raise serializers.ValidationError(
                    {
                        "approver_role": (
                            "approver_role is required "
                            "when approver_type is COMPANY_ROLE."
                        )
                    }
                )

            # Remove incompatible value
            attrs["specific_user"] = None

        elif (
            approver_type
            == ApprovalWorkflowStep.APPROVER_SPECIFIC_USER
        ):

            if not specific_user:
                raise serializers.ValidationError(
                    {
                        "specific_user": (
                            "specific_user is required "
                            "when approver_type is SPECIFIC_USER."
                        )
                    }
                )

            attrs["approver_role"] = None

        elif approver_type in [
            ApprovalWorkflowStep.APPROVER_REPORTING_MANAGER,
            ApprovalWorkflowStep.APPROVER_DEPARTMENT_MANAGER,
        ]:

            attrs["approver_role"] = None
            attrs["specific_user"] = None

        # --------------------------------------------------
        # ROUTING validation
        # --------------------------------------------------

        if (
            routing_type
            == ApprovalWorkflowStep.ROUTING_DEPARTMENT
        ):

            if not department:
                raise serializers.ValidationError(
                    {
                        "department": (
                            "Department is required for "
                            "department-based routing."
                        )
                    }
                )

        elif (
            routing_type
            == ApprovalWorkflowStep.ROUTING_COMPANY
        ):

            attrs["department"] = None

        return attrs