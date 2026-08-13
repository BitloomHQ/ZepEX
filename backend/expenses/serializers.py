from rest_framework import serializers

from .models import (
    ExpenseReport,
    ExpenseSubmission,
    ExpenseReceipt,
    ExpenseLineItem,
    ApprovalHistory,
    ApprovalWorkflow,
    ApprovalWorkflowStep,
    Notification
)
from .report_utils import is_payment_queue_role
from tenants.media_utils import profile_picture_url



class ExpenseLineItemSerializer(serializers.ModelSerializer):

    class Meta:
        model = ExpenseLineItem
        fields = [
            "id",
            "receipt",
            "description",
            "category",
            "subcategory",
            "vendor",
            "amount",
            "bill_date",
            "is_violating",
            "violation_reason",

            # Approval fields
            "is_removed",
            "removed_by",
            "removed_at",
            "removal_reason",

            "created_at",
        ]
        read_only_fields = [
            "id",
            "receipt",
            "is_removed",
            "removed_by",
            "removed_at",
            "removal_reason",
            "created_at",
        ]


class ExpenseReceiptSerializer(serializers.ModelSerializer):

    # -----------------------------------------
    # Expense line items
    # -----------------------------------------

    line_items = ExpenseLineItemSerializer(
        many=True,
        read_only=True
    )

    # Frontend-friendly alias
    claim_lines = ExpenseLineItemSerializer(
        source="line_items",
        many=True,
        read_only=True
    )

    # -----------------------------------------
    # Employee
    # -----------------------------------------

    employee_email = serializers.EmailField(
        source="employee.user.email",
        read_only=True
    )

    # -----------------------------------------
    # Department
    # -----------------------------------------

    department_name = serializers.CharField(
        source="department.name",
        read_only=True
    )

    class Meta:
        model = ExpenseReceipt

        fields = [
            # ---------------------------------
            # IDs / relationships
            # ---------------------------------
            "id",
            "report",
            "submission",
            "company",

            # ---------------------------------
            # Employee
            # ---------------------------------
            "employee",
            "employee_email",

            # ---------------------------------
            # Department
            # ---------------------------------
            "department",
            "department_name",

            # ---------------------------------
            # Receipt
            # ---------------------------------
            "receipt_file",
            "vendor_name",
            "invoice_date",

            # ---------------------------------
            # Amount
            # ---------------------------------
            "total_amount",
            "currency",

            # ---------------------------------
            # Original receipt currency
            # ---------------------------------
            "original_amount",
            "original_currency",

            # ---------------------------------
            # Company reimbursement currency
            # ---------------------------------
            "company_amount",
            "company_currency",

            # ---------------------------------
            # Exchange information
            # ---------------------------------
            "exchange_rate",
            "exchange_rate_date",
            "exchange_rate_provider",

            # ---------------------------------
            # Receipt status
            # ---------------------------------
            "status",

            # ---------------------------------
            # AI
            # ---------------------------------
            "ai_status",
            "ai_error_message",
            "ai_retry_count",

            # ---------------------------------
            # Policy
            # ---------------------------------
            "policy_violation_reason",
            "has_duplicate_violation",
            "has_old_bill_violation",
            "has_amount_violation",
            "has_any_violation",

            # ---------------------------------
            # Line items
            # ---------------------------------
            "line_items",

            # Frontend alias
            "claim_lines",

            # ---------------------------------
            # Timestamps
            # ---------------------------------
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            # ---------------------------------
            # IDs / relationships
            # ---------------------------------
            "id",
            "report",
            "submission",
            "company",

            # ---------------------------------
            # Employee
            # ---------------------------------
            "employee",
            "department",

            # ---------------------------------
            # Receipt information
            # ---------------------------------
            "vendor_name",
            "invoice_date",

            # ---------------------------------
            # Amount
            # ---------------------------------
            "total_amount",
            "currency",

            # ---------------------------------
            # Original currency
            # ---------------------------------
            "original_amount",
            "original_currency",

            # ---------------------------------
            # Company currency
            # ---------------------------------
            "company_amount",
            "company_currency",

            # ---------------------------------
            # Exchange information
            # ---------------------------------
            "exchange_rate",
            "exchange_rate_date",
            "exchange_rate_provider",

            # ---------------------------------
            # Status
            # ---------------------------------
            "status",

            # ---------------------------------
            # AI
            # ---------------------------------
            "ai_status",
            "ai_error_message",
            "ai_retry_count",

            # ---------------------------------
            # Policy
            # ---------------------------------
            "policy_violation_reason",
            "has_duplicate_violation",
            "has_old_bill_violation",
            "has_amount_violation",
            "has_any_violation",

            # ---------------------------------
            # Line items
            # ---------------------------------
            "line_items",
            "claim_lines",

            # ---------------------------------
            # Timestamps
            # ---------------------------------
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

    # ==========================================================
    # RECEIPTS
    # ==========================================================

    receipts = ExpenseReceiptSerializer(
        many=True,
        read_only=True
    )

    # ==========================================================
    # APPROVAL HISTORY
    # ==========================================================

    approval_history = ApprovalHistorySerializer(
        many=True,
        read_only=True
    )

    # ==========================================================
    # EMPLOYEE
    # ==========================================================

    employee_email = serializers.EmailField(
        source="employee.user.email",
        read_only=True
    )

    employee_name = serializers.SerializerMethodField()

    employee_profile_picture = serializers.SerializerMethodField()

    # ==========================================================
    # DEPARTMENT
    # ==========================================================

    department_name = serializers.CharField(
        source="department.name",
        read_only=True
    )

    # ==========================================================
    # WORKFLOW
    # ==========================================================

    current_step = serializers.SerializerMethodField()

    workflow_timeline = serializers.SerializerMethodField()

    latest_rejection_reason = serializers.SerializerMethodField()

    approval_type = serializers.SerializerMethodField()

    approval_required = serializers.SerializerMethodField()

    view_only_for_workflow = serializers.SerializerMethodField()

    # ==========================================================
    # CURRENCY
    # ==========================================================

    company_currency = serializers.SerializerMethodField()

    # ==========================================================
    # META
    # ==========================================================

    class Meta:
        model = ExpenseReport

        fields = [
            # --------------------------------------------------
            # Basic
            # --------------------------------------------------

            "id",
            "company",

            # --------------------------------------------------
            # Employee
            # --------------------------------------------------

            "employee",
            "employee_name",
            "employee_profile_picture",
            "employee_email",

            # --------------------------------------------------
            # Department
            # --------------------------------------------------

            "department",
            "department_name",

            # --------------------------------------------------
            # Report
            # --------------------------------------------------

            "month",
            "status",

            # --------------------------------------------------
            # Auto approval
            # --------------------------------------------------

            "is_auto_approved",
            "auto_approved_at",

            # --------------------------------------------------
            # Approval information
            # --------------------------------------------------

            "approval_type",
            "approval_required",
            "view_only_for_workflow",

            # --------------------------------------------------
            # Amount
            # --------------------------------------------------

            "total_amount",
            "company_currency",

            # --------------------------------------------------
            # Dates
            # --------------------------------------------------

            "submitted_at",
            "paid_at",
            "paid_notes",

            # --------------------------------------------------
            # Workflow
            # --------------------------------------------------

            "current_workflow_step",
            "current_step",
            "workflow_timeline",
            "latest_rejection_reason",
            "workflow_completed",

            # --------------------------------------------------
            # Receipts
            # --------------------------------------------------

            "receipts",

            # --------------------------------------------------
            # Approval history
            # --------------------------------------------------

            "approval_history",

            # --------------------------------------------------
            # Timestamps
            # --------------------------------------------------

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            # --------------------------------------------------
            # Basic
            # --------------------------------------------------

            "id",
            "company",

            # --------------------------------------------------
            # Employee
            # --------------------------------------------------

            "employee",

            # --------------------------------------------------
            # Department
            # --------------------------------------------------

            "department",

            # --------------------------------------------------
            # Report status
            # --------------------------------------------------

            "status",

            # --------------------------------------------------
            # Auto approval
            # --------------------------------------------------

            "is_auto_approved",
            "auto_approved_at",

            # --------------------------------------------------
            # Approval
            # --------------------------------------------------

            "approval_type",
            "approval_required",
            "view_only_for_workflow",

            # --------------------------------------------------
            # Amount
            # --------------------------------------------------

            "total_amount",
            "company_currency",

            # --------------------------------------------------
            # Dates
            # --------------------------------------------------

            "submitted_at",
            "paid_at",
            "paid_notes",

            # --------------------------------------------------
            # Workflow
            # --------------------------------------------------

            "current_workflow_step",
            "workflow_completed",

            # --------------------------------------------------
            # Timestamps
            # --------------------------------------------------

            "created_at",
            "updated_at",
        ]

    # ==========================================================
    # COMPANY CURRENCY
    # ==========================================================

    def get_company_currency(self, obj):

        try:
            finance_settings = obj.company.finance_settings
        except Exception:
            finance_settings = None

        if (
            finance_settings
            and finance_settings.base_currency_id
        ):
            return finance_settings.base_currency.code.upper()

        for receipt in obj.receipts.all():

            amount = (
                receipt.company_amount
                or receipt.total_amount
            )

            if (
                receipt.company_currency
                and amount is not None
                and amount > 0
            ):
                return receipt.company_currency.upper()

        return "USD"

    # ==========================================================
    # EMPLOYEE NAME
    # ==========================================================

    def get_employee_name(self, obj):

        full_name = (
            f"{obj.employee.user.first_name} "
            f"{obj.employee.user.last_name}"
        ).strip()

        return (
            full_name
            or obj.employee.user.email
        )

    # ==========================================================
    # EMPLOYEE PROFILE PICTURE
    # ==========================================================

    def get_employee_profile_picture(self, obj):

        return profile_picture_url(
            obj.employee,
            self.context.get("request")
        )

    # ==========================================================
    # APPROVAL TYPE
    # ==========================================================

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

    # ==========================================================
    # APPROVAL REQUIRED
    # ==========================================================

    def get_approval_required(self, obj):

        return (
            obj.status == ExpenseReport.STATUS_SUBMITTED
            and not obj.workflow_completed
            and not obj.is_auto_approved
        )

    # ==========================================================
    # VIEW ONLY
    # ==========================================================

    def get_view_only_for_workflow(self, obj):

        return (
            obj.is_auto_approved
            and obj.status in [
                ExpenseReport.STATUS_APPROVED,
                ExpenseReport.STATUS_PAID,
            ]
        )

    # ==========================================================
    # CURRENT WORKFLOW STEP
    # ==========================================================

    def get_current_step(self, obj):

        step = obj.current_workflow_step

        if not step:
            return None

        return {
            "id": str(step.id),

            "step_order": step.step_order,

            "approver_type": step.approver_type,

            "approver_role": (
                step.approver_role.name
                if step.approver_role
                else None
            ),

            "routing_type": step.routing_type,

            "department": (
                step.department.name
                if step.department
                else None
            ),

            "specific_user": (
                step.specific_user.user.email
                if step.specific_user
                else None
            ),
        }

    # ==========================================================
    # LATEST REJECTION
    # ==========================================================

    def get_latest_rejection_reason(self, obj):

        rejection = (
            obj.approval_history
            .filter(
                action=ApprovalHistory.ACTION_STEP_REJECTED
            )
            .order_by("-created_at")
            .first()
        )

        if not rejection:
            return None

        return {
            "rejected_by": (
                rejection.action_by.user.email
                if rejection.action_by
                else None
            ),

            "role": (
                rejection.action_by.company_role.name
                if (
                    rejection.action_by
                    and rejection.action_by.company_role
                )
                else (
                    rejection.action_by.role
                    if rejection.action_by
                    else None
                )
            ),

            "reason": rejection.comments,

            "rejected_at": rejection.created_at,
        }

    # ==========================================================
    # WORKFLOW TIMELINE
    # ==========================================================

    def get_workflow_timeline(self, obj):

        timeline = []

        # ------------------------------------------------------
        # Employee submission
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # Auto approved
        # ------------------------------------------------------

        if obj.is_auto_approved:

            timeline.append({
                "step_order": 1,
                "step_name": "System Auto Approval",

                "status": "AUTO_APPROVED",

                "action_by": "SYSTEM",

                "action_role": "SYSTEM",

                "comments": (
                    "Approved automatically because all "
                    "receipts satisfied company policy."
                ),

                "action_at": obj.auto_approved_at,
            })

            workflow_steps = (
                ApprovalWorkflowStep.objects
                .filter(
                    workflow__company=obj.company,
                    is_active=True
                )
                .select_related(
                    "approver_role",
                    "department"
                )
                .order_by("step_order")
            )

            for step in workflow_steps:

                timeline.append({
                    "step_order": step.step_order + 1,

                    "step_name": (
                        step.approver_role.name
                        if step.approver_role
                        else step.approver_type
                    ),

                    "status": "VIEW_ONLY",

                    "action_by": None,

                    "action_role": (
                        step.approver_role.name
                        if step.approver_role
                        else step.approver_type
                    ),

                    "comments": (
                        "No action required. "
                        "Auto approved by system."
                    ),

                    "action_at": None,
                })

            # --------------------------------------------------
            # Payment
            # --------------------------------------------------

            if obj.status == ExpenseReport.STATUS_PAID:

                paid_history = (
                    obj.approval_history
                    .filter(
                        action=ApprovalHistory.ACTION_PAID
                    )
                    .first()
                )

                timeline.append({
                    "step_order": 999,

                    "step_name": "Payment",

                    "status": "PAID",

                    "action_by": (
                        paid_history.action_by.user.email
                        if (
                            paid_history
                            and paid_history.action_by
                        )
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

        # ======================================================
        # MANUAL WORKFLOW
        # ======================================================

        workflow = None

        if obj.current_workflow_step:

            workflow = (
                obj.current_workflow_step.workflow
            )

        else:

            first_step = (
                ApprovalWorkflowStep.objects
                .filter(
                    workflow__company=obj.company,
                    is_active=True
                )
                .select_related("workflow")
                .order_by("step_order")
                .first()
            )

            if first_step:
                workflow = first_step.workflow

        if not workflow:
            return timeline

        # ------------------------------------------------------
        # History
        # ------------------------------------------------------

        # ------------------------------------------------------
        # Approval history
        # ------------------------------------------------------

        approval_histories = (
            obj.approval_history
            .select_related(
                "action_by",
                "action_by__user",
                "action_by__company_role",
                "line_item",
                "receipt",
            )
            .order_by("created_at")
        )

        history_map = {}

        line_item_actions = []

        for history in approval_histories:

            # ----------------------------------------------
            # Line item actions
            # ----------------------------------------------

            if history.action in [
                ApprovalHistory.ACTION_LINE_ITEM_REMOVED,
                ApprovalHistory.ACTION_LINE_ITEM_RESTORED,
                ApprovalHistory.ACTION_LINE_ITEM_UPDATED,
            ]:

                line_item_actions.append({
                    "action": history.action,
                    "action_by": (
                        history.action_by.user.email
                        if history.action_by
                        else None
                    ),
                    "action_role": (
                        history.action_by.company_role.name
                        if (
                            history.action_by
                            and history.action_by.company_role
                        )
                        else (
                            history.action_by.role
                            if history.action_by
                            else None
                        )
                    ),
                    "comments": history.comments,
                    "action_at": history.created_at,

                    "line_item_id": (
                        str(history.line_item_id)
                        if history.line_item_id
                        else None
                    ),

                    "receipt_id": (
                        str(history.receipt_id)
                        if history.receipt_id
                        else None
                    ),

                    "description": (
                        history.line_item.description
                        if history.line_item
                        else None
                    ),

                    "category": (
                        history.line_item.category
                        if history.line_item
                        else None
                    ),

                    "subcategory": (
                        history.line_item.subcategory
                        if history.line_item
                        else None
                    ),

                    "amount": (
                        str(history.line_item.amount)
                        if history.line_item
                        else None
                    ),
                })

                continue

            # ----------------------------------------------
            # Normal workflow actions
            # ----------------------------------------------

            if not history.action_by:
                continue

            role_name = (
                history.action_by.company_role.name
                if history.action_by.company_role
                else history.action_by.role
            )

            history_map[role_name] = history

        # ------------------------------------------------------
        # Workflow steps
        # ------------------------------------------------------

        workflow_steps = (
            workflow.steps
            .filter(is_active=True)
            .select_related(
                "approver_role",
                "department"
            )
            .order_by("step_order")
        )

        workflow_stopped = (
            obj.status == ExpenseReport.STATUS_REJECTED
        )

        for step in workflow_steps:

            role_name = (
                step.approver_role.name
                if step.approver_role
                else step.approver_type
            )

            history = history_map.get(role_name)

            if history:

                if (
                    history.action
                    == ApprovalHistory.ACTION_STEP_APPROVED
                ):
                    status_value = "APPROVED"

                elif (
                    history.action
                    == ApprovalHistory.ACTION_STEP_REJECTED
                ):
                    status_value = "REJECTED"

                else:
                    status_value = history.action

                timeline.append({
                    "step_order": step.step_order,

                    "step_name": role_name,

                    "status": status_value,

                    "action_by": (
                        history.action_by.user.email
                        if history.action_by
                        else None
                    ),

                    "action_role": role_name,

                    "comments": history.comments,

                    "action_at": history.created_at,
                })

            else:

                if workflow_stopped:

                    status_value = "CANCELLED"

                elif (
                    obj.current_workflow_step
                    and obj.current_workflow_step.id
                    == step.id
                ):

                    if is_payment_queue_role(
                        step.approver_role
                    ):
                        status_value = "PENDING_PAYMENT"

                    else:
                        status_value = "PENDING"

                elif (
                    obj.workflow_completed
                    or obj.status in [
                        ExpenseReport.STATUS_APPROVED,
                        ExpenseReport.STATUS_PAID,
                    ]
                ):

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

        # ======================================================
        # LINE ITEM ACTIONS
        # ======================================================

        for action in line_item_actions:

            if action["action"] == ApprovalHistory.ACTION_LINE_ITEM_REMOVED:
                status_value = "LINE_ITEM_REMOVED"
                step_name = "Expense Item Removed"

            elif action["action"] == ApprovalHistory.ACTION_LINE_ITEM_RESTORED:
                status_value = "LINE_ITEM_RESTORED"
                step_name = "Expense Item Restored"

            else:
                status_value = "LINE_ITEM_UPDATED"
                step_name = "Expense Item Updated"

            timeline.append({
                "step_order": 500,

                "step_name": step_name,

                "status": status_value,

                "action_by": action["action_by"],

                "action_role": action["action_role"],

                "comments": action["comments"],

                "action_at": action["action_at"],

                "line_item": {
                    "id": action["line_item_id"],
                    "receipt_id": action["receipt_id"],
                    "description": action["description"],
                    "category": action["category"],
                    "subcategory": action["subcategory"],
                    "amount": action["amount"],
                },
            })

        # ======================================================
        # PAYMENT
        # ======================================================

        if obj.status == ExpenseReport.STATUS_PAID:

            paid_history = (
                obj.approval_history
                .filter(
                    action=ApprovalHistory.ACTION_PAID
                )
                .first()
            )

            timeline.append({
                "step_order": 999,

                "step_name": "Payment",

                "status": "PAID",

                "action_by": (
                    paid_history.action_by.user.email
                    if (
                        paid_history
                        and paid_history.action_by
                    )
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
from tenants.models import CompanyPolicy
class CompanyPolicySerializer(serializers.ModelSerializer):

    class Meta:
        model = CompanyPolicy

        fields = [
            "id",
            "company",
            "old_bill_limit_days",
            "auto_approve_if_no_violation",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "company",
            "updated_at",
        ]

    def validate_old_bill_limit_days(self, value):

        if value < 1:
            raise serializers.ValidationError(
                "Old bill limit must be at least 1 day."
            )

        if value > 3650:
            raise serializers.ValidationError(
                "Old bill limit cannot exceed 3650 days."
            )

        return value


class NotificationSerializer(serializers.ModelSerializer):

    recipient_email = serializers.EmailField(
        source="recipient.user.email",
        read_only=True,
    )

    notification_type_name = serializers.CharField(
        source="get_notification_type_display",
        read_only=True,
    )

    report_id = serializers.SerializerMethodField()
    receipt_id = serializers.SerializerMethodField()

    class Meta:
        model = Notification

        fields = [
            "id",

            # Notification information
            "notification_type",
            "notification_type_name",
            "title",
            "message",

            # Recipient
            "recipient",
            "recipient_email",

            # Company
            "company",

            # Related objects
            "report_id",
            "receipt_id",

            # Read status
            "is_read",
            "read_at",

            # Timestamps
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "recipient",
            "recipient_email",
            "company",
            "report_id",
            "receipt_id",
            "notification_type",
            "notification_type_name",
            "title",
            "message",
            "is_read",
            "read_at",
            "created_at",
            "updated_at",
        ]

    def get_report_id(self, obj):
        return (
            str(obj.report.id)
            if obj.report
            else None
        )

    def get_receipt_id(self, obj):
        return (
            str(obj.receipt.id)
            if obj.receipt
            else None
        )