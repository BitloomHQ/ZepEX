from rest_framework import serializers

from .models import (
    ExpenseReport,
    ExpenseSubmission,
    ExpenseReceipt,
    ExpenseLineItem,
    ApprovalHistory,
    ApprovalWorkflow,
    ApprovalWorkflowStep
)
from .report_utils import is_payment_queue_role
from tenants.media_utils import profile_picture_url



class ExpenseLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseLineItem
        fields = [
            "id",
            "description",
            "category",
            "subcategory",
            "vendor",
            "amount",
            "bill_date",
            "is_violating",
            "violation_reason",
            "created_at",
        ]


class ExpenseReceiptSerializer(serializers.ModelSerializer):

    # Existing field
    line_items = ExpenseLineItemSerializer(
        many=True,
        read_only=True
    )

    # Explicit frontend-friendly alias
    claim_lines = ExpenseLineItemSerializer(
        source="line_items",
        many=True,
        read_only=True
    )

    employee_email = serializers.EmailField(
        source="employee.user.email",
        read_only=True
    )

    department_name = serializers.CharField(
        source="department.name",
        read_only=True
    )

    class Meta:
        model = ExpenseReceipt

        fields = [
            "id",
            "report",
            "submission",
            "company",

            "employee",
            "employee_email",

            "department",
            "department_name",

            "receipt_file",

            "vendor_name",
            "invoice_date",

            # Existing
            "total_amount",
            "currency",

            # Original receipt
            "original_amount",
            "original_currency",

            # Company reimbursement
            "company_amount",
            "company_currency",

            # Exchange details
            "exchange_rate",
            "exchange_rate_date",
            "exchange_rate_provider",

            # Status
            "status",

            # AI extraction
            "ai_status",
            "ai_error_message",
            "ai_retry_count",

            # Policy
            "policy_violation_reason",
            "has_duplicate_violation",
            "has_old_bill_violation",
            "has_amount_violation",
            "has_any_violation",

            # Expense line items
            "line_items",

            # Frontend alias
            "claim_lines",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "report",
            "submission",
            "company",

            "employee",
            "department",

            "vendor_name",
            "invoice_date",

            "total_amount",
            "currency",

            "original_amount",
            "original_currency",

            "company_amount",
            "company_currency",

            "exchange_rate",
            "exchange_rate_date",
            "exchange_rate_provider",

            "status",

            "ai_status",
            "ai_error_message",
            "ai_retry_count",

            "policy_violation_reason",
            "has_duplicate_violation",
            "has_old_bill_violation",
            "has_amount_violation",
            "has_any_violation",

            "line_items",
            "claim_lines",

            "created_at",
            "updated_at",
        ]

class ApprovalHistorySerializer(serializers.ModelSerializer):
    action_by_email = serializers.EmailField(
        source="action_by.user.email",
        read_only=True
    )

    action_by_role = serializers.CharField(
        source="action_by.company_role.name",
        read_only=True
    )

    class Meta:
        model = ApprovalHistory
        fields = [
            "id",
            "report",
            "receipt",
            "action_by",
            "action_by_email",
            "action_by_role",
            "action",
            "comments",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]


class ApprovalWorkflowStepSerializer(serializers.ModelSerializer):

    approver_role_name = serializers.CharField(
        source="approver_role.name",
        read_only=True
    )

    department_name = serializers.CharField(
        source="department.name",
        read_only=True
    )

    approver_type_name = serializers.CharField(
        source="get_approver_type_display",
        read_only=True
    )

    specific_user_name = serializers.CharField(
        source="specific_user.user.get_full_name",
        read_only=True
    )

    specific_user_email = serializers.EmailField(
        source="specific_user.user.email",
        read_only=True
    )

    class Meta:
        model = ApprovalWorkflowStep

        fields = [
            "id",
            "step_order",

            "approver_type",
            "approver_type_name",

            "approver_role",
            "approver_role_name",

            "specific_user",
            "specific_user_name",
            "specific_user_email",

            "department",
            "department_name",

            "routing_type",

            "is_active",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]


