from django.shortcuts import render

# Create your views here.
from datetime import date

from django.conf import settings

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from platform_access.permissions import has_platform_permission
from expenses.models import (
    ExpenseReport,
    ApprovalHistory,
    ApprovalWorkflow,
)
from expenses.serializers import ExpenseReportSerializer, ExpenseReceiptSerializer
from expenses.report_utils import get_pending_approval_reports_for

from tenants.models import Department, UserProfile, Company
from django.db.models import Sum
from platform_management.models import CompanyRegistrationRequest

from tenants.models import (
    Department,
    UserProfile,
    Company,
    CompanyPolicy,  
)
from django.db.models import Sum
from expenses.models import ExpenseLineItem
from django.conf import settings
from platform_access.decorators import platform_permission_required

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def employee_dashboard(request):

    profile = request.user.profile

    if not profile.company_role:
        return Response(
            {"error": "Your company role is not assigned."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not profile.company_role.can_submit_expense:
        return Response(
            {"error": "Your role is not allowed to access this dashboard."},
            status=status.HTTP_403_FORBIDDEN
        )

    current_month = date.today().replace(day=1)

    current_report = ExpenseReport.objects.filter(
        company=profile.company,
        employee=profile,
        month=current_month
    ).select_related(
        "department",
        "current_approver",
        "current_approver__user",
        "current_workflow_step",
        "current_workflow_step__approver_role",
        "current_workflow_step__specific_user",
        "current_workflow_step__specific_user__user",
        "current_workflow_step__department",
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history",
        "approval_history__action_by",
        "approval_history__action_by__user",
    ).first()

    all_reports = ExpenseReport.objects.filter(
        company=profile.company,
        employee=profile
    )

    submitted_reports = all_reports.exclude(
        status=ExpenseReport.STATUS_DRAFT
    ).select_related(
        "department",
        "current_approver",
        "current_approver__user",
        "current_workflow_step",
        "current_workflow_step__approver_role",
        "current_workflow_step__specific_user",
        "current_workflow_step__specific_user__user",
        "current_workflow_step__department",
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history",
        "approval_history__action_by",
        "approval_history__action_by__user",
    ).order_by("-month")

    total_reports = all_reports.count()

    draft_reports = all_reports.filter(
        status=ExpenseReport.STATUS_DRAFT
    ).count()

    pending_reports = all_reports.filter(
        status=ExpenseReport.STATUS_SUBMITTED
    ).count()

    approved_reports = all_reports.filter(
        status=ExpenseReport.STATUS_APPROVED
    ).count()

    rejected_reports = all_reports.filter(
        status=ExpenseReport.STATUS_REJECTED
    ).count()

    paid_reports = all_reports.filter(
        status=ExpenseReport.STATUS_PAID
    ).count()

    data = {
        "user": {
            "name": request.user.get_full_name(),
            "email": request.user.email,
            "system_role": profile.role,
            "company_role": profile.company_role.name,
            "company": profile.company.name,
            "department": (
                profile.department.name
                if profile.department else None
            ),
            "permissions": {
                "can_upload_receipt": profile.company_role.can_upload_receipt,
                "can_submit_expense": profile.company_role.can_submit_expense,
                "can_approve_expense": profile.company_role.can_approve_expense,
                "can_mark_paid": profile.company_role.can_mark_paid,
            }
        },

        "metrics": {
            "total_reports": total_reports,
            "draft_reports": draft_reports,
            "pending_reports": pending_reports,
            "approved_reports": approved_reports,
            "rejected_reports": rejected_reports,
            "paid_reports": paid_reports,
        },

        "current_month_report": None,

        "submitted_reports": ExpenseReportSerializer(
            submitted_reports,
            many=True
        ).data
    }

    if current_report:

        no_violation_receipts = current_report.receipts.filter(
            has_any_violation=False
        )

        violation_receipts = current_report.receipts.filter(
            has_any_violation=True
        )

        current_approver = current_report.current_approver
        current_step = current_report.current_workflow_step

        data["current_month_report"] = {
            "report": ExpenseReportSerializer(current_report).data,

            "workflow_status": {
                "workflow_completed": current_report.workflow_completed,
                "current_approver": (
                    {
                        "id": str(current_approver.id),
                        "name": current_approver.user.get_full_name(),
                        "email": current_approver.user.email,
                    }
                    if current_approver else None
                ),
                "current_step": (
                    {
                        "id": str(current_step.id),
                        "step_order": current_step.step_order,
                        "approver_type": current_step.approver_type,
                        "approver_type_display": current_step.get_approver_type_display(),
                        "approver_role": (
                            current_step.approver_role.name
                            if current_step.approver_role else None
                        ),
                        "specific_user": (
                            {
                                "id": str(current_step.specific_user.id),
                                "name": current_step.specific_user.user.get_full_name(),
                                "email": current_step.specific_user.user.email,
                            }
                            if current_step.specific_user else None
                        ),
                        "routing_type": current_step.routing_type,
                        "department": (
                            current_step.department.name
                            if current_step.department else None
                        ),
                    }
                    if current_step else None
                ),
            },

            "summary": {
                "total_receipts": current_report.receipts.count(),
                "no_violation_receipts": no_violation_receipts.count(),
                "violation_receipts": violation_receipts.count(),
                "total_amount": str(current_report.total_amount),
            },

            "no_violation_receipts": ExpenseReceiptSerializer(
                no_violation_receipts,
                many=True
            ).data,

            "violation_receipts": ExpenseReceiptSerializer(
                violation_receipts,
                many=True
            ).data,
        }

    return Response(data)

from django.db.models import Q, Sum
from expenses.models import ApprovalWorkflowStep

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def approver_dashboard(request):

    profile = request.user.profile

    if not profile.company_role:
        return Response(
            {"error": "Your company role is not assigned."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not profile.company_role.can_approve_expense:
        return Response(
            {"error": "Your role is not allowed to approve expenses."},
            status=status.HTTP_403_FORBIDDEN
        )

    pending_reports = ExpenseReport.objects.filter(
        company=profile.company,
        status=ExpenseReport.STATUS_SUBMITTED,
        workflow_completed=False,
        current_approver=profile,
    ).select_related(
        "employee",
        "employee__user",
        "department",
        "current_approver",
        "current_approver__user",
        "current_workflow_step",
        "current_workflow_step__workflow",
        "current_workflow_step__approver_role",
        "current_workflow_step__specific_user",
        "current_workflow_step__specific_user__user",
        "current_workflow_step__department",
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history",
        "approval_history__action_by",
        "approval_history__action_by__user",
    ).order_by("-submitted_at", "-updated_at")

    approved_reports = ExpenseReport.objects.filter(
        company=profile.company,
        approval_history__action=ApprovalHistory.ACTION_STEP_APPROVED,
        approval_history__action_by=profile,
    ).select_related(
        "employee",
        "employee__user",
        "department",
        "current_approver",
        "current_approver__user",
        "current_workflow_step",
        "current_workflow_step__approver_role",
        "current_workflow_step__specific_user",
        "current_workflow_step__specific_user__user",
        "current_workflow_step__department",
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history",
    ).distinct().order_by("-updated_at")

    rejected_reports = ExpenseReport.objects.filter(
        company=profile.company,
        approval_history__action=ApprovalHistory.ACTION_STEP_REJECTED,
        approval_history__action_by=profile,
    ).select_related(
        "employee",
        "employee__user",
        "department",
        "current_approver",
        "current_approver__user",
        "current_workflow_step",
        "current_workflow_step__approver_role",
        "current_workflow_step__specific_user",
        "current_workflow_step__specific_user__user",
        "current_workflow_step__department",
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history",
    ).distinct().order_by("-updated_at")

    violation_reports = pending_reports.filter(
        receipts__has_any_violation=True
    ).distinct()

    pending_amount = pending_reports.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    approved_amount = approved_reports.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    rejected_amount = rejected_reports.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    recent_pending_reports = pending_reports[:10]

    return Response({
        "approver": {
            "name": request.user.get_full_name(),
            "email": request.user.email,
            "company": profile.company.name,
            "company_role": profile.company_role.name,
            "department": (
                profile.department.name
                if profile.department else None
            ),
            "permissions": {
                "can_approve_expense": profile.company_role.can_approve_expense,
                "can_mark_paid": profile.company_role.can_mark_paid,
            }
        },

        "metrics": {
            "pending_reports": pending_reports.count(),
            "approved_reports": approved_reports.count(),
            "rejected_reports": rejected_reports.count(),
            "violation_reports": violation_reports.count(),
            "pending_amount": str(pending_amount),
            "approved_amount": str(approved_amount),
            "rejected_amount": str(rejected_amount),
        },

        "approval_routing": {
            "dynamic_workflow_enabled": True,
            "matching_rule": "current_approver",
            "current_approver_id": str(profile.id),
            "current_approver_email": profile.user.email,
        },

        "recent_pending_reports": ExpenseReportSerializer(
            recent_pending_reports,
            many=True
        ).data,

        "pending_reports": ExpenseReportSerializer(
            pending_reports,
            many=True
        ).data,

        "approved_reports": ExpenseReportSerializer(
            approved_reports[:10],
            many=True
        ).data,

        "rejected_reports": ExpenseReportSerializer(
            rejected_reports[:10],
            many=True
        ).data,
    })
from expenses.report_utils import get_reports_awaiting_payment
from expenses.models import ExpenseReport, ApprovalWorkflow
from tenants.models import CompanyRole
from tenants.role_schema import defer_missing_company_role_fields

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_dashboard(request):

    profile = request.user.profile

    if not profile.company_role:
        return Response(
            {
                "error": "Your company role is not assigned."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if not profile.company_role.can_mark_paid:
        return Response(
            {
                "error": "Your role is not allowed to access payment dashboard."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    reports = ExpenseReport.objects.filter(
        company=profile.company
    )

    payment_queue_reports = get_reports_awaiting_payment(
        profile.company
    )

    approved_reports = payment_queue_reports.filter(
        status=ExpenseReport.STATUS_APPROVED
    )

    rejected_reports_for_accounts = payment_queue_reports.filter(
        status=ExpenseReport.STATUS_REJECTED
    )

    auto_approved_reports = approved_reports.filter(
        is_auto_approved=True
    )

    manual_approved_reports = approved_reports.filter(
        is_auto_approved=False
    )

    paid_reports = reports.filter(
        status=ExpenseReport.STATUS_PAID
    ).select_related(
        "employee",
        "employee__user",
        "department",
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history",
        "approval_history__action_by",
        "approval_history__action_by__user",
    ).order_by("-paid_at")

    all_rejected_reports = reports.filter(
        status=ExpenseReport.STATUS_REJECTED
    ).select_related(
        "employee",
        "employee__user",
        "department",
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history",
        "approval_history__action_by",
        "approval_history__action_by__user",
    ).order_by("-updated_at")

    approved_amount = approved_reports.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    rejected_queue_amount = rejected_reports_for_accounts.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    auto_approved_amount = auto_approved_reports.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    manual_approved_amount = manual_approved_reports.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    paid_amount = paid_reports.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    rejected_amount = all_rejected_reports.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    total_reports = reports.count()

    payment_completion_rate = 0

    if total_reports > 0:
        payment_completion_rate = round(
            (paid_reports.count() / total_reports) * 100,
            2
        )

    department_payment_summary = paid_reports.values(
        "department__name"
    ).annotate(
        total_paid=Sum("total_amount")
    ).order_by("-total_paid")

    return Response({
        "payment_user": {
            "name": request.user.get_full_name(),
            "email": request.user.email,
            "company": profile.company.name,
            "company_role": profile.company_role.name,
            "permissions": {
                "can_mark_paid": profile.company_role.can_mark_paid,
                "can_approve_expense": profile.company_role.can_approve_expense,
            }
        },

        "metrics": {
            "payment_queue_reports": payment_queue_reports.count(),
            "approved_reports_waiting_payment": approved_reports.count(),
            "rejected_reports_waiting_accounts_action": rejected_reports_for_accounts.count(),

            "auto_approved_reports_waiting_payment": auto_approved_reports.count(),
            "manual_approved_reports_waiting_payment": manual_approved_reports.count(),

            "paid_reports": paid_reports.count(),
            "total_rejected_reports": all_rejected_reports.count(),

            "approved_amount": str(approved_amount),
            "rejected_queue_amount": str(rejected_queue_amount),
            "auto_approved_amount": str(auto_approved_amount),
            "manual_approved_amount": str(manual_approved_amount),

            "paid_amount": str(paid_amount),
            "total_rejected_amount": str(rejected_amount),

            "payment_completion_rate": payment_completion_rate,
        },

        "payment_queue": {
            "ready_for_accounts_action": payment_queue_reports.count(),
            "approved_waiting_payment": approved_reports.count(),
            "rejected_waiting_accounts_action": rejected_reports_for_accounts.count(),
            "allowed_actions": [
                "MARK_PAID"
            ],
            "includes_statuses": [
                ExpenseReport.STATUS_APPROVED,
                ExpenseReport.STATUS_REJECTED,
            ],
        },

        "department_payment_summary": [
            {
                "department": item["department__name"] or "No Department",
                "total_paid": str(item["total_paid"] or 0),
            }
            for item in department_payment_summary
        ],

        "recent_payment_queue_reports": ExpenseReportSerializer(
            payment_queue_reports[:10],
            many=True
        ).data,

        "recent_approved_reports": ExpenseReportSerializer(
            approved_reports[:10],
            many=True
        ).data,

        "recent_rejected_reports_for_accounts": ExpenseReportSerializer(
            rejected_reports_for_accounts[:10],
            many=True
        ).data,

        "recent_auto_approved_reports": ExpenseReportSerializer(
            auto_approved_reports[:10],
            many=True
        ).data,

        "recent_manual_approved_reports": ExpenseReportSerializer(
            manual_approved_reports[:10],
            many=True
        ).data,

        "recent_paid_reports": ExpenseReportSerializer(
            paid_reports[:10],
            many=True
        ).data,

        "payment_queue_reports": ExpenseReportSerializer(
            payment_queue_reports,
            many=True
        ).data,

        "approved_reports": ExpenseReportSerializer(
            approved_reports,
            many=True
        ).data,

        "rejected_reports_for_accounts": ExpenseReportSerializer(
            rejected_reports_for_accounts,
            many=True
        ).data,

        "auto_approved_reports": ExpenseReportSerializer(
            auto_approved_reports,
            many=True
        ).data,

        "manual_approved_reports": ExpenseReportSerializer(
            manual_approved_reports,
            many=True
        ).data,

        "paid_reports": ExpenseReportSerializer(
            paid_reports,
            many=True
        ).data,

        "all_rejected_reports": ExpenseReportSerializer(
            all_rejected_reports[:10],
            many=True
        ).data,
    })
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def company_admin_dashboard(request):
    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can access this dashboard."},
            status=status.HTTP_403_FORBIDDEN
        )

    company = profile.company

    departments = Department.objects.filter(company=company)

    users = defer_missing_company_role_fields(
        UserProfile.objects.select_related(
            "user",
            "department",
            "company_role",
        ).filter(
            company=company
        ),
        prefix="company_role__",
    )

    employees = users.filter(
        company_role__can_submit_expense=True
    )

    approvers = users.filter(
        company_role__can_approve_expense=True
    )

    payment_users = users.filter(
        company_role__can_mark_paid=True
    )

    reports = ExpenseReport.objects.filter(
        company=company
    )

    company_roles = defer_missing_company_role_fields(
        CompanyRole.objects.filter(
            company=company
        )
    )

    workflows = ApprovalWorkflow.objects.filter(
        company=company,
        is_active=True
    ).select_related(
        "start_role"
    ).prefetch_related(
        "steps",
        "steps__approver_role",
        "steps__specific_user",
        "steps__specific_user__user",
        "steps__department",
    ).order_by(
        "start_role__name"
    )

    workflow_steps = ApprovalWorkflowStep.objects.filter(
        workflow__company=company,
        workflow__is_active=True,
        is_active=True
    )

    workflow_steps_count = workflow_steps.count()

    platform_receipt_email = getattr(
        settings,
        "PLATFORM_RECEIPT_EMAIL",
        "receipts@zepex.ai"
    )

    reimbursement_email_configured = bool(
        company.reimbursement_email
    )

    smtp_configured = bool(
        getattr(settings, "EMAIL_HOST", None)
        and getattr(settings, "EMAIL_HOST_USER", None)
        and getattr(settings, "EMAIL_HOST_PASSWORD", None)
    )

    policy_configured = CompanyPolicy.objects.filter(
        company=company
    ).exists()

    total_expense_amount = reports.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    submitted_amount = reports.filter(
        status=ExpenseReport.STATUS_SUBMITTED
    ).aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    approved_amount = reports.filter(
        status=ExpenseReport.STATUS_APPROVED
    ).aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    paid_amount = reports.filter(
        status=ExpenseReport.STATUS_PAID
    ).aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    rejected_amount = reports.filter(
        status=ExpenseReport.STATUS_REJECTED
    ).aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    department_wise_spend = reports.values(
        "department__name"
    ).annotate(
        total=Sum("total_amount")
    ).order_by("-total")

    try:
        category_wise_spend = ExpenseLineItem.objects.filter(
            receipt__report__company=company
        ).values(
            "category"
        ).annotate(
            total=Sum("amount")
        ).order_by("-total")
        list(category_wise_spend)
    except Exception:
        category_wise_spend = []

    recent_reports = reports.select_related(
        "employee",
        "employee__user",
        "department",
        "current_approver",
        "current_approver__user",
        "current_workflow_step",
        "current_workflow_step__approver_role",
        "current_workflow_step__specific_user",
        "current_workflow_step__specific_user__user",
    ).order_by("-created_at")[:10]

    return Response({
        "company_admin": {
            "name": request.user.get_full_name(),
            "email": request.user.email,
            "company": company.name,
            "company_id": str(company.id),
        },

        "setup_status": {
            "departments_created": departments.exists(),
            "users_created": users.exists(),
            "employees_created": employees.exists(),
            "roles_created": company_roles.exists(),
            "workflow_configured": workflows.exists(),
            "workflow_steps_created": workflow_steps_count > 0,
            "policy_configured": policy_configured,
            "email_forwarding_enabled": reimbursement_email_configured,
            "platform_smtp_configured": smtp_configured,
            "imap_required": False,
            "company_smtp_required": False,
            "workflow_engine": "Dynamic",
        },

        "email_forwarding": {
            "company_reimbursement_email": company.reimbursement_email,
            "platform_receipt_email": platform_receipt_email,
            "forwarding_instruction": (
                f"Forward all reimbursement emails from "
                f"{company.reimbursement_email or 'your company reimbursement email'} "
                f"to {platform_receipt_email}"
            ),
        },

        "metrics": {
            "total_departments": departments.count(),
            "total_users": users.count(),
            "total_employees": employees.count(),
            "total_approvers": approvers.count(),
            "payment_users": payment_users.count(),
            "active_users": users.filter(user__is_active=True).count(),
            "inactive_users": users.filter(user__is_active=False).count(),
            "total_company_roles": company_roles.count(),

            "total_workflows": workflows.count(),
            "total_workflow_steps": workflow_steps_count,
            "reporting_manager_steps": workflow_steps.filter(
                approver_type=ApprovalWorkflowStep.APPROVER_REPORTING_MANAGER
            ).count(),
            "department_manager_steps": workflow_steps.filter(
                approver_type=ApprovalWorkflowStep.APPROVER_DEPARTMENT_MANAGER
            ).count(),
            "company_role_steps": workflow_steps.filter(
                approver_type=ApprovalWorkflowStep.APPROVER_COMPANY_ROLE
            ).count(),
            "specific_user_steps": workflow_steps.filter(
                approver_type=ApprovalWorkflowStep.APPROVER_SPECIFIC_USER
            ).count(),

            "total_reports": reports.count(),
            "draft_reports": reports.filter(
                status=ExpenseReport.STATUS_DRAFT
            ).count(),
            "submitted_reports": reports.filter(
                status=ExpenseReport.STATUS_SUBMITTED
            ).count(),
            "approved_reports": reports.filter(
                status=ExpenseReport.STATUS_APPROVED
            ).count(),
            "rejected_reports": reports.filter(
                status=ExpenseReport.STATUS_REJECTED
            ).count(),
            "paid_reports": reports.filter(
                status=ExpenseReport.STATUS_PAID
            ).count(),

            "total_expense_amount": str(total_expense_amount),
            "submitted_amount": str(submitted_amount),
            "approved_amount": str(approved_amount),
            "paid_amount": str(paid_amount),
            "rejected_amount": str(rejected_amount),
        },

        "department_wise_spend": [
            {
                "department": item["department__name"] or "No Department",
                "total_amount": str(item["total"] or 0),
            }
            for item in department_wise_spend
        ],

        "category_wise_spend": [
            {
                "category": item["category"] or "Uncategorized",
                "total_amount": str(item["total"] or 0),
            }
            for item in category_wise_spend
        ],

        "recent_reports": [
            {
                "id": str(report.id),
                "employee_name": (
                    report.employee.user.get_full_name()
                    or report.employee.user.email
                ),
                "employee_email": report.employee.user.email,
                "department": (
                    report.department.name
                    if report.department else None
                ),
                "month": report.month,
                "status": report.status,
                "total_amount": str(report.total_amount),
                "current_approver": (
                    {
                        "id": str(report.current_approver.id),
                        "email": report.current_approver.user.email,
                        "name": report.current_approver.user.get_full_name(),
                    }
                    if report.current_approver else None
                ),
                "current_step": (
                    report.current_workflow_step.step_order
                    if report.current_workflow_step else None
                ),
                "approver_type": (
                    report.current_workflow_step.get_approver_type_display()
                    if report.current_workflow_step else None
                ),
                "workflow_completed": report.workflow_completed,
                "created_at": report.created_at,
            }
            for report in recent_reports
        ],

        "workflow_summary": {
            "total_workflows": workflows.count(),
            "active_workflows": workflows.count(),
            "total_steps": workflow_steps_count,
            "engine": "Dynamic Approval Engine",
            "supports": [
                "Reporting Manager",
                "Department Manager",
                "Company Role",
                "Specific User",
                "Automatic Skip Logic",
                "Role Based Workflow",
                "Role Based Policy Rules",
                "Department Routing",
                "Company Routing",
            ],
        },

        "workflows": [
            {
                "id": str(workflow.id),
                "name": workflow.name,
                "start_role": (
                    workflow.start_role.name
                    if workflow.start_role else None
                ),
                "start_role_id": (
                    str(workflow.start_role.id)
                    if workflow.start_role else None
                ),
                "steps": [
                    {
                        "id": str(step.id),
                        "step_order": step.step_order,
                        "approver_type": step.approver_type,
                        "approver_type_name": step.get_approver_type_display(),
                        "approver_role": (
                            step.approver_role.name
                            if step.approver_role else None
                        ),
                        "specific_user": (
                            {
                                "id": str(step.specific_user.id),
                                "name": step.specific_user.user.get_full_name(),
                                "email": step.specific_user.user.email,
                            }
                            if step.specific_user else None
                        ),
                        "routing_type": step.routing_type,
                        "department": (
                            step.department.name
                            if step.department else None
                        ),
                        "is_active": step.is_active,
                    }
                    for step in workflow.steps.filter(
                        is_active=True
                    ).order_by("step_order")
                ],
            }
            for workflow in workflows
        ],
    })
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@platform_permission_required("view_dashboard")
def platform_dashboard(request):

    companies = Company.objects.all()
    reports = ExpenseReport.objects.all()
    company_requests = CompanyRegistrationRequest.objects.all()

    total_expense_amount = reports.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    approved_amount = reports.filter(
        status=ExpenseReport.STATUS_APPROVED
    ).aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    paid_amount = reports.filter(
        status=ExpenseReport.STATUS_PAID
    ).aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    recent_companies = companies.order_by("-created_at")[:5]

    return Response({
        "platform_owner": {
            "name": request.user.get_full_name(),
            "email": request.user.email,
        },

        "metrics": {
            "total_companies": companies.count(),
            "verified_companies": companies.filter(is_verified=True).count(),
            "unverified_companies": companies.filter(is_verified=False).count(),

            "pending_company_requests": company_requests.filter(status="PENDING").count(),
            "approved_company_requests": company_requests.filter(status="APPROVED").count(),
            "rejected_company_requests": company_requests.filter(status="REJECTED").count(),

            "total_reports": reports.count(),
            "draft_reports": reports.filter(status=ExpenseReport.STATUS_DRAFT).count(),
            "submitted_reports": reports.filter(status=ExpenseReport.STATUS_SUBMITTED).count(),
            "approved_reports": reports.filter(status=ExpenseReport.STATUS_APPROVED).count(),
            "rejected_reports": reports.filter(status=ExpenseReport.STATUS_REJECTED).count(),
            "paid_reports": reports.filter(status=ExpenseReport.STATUS_PAID).count(),

            "total_expense_amount": str(total_expense_amount),
            "approved_amount": str(approved_amount),
            "paid_amount": str(paid_amount),
        },

        "recent_companies": [
            {
                "id": str(company.id),
                "name": company.name,
                "domain": company.domain,
                "is_verified": company.is_verified,
                "created_at": company.created_at,
            }
            for company in recent_companies
        ]
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_router(request):

    profile = getattr(request.user, "profile", None)

    if has_platform_permission(
        user=request.user,
        profile=profile,
        permission_code="view_dashboard",
    ):
        return platform_dashboard(request)

    if profile is None:
        return Response(
            {"error": "User profile is not configured."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if profile.role == "COMPANY_ADMIN":
        return company_admin_dashboard(request)

    # -----------------------------
    # Company Role Required
    # -----------------------------
    if not profile.company_role:
        return Response(
            {
                "error": "Your company role is not assigned."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    role = profile.company_role

    # -----------------------------
    # Accounts Dashboard
    # -----------------------------
    if role.can_mark_paid:
        return payment_dashboard(request)

    # -----------------------------
    # Approval Dashboard
    # -----------------------------
    if role.can_approve_expense:
        return approver_dashboard(request)

    # -----------------------------
    # Employee Dashboard
    # -----------------------------
    if role.can_submit_expense:
        return employee_dashboard(request)

    return Response(
        {
            "error": "No dashboard assigned for your company role."
        },
        status=status.HTTP_403_FORBIDDEN
    )    