class ExpenseReportSerializer(serializers.ModelSerializer):

    receipts = ExpenseReceiptSerializer(
        many=True,
        read_only=True
    )

    approval_history = ApprovalHistorySerializer(
        many=True,
        read_only=True
    )

    employee_email = serializers.EmailField(
        source="employee.user.email",
        read_only=True
    )

    employee_name = serializers.SerializerMethodField()

    employee_profile_picture = serializers.SerializerMethodField()

    department_name = serializers.CharField(
        source="department.name",
        read_only=True
    )

    current_step = serializers.SerializerMethodField()

    workflow_timeline = serializers.SerializerMethodField()

    latest_rejection_reason = serializers.SerializerMethodField()

    approval_type = serializers.SerializerMethodField()

    approval_required = serializers.SerializerMethodField()

    view_only_for_workflow = serializers.SerializerMethodField()

    company_currency = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseReport

        fields = [
            "id",
            "company",
            "employee",
            "employee_name",
            "employee_profile_picture",
            "employee_email",
            "department",
            "department_name",
            "month",
            "status",
            "is_auto_approved",
            "auto_approved_at",
            "approval_type",
            "approval_required",
            "view_only_for_workflow",
            "total_amount",
            "company_currency",
            "submitted_at",
            "paid_at",
            "paid_notes",
            "current_workflow_step",
            "current_step",
            "workflow_timeline",
            "latest_rejection_reason",
            "workflow_completed",
            "receipts",
            "approval_history",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "company",
            "employee",
            "department",
            "status",
            "is_auto_approved",
            "auto_approved_at",
            "approval_type",
            "approval_required",
            "view_only_for_workflow",
            "total_amount",
            "company_currency",
            "submitted_at",
            "paid_at",
            "paid_notes",
            "current_workflow_step",
            "workflow_completed",
            "created_at",
            "updated_at",
        ]

    def get_company_currency(self, obj):
        try:
            finance_settings = obj.company.finance_settings
        except Exception:
            finance_settings = None

        if finance_settings and finance_settings.base_currency_id:
            return finance_settings.base_currency.code.upper()

        for receipt in obj.receipts.all():
            amount = receipt.company_amount or receipt.total_amount
            if (
                receipt.company_currency
                and amount is not None
                and amount > 0
            ):
                return receipt.company_currency.upper()

        return "USD"

    def get_employee_name(self, obj):
        full_name = (
            f"{obj.employee.user.first_name} "
            f"{obj.employee.user.last_name}"
        ).strip()

        return full_name or obj.employee.user.email

    def get_employee_profile_picture(self, obj):
        return profile_picture_url(
            obj.employee,
            self.context.get("request")
        )

    def get_approval_type(self, obj):
        if obj.is_auto_approved:
            return "SYSTEM_AUTO_APPROVED"

        if obj.status == ExpenseReport.STATUS_APPROVED:
            return "MANUAL_APPROVED"

        if obj.status == ExpenseReport.STATUS_REJECTED:
            return "REJECTED"

        if obj.status == ExpenseReport.STATUS_SUBMITTED:
            return "MANUAL_APPROVAL_REQUIRED"

        return "NOT_SUBMITTED"

    def get_approval_required(self, obj):
        return (
            obj.status == ExpenseReport.STATUS_SUBMITTED
            and not obj.workflow_completed
            and not obj.is_auto_approved
        )

    def get_view_only_for_workflow(self, obj):
        return (
            obj.is_auto_approved
            and obj.status in [
                ExpenseReport.STATUS_APPROVED,
                ExpenseReport.STATUS_PAID,
            ]
        )

    def get_current_step(self, obj):
        step = obj.current_workflow_step

        if not step:
            return None

        return {
            "id": str(step.id),
            "step_order": step.step_order,
            "approver_role": step.approver_role.name,
            "routing_type": step.routing_type,
            "department": (
                step.department.name
                if step.department else None
            ),
        }

    def get_latest_rejection_reason(self, obj):
        rejection = obj.approval_history.filter(
            action=ApprovalHistory.ACTION_STEP_REJECTED
        ).order_by("-created_at").first()

        if not rejection:
            return None

        return {
            "rejected_by": rejection.action_by.user.email,
            "role": (
                rejection.action_by.company_role.name
                if rejection.action_by.company_role
                else rejection.action_by.role
            ),
            "reason": rejection.comments,
            "rejected_at": rejection.created_at,
        }

    def get_workflow_timeline(self, obj):
        timeline = []

        timeline.append({
            "step_order": 0,
            "step_name": "Employee Submission",
            "status": (
                "COMPLETED"
                if obj.submitted_at
                else "DRAFT"
            ),
            "action_by": obj.employee.user.email,
            "action_role": "EMPLOYEE",
            "comments": None,
            "action_at": obj.submitted_at,
        })

        if obj.is_auto_approved:
            timeline.append({
                "step_order": 1,
                "step_name": "System Auto Approval",
                "status": "AUTO_APPROVED",
                "action_by": "SYSTEM",
                "action_role": "SYSTEM",
                "comments": (
                    "Approved automatically because all receipts satisfied "
                    "company policy."
                ),
                "action_at": obj.auto_approved_at,
            })

            workflow_steps = ApprovalWorkflowStep.objects.filter(
                workflow__company=obj.company,
                is_active=True
            ).select_related(
                "approver_role",
                "department"
            ).order_by(
                "step_order"
            )

            for step in workflow_steps:
                timeline.append({
                    "step_order": step.step_order + 1,
                    "step_name": step.approver_role.name,
                    "status": "VIEW_ONLY",
                    "action_by": None,
                    "action_role": step.approver_role.name,
                    "comments": "No action required. Auto approved by system.",
                    "action_at": None,
                })

            if obj.status == ExpenseReport.STATUS_PAID:
                paid_history = obj.approval_history.filter(
                    action=ApprovalHistory.ACTION_PAID
                ).first()

                timeline.append({
                    "step_order": 999,
                    "step_name": "Payment",
                    "status": "PAID",
                    "action_by": (
                        paid_history.action_by.user.email
                        if paid_history and paid_history.action_by
                        else None
                    ),
                    "action_role": "ACCOUNTS",
                    "comments": (
                        paid_history.comments
                        if paid_history
                        else obj.paid_notes
                    ),
                    "action_at": obj.paid_at,
                })

            else:
                timeline.append({
                    "step_order": 999,
                    "step_name": "Payment",
                    "status": "PENDING_PAYMENT",
                    "action_by": None,
                    "action_role": "ACCOUNTS",
                    "comments": None,
                    "action_at": None,
                })

            return timeline

        workflow = None

        if obj.current_workflow_step:
            workflow = obj.current_workflow_step.workflow
        else:
            first_step = ApprovalWorkflowStep.objects.filter(
                workflow__company=obj.company,
                is_active=True
            ).select_related(
                "workflow"
            ).order_by(
                "step_order"
            ).first()

            if first_step:
                workflow = first_step.workflow

        if not workflow:
            return timeline

        history_map = {}

        for history in obj.approval_history.all():
            if not history.action_by:
                continue

            role_name = (
                history.action_by.company_role.name
                if history.action_by.company_role
                else history.action_by.role
            )

            history_map[role_name] = history

        workflow_steps = workflow.steps.filter(
            is_active=True
        ).select_related(
            "approver_role",
            "department"
        ).order_by(
            "step_order"
        )

        workflow_stopped = obj.status == ExpenseReport.STATUS_REJECTED

        for step in workflow_steps:
            role_name = step.approver_role.name
            history = history_map.get(role_name)

            if history:
                if history.action == ApprovalHistory.ACTION_STEP_APPROVED:
                    status_value = "APPROVED"
                elif history.action == ApprovalHistory.ACTION_STEP_REJECTED:
                    status_value = "REJECTED"
                else:
                    status_value = history.action

                timeline.append({
                    "step_order": step.step_order,
                    "step_name": role_name,
                    "status": status_value,
                    "action_by": history.action_by.user.email,
                    "action_role": role_name,
                    "comments": history.comments,
                    "action_at": history.created_at,
                })

            else:
                if workflow_stopped:
                    status_value = "CANCELLED"
                elif (
                    obj.current_workflow_step
                    and obj.current_workflow_step.id == step.id
                ):
                    if is_payment_queue_role(step.approver_role):
                        status_value = "PENDING_PAYMENT"
                    else:
                        status_value = "PENDING"
                elif obj.workflow_completed or obj.status in [
                    ExpenseReport.STATUS_APPROVED,
                    ExpenseReport.STATUS_PAID,
                ]:
                    status_value = "APPROVED"
                else:
                    status_value = "WAITING"

                timeline.append({
                    "step_order": step.step_order,
                    "step_name": role_name,
                    "status": status_value,
                    "action_by": None,
                    "action_role": role_name,
                    "comments": None,
                    "action_at": None,
                })

        if obj.status == ExpenseReport.STATUS_PAID:
            paid_history = obj.approval_history.filter(
                action=ApprovalHistory.ACTION_PAID
            ).first()

            timeline.append({
                "step_order": 999,
                "step_name": "Payment",
                "status": "PAID",
                "action_by": (
                    paid_history.action_by.user.email
                    if paid_history and paid_history.action_by
                    else None
                ),
                "action_role": "ACCOUNTS",
                "comments": (
                    paid_history.comments
                    if paid_history
                    else obj.paid_notes
                ),
                "action_at": obj.paid_at,
            })

        elif obj.status == ExpenseReport.STATUS_APPROVED:
            timeline.append({
                "step_order": 999,
                "step_name": "Payment",
                "status": "PENDING_PAYMENT",
                "action_by": None,
                "action_role": "ACCOUNTS",
                "comments": None,
                "action_at": None,
            })

        return timeline
class ExpenseSubmissionSerializer(serializers.ModelSerializer):
    receipts = ExpenseReceiptSerializer(
        many=True,
        read_only=True
    )

    employee_email = serializers.EmailField(
        source="employee.user.email",
        read_only=True
    )

    class Meta:
        model = ExpenseSubmission
        fields = [
            "id",
            "report",
            "company",
            "employee",
            "employee_email",
            "source",
            "email_subject",
            "receipts",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "report",
            "company",
            "employee",
            "created_at",
        ]


class ReceiptUploadSerializer(serializers.Serializer):
    receipt_file = serializers.FileField()


class ApprovalWorkflowSerializer(serializers.ModelSerializer):

    steps = ApprovalWorkflowStepSerializer(
        many=True,
        read_only=True
    )

    start_role_name = serializers.CharField(
        source="start_role.name",
        read_only=True
    )

    class Meta:
        model = ApprovalWorkflow

        fields = [
            "id",
            "company",
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
            "company",
            "created_at",
            "updated_at",
        ]

from .models import DuplicateReceiptLog


class DuplicateReceiptLogSerializer(serializers.ModelSerializer):

    original_vendor = serializers.CharField(
        source="original_receipt.vendor_name",
        read_only=True
    )

    duplicate_vendor = serializers.CharField(
        source="duplicate_receipt.vendor_name",
        read_only=True
    )

    class Meta:
        model = DuplicateReceiptLog
        fields = [
            "id",
            "original_receipt",
            "duplicate_receipt",
            "original_vendor",
            "duplicate_vendor",
            "created_at",
        ]        


from .models import DuplicateReceiptLog

class DuplicateReceiptLogSerializer(serializers.ModelSerializer):
    original_employee_email = serializers.EmailField(
        source="original_receipt.employee.user.email",
        read_only=True
    )
    duplicate_employee_email = serializers.EmailField(
        source="duplicate_receipt.employee.user.email",
        read_only=True
    )
    original_vendor = serializers.CharField(
        source="original_receipt.vendor_name",
        read_only=True
    )
    duplicate_vendor = serializers.CharField(
        source="duplicate_receipt.vendor_name",
        read_only=True
    )

    class Meta:
        model = DuplicateReceiptLog
        fields = [
            "id",
            "original_receipt",
            "duplicate_receipt",
            "duplicate_type",
            "original_employee_email",
            "duplicate_employee_email",
            "original_vendor",
            "duplicate_vendor",
            "created_at",
        ]