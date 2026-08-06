from datetime import date

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    parser_classes
)
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from tenants.models import Company, UserProfile, CompanyRole, Department

from .models import (
    ExpenseAuditTrail,
    ExpenseReport,
    ExpenseSubmission,
    ExpenseReceipt,
    Department
)
from tenants.models import CompanyRole
from expenses.workflow_engine import reorder_workflow_steps
from .workflow_engine import resolve_step_approver
from expenses.workflow_engine import start_workflow
from .serializers import ExpenseReceiptSerializer,ExpenseReportSerializer, ApprovalHistorySerializer
from .services import extract_receipt_with_gemini, recalculate_receipt_from_line_items, sync_receipt_totals_for_report
from .models import ApprovalWorkflow, ApprovalWorkflowStep
from .serializers import ApprovalWorkflowSerializer, ApprovalWorkflowStepSerializer
from django.utils import timezone
from .models import ApprovalHistory
from .serializers import ExpenseReportSerializer
from django.utils import timezone
from django.conf import settings
from .ai_queue import queue_receipt_ai_processing
from .report_utils import (
    can_approve_report,
    get_or_create_current_month_report,
    get_pending_approval_reports_for,
    get_reports_awaiting_payment,
    is_payment_queue_role,
)
from audit_logs.utils import create_audit_log
from .models import ExpenseLineItem

from tenants.permissions import IsCompanyAdmin
from django.core.paginator import Paginator
from .email_notifications import send_workflow_status_email
from .workflow_engine import can_user_approve_step,approve_current_step,reject_current_step
from django.db import transaction
from expenses.workflow_validator import validate_workflow

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_receipt(request):

    profile = request.user.profile

    if not profile.company_role:
        return Response(
            {
                "error": "Your company role is not assigned. Please contact company admin."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if not profile.company_role.can_upload_receipt:
        return Response(
            {"error": "Your role is not allowed to upload receipts."},
            status=status.HTTP_403_FORBIDDEN
        )

    if not profile.department:
        return Response(
            {"error": "User is not assigned to any department."},
            status=status.HTTP_400_BAD_REQUEST
        )

    files = request.FILES.getlist("files") or request.FILES.getlist("files[]")
    legacy_file = request.FILES.get("receipt_file")
    if legacy_file and not files:
        files = [legacy_file]

    if not files:
        return Response(
            {"error": "files is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    report = get_or_create_current_month_report(profile)

    requested_report_id = request.data.get("report_id")
    if requested_report_id and str(requested_report_id) != str(report.id):
        return Response(
            {
                "error": "report_id does not match the current draft monthly report."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if report.status != ExpenseReport.STATUS_DRAFT:
        return Response(
            {
                "error": "Current month report is already submitted. You cannot add more receipts."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    receipt_ids = []

    for receipt_file in files:
        submission = ExpenseSubmission.objects.create(
            report=report,
            company=profile.company,
            employee=profile,
            source=ExpenseSubmission.SOURCE_WEB
        )

        receipt = ExpenseReceipt.objects.create(
            report=report,
            submission=submission,
            company=profile.company,
            employee=profile,
            department=profile.department,
            receipt_file=receipt_file,
            status=ExpenseReceipt.STATUS_AI_PROCESSING,
            ai_status=ExpenseReceipt.AI_PENDING,
        )

        receipt_ids.append(str(receipt.id))

        create_audit_log(
            company=profile.company,
            action="RECEIPT_UPLOADED",
            action_by=profile,
            message=f"Receipt uploaded by {request.user.email}",
            metadata={
                "receipt_id": str(receipt.id),
                "report_id": str(report.id),
                "submission_id": str(submission.id),
                "filename": receipt.receipt_file.name,
                "source": ExpenseSubmission.SOURCE_WEB,
                "company_role": profile.company_role.name,
                "department": profile.department.name,
            }
        )

        create_audit_log(
            company=profile.company,
            action="AI_PROCESSING_STARTED",
            action_by=profile,
            message="AI extraction started for uploaded receipt.",
            metadata={
                "receipt_id": str(receipt.id),
                "report_id": str(report.id),
            }
        )

        queue_receipt_ai_processing(
            receipt_id=str(receipt.id),
            company=profile.company,
            action_by=profile,
            report_id=str(report.id),
        )

    return Response(
        {
            "message": "Receipt uploaded successfully.",
            "report_id": str(report.id),
            "receipt_ids": receipt_ids,
        },
        status=status.HTTP_201_CREATED
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def retry_receipt_ai(request, receipt_id):

    profile = request.user.profile

    try:
        receipt = ExpenseReceipt.objects.select_related("report").get(
            id=receipt_id,
            company=profile.company,
            employee=profile,
        )
    except ExpenseReceipt.DoesNotExist:
        return Response(
            {"error": "Receipt not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if receipt.ai_status not in (
        ExpenseReceipt.AI_FAILED,
        ExpenseReceipt.AI_RETRY_REQUIRED,
    ):
        return Response(
            {
                "error": "This receipt is not eligible for AI retry.",
                "ai_status": receipt.ai_status,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if receipt.report and receipt.report.status != ExpenseReport.STATUS_DRAFT:
        return Response(
            {
                "error": "You can retry AI extraction only before submitting the monthly report."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    receipt.ai_retry_count += 1
    receipt.save(update_fields=["ai_retry_count", "updated_at"])

    create_audit_log(
        company=profile.company,
        action="AI_PROCESSING_STARTED",
        action_by=profile,
        message="AI extraction retry started for receipt.",
        metadata={
            "receipt_id": str(receipt.id),
            "report_id": str(receipt.report_id) if receipt.report_id else None,
            "ai_retry_count": receipt.ai_retry_count,
        },
    )

    ai_result = extract_receipt_with_gemini(receipt)
    receipt.refresh_from_db()

    if ai_result.get("success"):
        from .policy_services import validate_receipt_policy

        policy_result = validate_receipt_policy(receipt)
        ai_result["policy"] = policy_result

        create_audit_log(
            company=profile.company,
            action="AI_PROCESSING_COMPLETED",
            action_by=profile,
            message="AI extraction retry completed successfully.",
            metadata={
                "receipt_id": str(receipt.id),
                "report_id": str(receipt.report_id) if receipt.report_id else None,
                "vendor": receipt.vendor_name,
                "total_amount": str(receipt.total_amount),
                "ai_retry_count": receipt.ai_retry_count,
            },
        )
    else:
        create_audit_log(
            company=profile.company,
            action="AI_PROCESSING_FAILED",
            action_by=profile,
            message=ai_result.get("error", "AI extraction failed."),
            metadata={
                "receipt_id": str(receipt.id),
                "report_id": str(receipt.report_id) if receipt.report_id else None,
                "error": ai_result.get("error"),
                "ai_retry_count": receipt.ai_retry_count,
                "retry_allowed": ai_result.get("retry_allowed"),
            },
        )

    serializer = ExpenseReceiptSerializer(receipt)

    return Response(
        {
            "message": "AI retry completed.",
            "receipt": serializer.data,
            "ai_result": ai_result,
        },
        status=status.HTTP_200_OK,
    )
from .email_service import ingest_forwarded_receipt_email

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def email_ingest_receipt(request):
    """
    HTTP ingest for receipt attachments (e.g. inbound parse webhook).

    Expected multipart fields:
    - sender_email
    - original_recipient (or recipient_email) — company reimbursement address when known
    - subject (optional)
    - receipt_file
    - X-Email-Ingest-Secret header when EMAIL_INGEST_SECRET is set
    """
    ingest_secret = getattr(settings, "EMAIL_INGEST_SECRET", "") or ""
    if ingest_secret:
        provided = (
            request.headers.get("X-Email-Ingest-Secret")
            or request.data.get("ingest_secret")
            or ""
        )
        if provided != ingest_secret:
            return Response(
                {"success": False, "error": "Unauthorized ingest request."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

    sender_email = str(request.data.get("sender_email", "")).lower().strip()
    email_subject = str(request.data.get("subject", "")).strip()
    original_recipient = str(
        request.data.get("original_recipient")
        or request.data.get("recipient_email")
        or ""
    ).lower().strip()
    receipt_file = request.FILES.get("receipt_file")

    result = ingest_forwarded_receipt_email(
        sender_email=sender_email,
        original_recipient=original_recipient,
        subject=email_subject,
        uploaded_file=receipt_file,
    )

    if not result.get("success"):
        return Response(
            {
                "success": False,
                "error": result.get("error"),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    report = result["report"]
    submission = result["submission"]
    receipt = result["receipt"]
    employee = result["employee"]
    company = result["company"]

    queue_receipt_ai_processing(
        receipt_id=str(receipt.id),
        company=company,
        action_by=employee,
        report_id=str(report.id),
    )

    create_audit_log(
        company=company,
        action="EMAIL_RECEIPT_RECEIVED",
        action_by=employee,
        message=f"Receipt email received from {sender_email}",
        metadata={
            "receipt_id": str(receipt.id),
            "report_id": str(report.id),
            "submission_id": str(submission.id),
            "email_subject": email_subject,
            "source": ExpenseSubmission.SOURCE_EMAIL,
            "sender_email": sender_email,
            "original_recipient": original_recipient,
            "company": company.name,
            "company_role": (
                employee.company_role.name
                if employee.company_role else None
            ),
            "ai_status": receipt.ai_status,
        },
    )

    create_audit_log(
        company=company,
        action="AI_PROCESSING_QUEUED",
        action_by=employee,
        message="AI extraction queued for email receipt.",
        metadata={
            "receipt_id": str(receipt.id),
            "report_id": str(report.id),
            "ai_status": receipt.ai_status,
        },
    )

    serializer = ExpenseReceiptSerializer(receipt)

    return Response(
        {
            "success": True,
            "message": "Receipt received successfully. AI extraction has been queued.",
            "company": company.name,
            "employee": employee.user.email,
            "report_id": str(report.id),
            "receipt": serializer.data,
            "ai": {
                "status": receipt.ai_status,
                "message": "Receipt has been queued for AI processing.",
            },
        },
        status=status.HTTP_201_CREATED,
    )

from .services import (
    sync_receipt_totals_for_report,
    recalculate_report_total,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_current_month_report(request):
    profile = request.user.profile

    if not profile.company_role:
        return Response(
            {
                "error": "Your company role is not assigned. Please contact company admin."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if not profile.company_role.can_submit_expense:
        return Response(
            {
                "error": "Your role is not allowed to submit expense reports."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    current_month = date.today().replace(day=1)

    try:
        report = ExpenseReport.objects.prefetch_related(
            "receipts"
        ).get(
            company=profile.company,
            employee=profile,
            month=current_month,
            status=ExpenseReport.STATUS_DRAFT
        )

    except ExpenseReport.DoesNotExist:
        return Response(
            {
                "error": "No draft report found for current month."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    # --------------------------------------------------
    # Report should contain at least one receipt
    # --------------------------------------------------

    if not report.receipts.exists():
        return Response(
            {
                "error": "Cannot submit an empty report."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    receipts = report.receipts.all()

    # --------------------------------------------------
    # AI must finish for every receipt
    # --------------------------------------------------

    processing_receipts = receipts.filter(
        ai_status__in=[
            ExpenseReceipt.AI_PENDING,
            ExpenseReceipt.AI_PROCESSING,
        ]
    )

    if processing_receipts.exists():
        return Response(
            {
                "error": (
                    "Some receipts are still being processed by AI. "
                    "Please wait before submitting the report."
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    failed_receipts = receipts.filter(
        ai_status__in=[
            ExpenseReceipt.AI_FAILED,
            ExpenseReceipt.AI_RETRY_REQUIRED,
        ]
    )

    if failed_receipts.exists():
        return Response(
            {
                "error": (
                    "Some receipts failed AI extraction. "
                    "Please retry them before submitting."
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # --------------------------------------------------
    # Synchronize totals before submission
    # --------------------------------------------------

    sync_receipt_totals_for_report(report)
    recalculate_report_total(report)

    report.refresh_from_db()

    # --------------------------------------------------
    # Check policy violations
    # --------------------------------------------------

    has_violation = report.receipts.filter(
        has_any_violation=True
    ).exists()

    submitted_at = timezone.now()

    # ==================================================
    # CASE 1 : Auto Approve
    # ==================================================

    if not has_violation:

        report.status = ExpenseReport.STATUS_APPROVED
        report.is_auto_approved = True
        report.auto_approved_at = submitted_at
        report.current_workflow_step = None
        report.current_approver = None
        report.workflow_completed = True
        report.submitted_at = submitted_at

        report.save(update_fields=[
            "status",
            "is_auto_approved",
            "auto_approved_at",
            "current_workflow_step",
            "current_approver",
            "workflow_completed",
            "submitted_at",
            "updated_at",
        ])

        report.receipts.update(
            status=ExpenseReceipt.STATUS_APPROVED
        )

        ApprovalHistory.objects.create(
            report=report,
            action_by=profile,
            action=ApprovalHistory.ACTION_REPORT_SUBMITTED,
            comments=(
                "Monthly expense report submitted and "
                "approved automatically by system because "
                "all receipts satisfied company policy."
            )
        )

        create_audit_log(
            company=profile.company,
            action="REPORT_AUTO_APPROVED",
            action_by=profile,
            message=f"Expense report {report.id} approved automatically by system.",
            metadata={
                "report_id": str(report.id),
                "employee_email": profile.user.email,
                "auto_approved": True,
                "reason": "No policy violations found.",
                "status": ExpenseReport.STATUS_APPROVED,
            }
        )

        serializer = ExpenseReportSerializer(report)

        return Response(
            {
                "message": "Monthly report approved automatically by system.",
                "auto_approved": True,
                "approval_required": False,
                "view_only_for_workflow": True,
                "next_action": "Accounts can mark this report as paid.",
                "report": serializer.data,
            },
            status=status.HTTP_200_OK
        )

    # ==================================================
    # CASE 2 : Approval Workflow
    # ==================================================

    success, result = start_workflow(report)

    if not success:
        return Response(
            {
                "error": result
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    workflow = result["workflow"]
    first_step = result["step"]
    approver = result["approver"]

    report.refresh_from_db()

    create_audit_log(
        company=profile.company,
        action="REPORT_SUBMITTED",
        action_by=profile,
        message=f"Expense report {report.id} submitted for approval.",
        metadata={
            "report_id": str(report.id),
            "employee_email": profile.user.email,
            "has_violation": True,
            "auto_approved": False,
            "workflow_id": str(workflow.id),
            "workflow_name": workflow.name,
            "workflow_start_role": (
                workflow.start_role.name
                if workflow.start_role else None
            ),
            "current_step": first_step.step_order,
            "approver_type": first_step.approver_type,
            "approver_role": (
                first_step.approver_role.name
                if first_step.approver_role else None
            ),
            "current_approver_id": str(approver.id),
            "current_approver_email": approver.user.email,
            "routing_type": first_step.routing_type,
            "approval_department": (
                first_step.department.name
                if first_step.department else None
            ),
        }
    )

    serializer = ExpenseReportSerializer(report)

    return Response(
        {
            "message": "Monthly report submitted successfully.",
            "auto_approved": False,
            "approval_required": True,
            "workflow": {
                "id": str(workflow.id),
                "name": workflow.name,
                "start_role": (
                    workflow.start_role.name
                    if workflow.start_role else None
                ),
            },
            "current_approval_step": {
                "step_order": first_step.step_order,
                "approver_type": first_step.approver_type,
                "approver_role": (
                    first_step.approver_role.name
                    if first_step.approver_role else None
                ),
                "routing_type": first_step.routing_type,
                "department": (
                    first_step.department.name
                    if first_step.department else None
                ),
            },
            "current_approver": {
                "id": str(approver.id),
                "name": approver.user.get_full_name(),
                "email": approver.user.email,
            },
            "report": serializer.data,
        },
        status=status.HTTP_200_OK
    )
from django.db.models import Q
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_pending_approval_reports(request):
    profile = request.user.profile

    if not profile.company_role:
        return Response(
            {"error": "Your company role is not assigned."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not profile.company_role.can_approve_expense:
        return Response(
            {"error": "Your role is not allowed to approve expense reports."},
            status=status.HTTP_403_FORBIDDEN
        )

    reports = get_pending_approval_reports_for(profile)

    employee_id = request.GET.get("employee_id")
    employee_email = request.GET.get("employee_email")
    department_id = request.GET.get("department_id")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    min_amount = request.GET.get("min_amount")
    max_amount = request.GET.get("max_amount")

    if employee_id:
        reports = reports.filter(employee_id=employee_id)

    if employee_email:
        reports = reports.filter(
            employee__user__email__icontains=employee_email
        )

    if department_id:
        reports = reports.filter(department_id=department_id)

    if start_date:
        reports = reports.filter(submitted_at__date__gte=start_date)

    if end_date:
        reports = reports.filter(submitted_at__date__lte=end_date)

    if min_amount:
        reports = reports.filter(total_amount__gte=min_amount)

    if max_amount:
        reports = reports.filter(total_amount__lte=max_amount)

    reports = reports.select_related(
        "employee",
        "employee__user",
        "department",
        "current_workflow_step",
        "current_workflow_step__approver_role",
        "current_workflow_step__department"
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history"
    ).distinct().order_by(
        "-submitted_at"
    )

    serializer = ExpenseReportSerializer(
        reports,
        many=True
    )

    return Response({
        "count": reports.count(),
        "filters": {
            "employee_id": employee_id,
            "employee_email": employee_email,
            "department_id": department_id,
            "start_date": start_date,
            "end_date": end_date,
            "min_amount": min_amount,
            "max_amount": max_amount,
        },
        "results": serializer.data
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_approved_approval_reports(request):
    profile = request.user.profile

    if not profile.company_role:
        return Response(
            {"error": "Your company role is not assigned."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not profile.company_role.can_approve_expense:
        return Response(
            {"error": "Your role is not allowed to approve expense reports."},
            status=status.HTTP_403_FORBIDDEN
        )

    reports = ExpenseReport.objects.filter(
        company=profile.company,
        approval_history__action=ApprovalHistory.ACTION_STEP_APPROVED,
        approval_history__action_by=profile,
    )

    employee_id = request.GET.get("employee_id")
    employee_email = request.GET.get("employee_email")
    department_id = request.GET.get("department_id")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    min_amount = request.GET.get("min_amount")
    max_amount = request.GET.get("max_amount")

    if employee_id:
        reports = reports.filter(employee_id=employee_id)

    if employee_email:
        reports = reports.filter(
            employee__user__email__icontains=employee_email
        )

    if department_id:
        reports = reports.filter(department_id=department_id)

    if start_date:
        reports = reports.filter(submitted_at__date__gte=start_date)

    if end_date:
        reports = reports.filter(submitted_at__date__lte=end_date)

    if min_amount:
        reports = reports.filter(total_amount__gte=min_amount)

    if max_amount:
        reports = reports.filter(total_amount__lte=max_amount)

    reports = reports.select_related(
        "employee",
        "employee__user",
        "department",
        "current_workflow_step",
        "current_workflow_step__approver_role",
        "current_workflow_step__department"
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history"
    ).distinct().order_by(
        "-updated_at"
    )

    serializer = ExpenseReportSerializer(
        reports,
        many=True
    )

    return Response({
        "count": reports.count(),
        "filters": {
            "employee_id": employee_id,
            "employee_email": employee_email,
            "department_id": department_id,
            "start_date": start_date,
            "end_date": end_date,
            "min_amount": min_amount,
            "max_amount": max_amount,
        },
        "results": serializer.data
    })



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_month_report(request):

    profile = request.user.profile

    if not profile.company_role:
        return Response(
            {"error": "Your company role is not assigned."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not (
        profile.company_role.can_submit_expense
        or profile.company_role.can_upload_receipt
    ):
        return Response(
            {"error": "Your role is not allowed to view expense reports."},
            status=status.HTTP_403_FORBIDDEN
        )

    current_month = date.today().replace(day=1)

    try:
        report = ExpenseReport.objects.select_related(
            "employee",
            "employee__user",
            "department",
            "current_workflow_step",
            "current_workflow_step__workflow",
            "current_workflow_step__approver_role",
            "current_workflow_step__department",
        ).prefetch_related(
            "receipts",
            "receipts__line_items",
            "approval_history",
            "approval_history__action_by",
            "approval_history__action_by__user",
            "approval_history__action_by__company_role",
        ).get(
            company=profile.company,
            employee=profile,
            month=current_month
        )

    except ExpenseReport.DoesNotExist:
        return Response(
            {"message": "No report found for current month."},
            status=status.HTTP_404_NOT_FOUND
        )

    if sync_receipt_totals_for_report(report):
        report.refresh_from_db()

    serializer = ExpenseReportSerializer(report)
    payload = serializer.data
    payload["report_id"] = str(report.id)
    payload["no_violation_receipts"] = ExpenseReceiptSerializer(
        report.receipts.filter(has_any_violation=False),
        many=True,
    ).data
    payload["violation_receipts"] = ExpenseReceiptSerializer(
        report.receipts.filter(has_any_violation=True),
        many=True,
    ).data

    return Response(payload)




@api_view(["POST"])
@permission_classes([IsAuthenticated])
def accounts_mark_paid(request, report_id):

    profile = request.user.profile

    is_company_admin = profile.role == "COMPANY_ADMIN"

    if not is_company_admin:

        if not profile.company_role:
            return Response(
                {"error": "Your company role is not assigned."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not profile.company_role.can_mark_paid:
            return Response(
                {"error": "Your role is not allowed to mark reports as paid."},
                status=status.HTTP_403_FORBIDDEN
            )

    actor_role = (
        "COMPANY_ADMIN"
        if is_company_admin
        else profile.company_role.name
    )

    try:
        report = get_reports_awaiting_payment(
            profile.company
        ).get(
            id=report_id,
            company=profile.company,
        )

    except ExpenseReport.DoesNotExist:
        return Response(
            {"error": "Report not found in accounts/payment queue."},
            status=status.HTTP_404_NOT_FOUND
        )

    notes = request.data.get("notes", "").strip()

    previous_status = report.status

    report.status = ExpenseReport.STATUS_PAID
    report.paid_notes = notes
    report.paid_at = timezone.now()
    report.workflow_completed = True
    report.current_workflow_step = None
    report.current_approver = None

    report.save(update_fields=[
        "status",
        "paid_notes",
        "paid_at",
        "workflow_completed",
        "current_workflow_step",
        "current_approver",
        "updated_at",
    ])

    report.receipts.all().update(
        status=ExpenseReceipt.STATUS_PAID
    )

    ApprovalHistory.objects.create(
        report=report,
        action_by=profile,
        action=ApprovalHistory.ACTION_PAID,
        comments=notes,
    )

    create_audit_log(
        company=profile.company,
        action="MARKED_PAID",
        action_by=profile,
        message=f"{actor_role} marked expense report {report.id} as paid.",
        metadata={
            "report_id": str(report.id),
            "employee_email": report.employee.user.email,
            "department": (
                report.department.name
                if report.department else None
            ),
            "total_amount": str(report.total_amount),
            "previous_status": previous_status,
            "paid_by": profile.user.email,
            "paid_by_role": actor_role,
            "is_company_admin_override": is_company_admin,
            "notes": notes,
        }
    )

    send_workflow_status_email(
        report=report,
        subject="Reimbursement Payment Completed",
        message=(
            "Your reimbursement report has been processed by Accounts "
            "and marked as paid."
        ),
        action="PAID",
        action_by=profile,
        current_step=None,
        notes=notes or "Payment completed successfully.",
        notify_previous_approvers=True,
    )

    serializer = ExpenseReportSerializer(report)

    return Response(
        {
            "message": "Report marked as paid.",
            "previous_status": previous_status,
            "paid_by": actor_role,
            "is_company_admin_override": is_company_admin,
            "report": serializer.data,
        },
        status=status.HTTP_200_OK
    )

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_expense_line_item(request, line_item_id):
    profile = request.user.profile

    try:
        line_item = ExpenseLineItem.objects.select_related(
            "receipt",
            "receipt__report"
        ).get(
            id=line_item_id,
            receipt__company=profile.company,
            receipt__employee=profile
        )

    except ExpenseLineItem.DoesNotExist:
        return Response(
            {"error": "Line item not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    report = line_item.receipt.report

    if report.status != ExpenseReport.STATUS_DRAFT:
        return Response(
            {"error": "You can delete line items only before submitting the monthly report."},
            status=status.HTTP_400_BAD_REQUEST
        )

    receipt = line_item.receipt

    deleted_metadata = {
        "line_item_id": str(line_item.id),
        "receipt_id": str(receipt.id),
        "report_id": str(report.id),
        "description": line_item.description,
        "category": line_item.category,
        "amount": str(line_item.amount),
        "vendor": line_item.vendor,
    }

    line_item.delete()

    recalculate_receipt_from_line_items(receipt)

    create_audit_log(
        company=profile.company,
        action="LINE_ITEM_DELETED",
        action_by=profile,
        message=f"Line item deleted by {profile.user.email}",
        metadata=deleted_metadata
    )

    return Response(
        {"message": "Expense line item deleted successfully."},
        status=status.HTTP_200_OK
    )


@api_view(["DELETE", "POST"])
@permission_classes([IsAuthenticated])
def delete_receipt(request, receipt_id):
    profile = request.user.profile

    try:
        receipt = ExpenseReceipt.objects.select_related("report", "submission").get(
            id=receipt_id,
            company=profile.company,
            employee=profile,
        )
    except ExpenseReceipt.DoesNotExist:
        return Response(
            {"error": "Receipt not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    report = receipt.report
    if report is None or report.status != ExpenseReport.STATUS_DRAFT:
        return Response(
            {"error": "You can delete receipts only before submitting the monthly report."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    deleted_metadata = {
        "receipt_id": str(receipt.id),
        "report_id": str(report.id),
        "vendor_name": receipt.vendor_name,
        "total_amount": str(receipt.total_amount) if receipt.total_amount is not None else None,
        "filename": receipt.receipt_file.name if receipt.receipt_file else None,
    }
    submission = receipt.submission

    if receipt.receipt_file:
        receipt.receipt_file.delete(save=False)

    receipt.delete()

    if submission is not None and not submission.receipts.exists():
        submission.delete()

    sync_receipt_totals_for_report(report)

    create_audit_log(
        company=profile.company,
        action="RECEIPT_DELETED",
        action_by=profile,
        message=f"Receipt deleted by {profile.user.email}",
        metadata=deleted_metadata,
    )

    return Response(
        {"message": "Receipt deleted successfully."},
        status=status.HTTP_200_OK,
    )


from tenants.permissions import IsCompanyAdmin

@api_view(["GET"])
@permission_classes([
    IsAuthenticated,
    IsCompanyAdmin,
])
def admin_employee_expenses(request, employee_id):

    company = request.user.profile.company

    try:
        employee = UserProfile.objects.select_related(
            "user",
            "department",
            "company_role"
        ).get(
            id=employee_id,
            company=company
        )

    except UserProfile.DoesNotExist:

        return Response(
            {"error": "Employee not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    reports = ExpenseReport.objects.filter(
        company=company,
        employee=employee
    ).select_related(
        "current_workflow_step",
        "current_workflow_step__approver_role",
        "current_workflow_step__department"
    ).prefetch_related(
        "receipts",
        "receipts__line_items"
    ).order_by(
        "-month",
        "-created_at"
    )

    serializer = ExpenseReportSerializer(
        reports,
        many=True
    )

    return Response({
        "employee": {
            "id": str(employee.id),

            "name": (
                f"{employee.user.first_name} "
                f"{employee.user.last_name}"
            ).strip(),

            "email": employee.user.email,

            "department": (
                employee.department.name
                if employee.department else None
            ),

            "system_role": employee.role,

            "company_role": (
                employee.company_role.name
                if employee.company_role else None
            ),
        },

        "count": reports.count(),

        "results": serializer.data
    })



@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_or_update_workflow(request):
    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can configure workflow."},
            status=status.HTTP_403_FORBIDDEN
        )

    name = request.data.get("name", "Default Workflow").strip()
    start_role_id = request.data.get("start_role")
    workflow_id = request.data.get("workflow_id")

    if not start_role_id:
        return Response(
            {"error": "start_role is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        start_role = CompanyRole.objects.get(
            id=start_role_id,
            company=profile.company,
            is_active=True
        )
    except CompanyRole.DoesNotExist:
        return Response(
            {"error": "Invalid start_role for this company."},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():

        if workflow_id:
            try:
                workflow = ApprovalWorkflow.objects.get(
                    id=workflow_id,
                    company=profile.company
                )
            except ApprovalWorkflow.DoesNotExist:
                return Response(
                    {"error": "Workflow not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            if ApprovalWorkflow.objects.filter(
                company=profile.company,
                start_role=start_role,
                is_active=True
            ).exclude(id=workflow.id).exists():
                return Response(
                    {"error": f"A workflow already exists for '{start_role.name}'."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            workflow.name = name
            workflow.start_role = start_role
            workflow.is_active = True
            workflow.save()

            created = False

        else:
            if ApprovalWorkflow.objects.filter(
                company=profile.company,
                start_role=start_role,
                is_active=True
            ).exists():
                return Response(
                    {"error": f"A workflow already exists for '{start_role.name}'."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            workflow = ApprovalWorkflow.objects.create(
                company=profile.company,
                name=name,
                start_role=start_role,
                is_active=True
            )

            created = True

        if workflow.steps.filter(is_active=True).exists():
            valid, error = validate_workflow(workflow)

            if not valid:
                transaction.set_rollback(True)
                return Response(
                    {"error": error},
                    status=status.HTTP_400_BAD_REQUEST
                )

        create_audit_log(
            company=profile.company,
            action="WORKFLOW_CREATED" if created else "WORKFLOW_UPDATED",
            action_by=profile,
            message=(
                f"Workflow '{workflow.name}' "
                f"{'created' if created else 'updated'} "
                f"for role '{start_role.name}'."
            ),
            metadata={
                "workflow_id": str(workflow.id),
                "workflow_name": workflow.name,
                "start_role": start_role.name,
                "created": created,
            }
        )

        serializer = ApprovalWorkflowSerializer(workflow)

        return Response(
            {
                "message": (
                    "Workflow created successfully."
                    if created else
                    "Workflow updated successfully."
                ),
                "workflow": serializer.data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_workflow_step(request, step_id):
    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can update workflow steps."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        step = ApprovalWorkflowStep.objects.select_related(
            "workflow",
            "approver_role",
            "specific_user",
            "specific_user__user",
            "department",
        ).get(
            id=step_id,
            workflow__company=profile.company,
            is_active=True
        )
    except ApprovalWorkflowStep.DoesNotExist:
        return Response(
            {"error": "Workflow step not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    workflow = step.workflow
    new_step_order = request.data.get("step_order")

    with transaction.atomic():

        new_approver_type = request.data.get("approver_type")

        if new_approver_type:
            if new_approver_type not in [
                ApprovalWorkflowStep.APPROVER_REPORTING_MANAGER,
                ApprovalWorkflowStep.APPROVER_DEPARTMENT_MANAGER,
                ApprovalWorkflowStep.APPROVER_COMPANY_ROLE,
                ApprovalWorkflowStep.APPROVER_SPECIFIC_USER,
            ]:
                return Response(
                    {"error": "Invalid approver_type."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            step.approver_type = new_approver_type

            if new_approver_type in [
                ApprovalWorkflowStep.APPROVER_REPORTING_MANAGER,
                ApprovalWorkflowStep.APPROVER_DEPARTMENT_MANAGER,
            ]:
                step.approver_role = None
                step.specific_user = None

            elif new_approver_type == ApprovalWorkflowStep.APPROVER_COMPANY_ROLE:
                step.specific_user = None

            elif new_approver_type == ApprovalWorkflowStep.APPROVER_SPECIFIC_USER:
                step.approver_role = None

        if "approver_role" in request.data:
            approver_role_id = request.data.get("approver_role")

            if approver_role_id in [None, "", "null"]:
                step.approver_role = None
            else:
                try:
                    role = CompanyRole.objects.get(
                        id=approver_role_id,
                        company=profile.company,
                        is_active=True
                    )
                    step.approver_role = role
                except CompanyRole.DoesNotExist:
                    return Response(
                        {"error": "Approver role not found."},
                        status=status.HTTP_404_NOT_FOUND
                    )

        if "specific_user" in request.data:
            specific_user_id = request.data.get("specific_user")

            if specific_user_id in [None, "", "null"]:
                step.specific_user = None
            else:
                try:
                    user = UserProfile.objects.get(
                        id=specific_user_id,
                        company=profile.company,
                        user__is_active=True
                    )
                    step.specific_user = user
                except UserProfile.DoesNotExist:
                    return Response(
                        {"error": "Specific user not found or inactive."},
                        status=status.HTTP_404_NOT_FOUND
                    )

        if "routing_type" in request.data:
            routing_type = request.data.get("routing_type")

            if routing_type not in [
                ApprovalWorkflowStep.ROUTING_COMPANY,
                ApprovalWorkflowStep.ROUTING_DEPARTMENT,
            ]:
                return Response(
                    {"error": "Invalid routing_type."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            step.routing_type = routing_type

        if "department" in request.data:
            department_id = request.data.get("department")

            if department_id in [None, "", "null"]:
                step.department = None
            else:
                try:
                    department = Department.objects.get(
                        id=department_id,
                        company=profile.company,
                        is_active=True
                    )
                    step.department = department
                except Department.DoesNotExist:
                    return Response(
                        {"error": "Department not found."},
                        status=status.HTTP_404_NOT_FOUND
                    )

        if step.approver_type == ApprovalWorkflowStep.APPROVER_COMPANY_ROLE and not step.approver_role:
            return Response(
                {"error": "approver_role is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if step.approver_type == ApprovalWorkflowStep.APPROVER_SPECIFIC_USER and not step.specific_user:
            return Response(
                {"error": "specific_user is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

       

        if step.routing_type == ApprovalWorkflowStep.ROUTING_COMPANY:
            step.department = None

        step.full_clean()
        step.save()

        if new_step_order:
            new_step_order = int(new_step_order)

            active_steps = list(
                ApprovalWorkflowStep.objects.filter(
                    workflow=workflow,
                    is_active=True
                ).order_by("step_order", "created_at")
            )

            active_steps = [
                item for item in active_steps
                if item.id != step.id
            ]

            if new_step_order < 1:
                new_step_order = 1

            if new_step_order > len(active_steps) + 1:
                new_step_order = len(active_steps) + 1

            active_steps.insert(new_step_order - 1, step)

            for index, item in enumerate(active_steps, start=1):
                item.step_order = index + 1000
                item.save(update_fields=["step_order"])

            for index, item in enumerate(active_steps, start=1):
                item.step_order = index
                item.save(update_fields=["step_order"])

            step.refresh_from_db()

        valid, error = validate_workflow(workflow)

        if not valid:
            transaction.set_rollback(True)
            return Response(
                {"error": error},
                status=status.HTTP_400_BAD_REQUEST
            )

        create_audit_log(
            company=profile.company,
            action="WORKFLOW_STEP_UPDATED",
            action_by=profile,
            message=f"Workflow step {step.step_order} updated.",
            metadata={
                "workflow_id": str(workflow.id),
                "workflow_name": workflow.name,
                "step_id": str(step.id),
                "step_order": step.step_order,
                "approver_type": step.approver_type,
                "approver_role": step.approver_role.name if step.approver_role else None,
                "specific_user": step.specific_user.user.email if step.specific_user else None,
                "routing_type": step.routing_type,
                "department": step.department.name if step.department else None,
            },
        )

        return Response(
            {
                "message": "Workflow step updated successfully.",
                "workflow": {
                    "id": str(workflow.id),
                    "name": workflow.name,
                },
                "step": ApprovalWorkflowStepSerializer(step).data,
            },
            status=status.HTTP_200_OK
        )
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_workflow_step(request):
    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can add workflow steps."},
            status=status.HTTP_403_FORBIDDEN
        )

    workflow_id = request.data.get("workflow_id")

    if not workflow_id:
        return Response(
            {"error": "workflow_id is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        workflow = ApprovalWorkflow.objects.get(
            id=workflow_id,
            company=profile.company,
            is_active=True
        )
    except ApprovalWorkflow.DoesNotExist:
        return Response(
            {"error": "Workflow not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = ApprovalWorkflowStepSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    approver_type = serializer.validated_data["approver_type"]
    approver_role = serializer.validated_data.get("approver_role")
    specific_user = serializer.validated_data.get("specific_user")
    routing_type = serializer.validated_data.get(
        "routing_type",
        ApprovalWorkflowStep.ROUTING_COMPANY
    )
    department = serializer.validated_data.get("department")
    step_order = serializer.validated_data["step_order"]

    if approver_type == ApprovalWorkflowStep.APPROVER_COMPANY_ROLE:
        if not approver_role:
            return Response(
                {"error": "approver_role is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if approver_role.company != profile.company:
            return Response(
                {"error": "Approver role belongs to another company."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not approver_role.is_active:
            return Response(
                {"error": "Approver role is inactive."},
                status=status.HTTP_400_BAD_REQUEST
            )

        specific_user = None

    elif approver_type == ApprovalWorkflowStep.APPROVER_SPECIFIC_USER:
        if not specific_user:
            return Response(
                {"error": "specific_user is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if specific_user.company != profile.company:
            return Response(
                {"error": "Specific user belongs to another company."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not specific_user.user.is_active:
            return Response(
                {"error": "Specific user is inactive."},
                status=status.HTTP_400_BAD_REQUEST
            )

        approver_role = None

    elif approver_type in [
        ApprovalWorkflowStep.APPROVER_REPORTING_MANAGER,
        ApprovalWorkflowStep.APPROVER_DEPARTMENT_MANAGER,
    ]:
        approver_role = None
        specific_user = None

    

        if department.company != profile.company:
            return Response(
                {"error": "Department belongs to another company."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not department.is_active:
            return Response(
                {"error": "Department is inactive."},
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        department = None

    if ApprovalWorkflowStep.objects.filter(
        workflow=workflow,
        step_order=step_order,
        is_active=True
    ).exists():
        return Response(
            {"error": f"Step order {step_order} already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        step = serializer.save(
            workflow=workflow,
            approver_role=approver_role,
            specific_user=specific_user,
            routing_type=routing_type,
            department=department,
            is_active=True
        )

        step.full_clean()
        step.save()

        valid, error = validate_workflow(workflow)

        if not valid:
            transaction.set_rollback(True)
            return Response(
                {"error": error},
                status=status.HTTP_400_BAD_REQUEST
            )

        create_audit_log(
            company=profile.company,
            action="WORKFLOW_STEP_CREATED",
            action_by=profile,
            message=f"Workflow step {step.step_order} created.",
            metadata={
                "workflow_id": str(workflow.id),
                "workflow_name": workflow.name,
                "start_role": workflow.start_role.name,
                "step_order": step.step_order,
                "approver_type": step.approver_type,
                "approver_role": step.approver_role.name if step.approver_role else None,
                "specific_user": step.specific_user.user.email if step.specific_user else None,
                "routing_type": step.routing_type,
                "department": step.department.name if step.department else None,
            },
        )

        return Response(
            {
                "message": "Workflow step added successfully.",
                "workflow": {
                    "id": str(workflow.id),
                    "name": workflow.name,
                    "start_role": workflow.start_role.name,
                },
                "step": ApprovalWorkflowStepSerializer(step).data,
            },
            status=status.HTTP_201_CREATED
        )
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_workflow(request):

    profile = request.user.profile

    workflows = ApprovalWorkflow.objects.filter(
        company=profile.company,
        is_active=True
    ).select_related(
        "start_role"
    ).prefetch_related(
        "steps",
        "steps__approver_role",
        "steps__department",
        "steps__specific_user",
        "steps__specific_user__user",
    ).order_by(
        "start_role__name"
    )

    workflow_id = request.query_params.get("workflow_id")
    start_role_id = request.query_params.get("start_role")

    if workflow_id:
        workflows = workflows.filter(id=workflow_id)
    elif start_role_id:
        workflows = workflows.filter(start_role_id=start_role_id)

    if not workflows.exists():
        return Response(
            {
                "error": "No workflow configured."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = ApprovalWorkflowSerializer(
        workflows,
        many=True
    )

    if workflow_id or start_role_id:
        return Response(serializer.data[0])

    return Response(
        {
            "count": workflows.count(),
            "workflows": serializer.data
        }
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def deactivate_workflow_step(request, step_id):

    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {
                "error": "Only company admin can deactivate workflow steps."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        step = ApprovalWorkflowStep.objects.select_related(
            "workflow"
        ).get(
            id=step_id,
            workflow__company=profile.company,
            is_active=True,
        )

    except ApprovalWorkflowStep.DoesNotExist:
        return Response(
            {
                "error": "Workflow step not found."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    workflow = step.workflow
    old_step_order = step.step_order

    step.is_active = False

    # Move inactive step away from active ordering range
    step.step_order = old_step_order + 10000

    step.save(update_fields=[
        "is_active",
        "step_order",
    ])

    reorder_workflow_steps(workflow)

    create_audit_log(
        company=profile.company,
        action="WORKFLOW_STEP_DEACTIVATED",
        action_by=profile,
        message=f"Workflow step {old_step_order} deactivated.",
        metadata={
            "workflow_id": str(workflow.id),
            "workflow_name": workflow.name,
            "step_id": str(step.id),
            "old_step_order": old_step_order,
        }
    )

    return Response(
        {
            "message": "Workflow step deactivated successfully.",
            "workflow_steps_reordered": True,
        },
        status=status.HTTP_200_OK
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_workflow(request, workflow_id):
    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can delete workflows."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        workflow = ApprovalWorkflow.objects.select_related("start_role").get(
            id=workflow_id,
            company=profile.company,
            is_active=True,
        )
    except ApprovalWorkflow.DoesNotExist:
        return Response(
            {"error": "Workflow not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    in_use = ExpenseReport.objects.filter(
        company=profile.company,
        current_workflow_step__workflow=workflow,
        workflow_completed=False,
        status=ExpenseReport.STATUS_SUBMITTED,
    ).exists()

    if in_use:
        return Response(
            {
                "error": (
                    "Cannot delete this workflow while reports are pending "
                    "approval in it."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    workflow_name = workflow.name
    start_role_name = workflow.start_role.name if workflow.start_role else None
    workflow_id_str = str(workflow.id)

    workflow.delete()

    create_audit_log(
        company=profile.company,
        action="WORKFLOW_DELETED",
        action_by=profile,
        message=(
            f"Workflow '{workflow_name}' deleted"
            + (f" for start role '{start_role_name}'." if start_role_name else ".")
        ),
        metadata={
            "workflow_id": workflow_id_str,
            "workflow_name": workflow_name,
            "start_role_name": start_role_name,
        },
    )

    return Response(
        {"message": f"Workflow '{workflow_name}' deleted successfully."}
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_report_step(request, report_id):

    profile = request.user.profile

    try:
        report = ExpenseReport.objects.select_related(
            "employee",
            "employee__user",
            "department",
            "current_workflow_step",
            "current_workflow_step__workflow",
            "current_workflow_step__approver_role",
            "current_workflow_step__specific_user",
            "current_workflow_step__specific_user__user",
            "current_workflow_step__department",
            "current_approver",
            "current_approver__user",
        ).get(
            id=report_id,
            company=profile.company,
            workflow_completed=False,
            status=ExpenseReport.STATUS_SUBMITTED,
        )

    except ExpenseReport.DoesNotExist:
        return Response(
            {"error": "Report not found or not pending approval."},
            status=status.HTTP_404_NOT_FOUND
        )

    current_step = report.current_workflow_step

    if not current_step:
        return Response(
            {"error": "Workflow step not found."},
            status=status.HTTP_400_BAD_REQUEST
        )

    notes = request.data.get("notes", "").strip()

    success, result = approve_current_step(
        report=report,
        approver_profile=profile,
        notes=notes,
    )

    if not success:
        return Response(
            {"error": result},
            status=status.HTTP_403_FORBIDDEN
        )

    report.refresh_from_db()

    actor_role = (
        "COMPANY_ADMIN"
        if profile.role == "COMPANY_ADMIN"
        else profile.company_role.name
    )

    steps_skipped = result.get("steps_skipped", 0)

    create_audit_log(
        company=profile.company,
        action="STEP_APPROVED",
        action_by=profile,
        message=f"{actor_role} approved expense report {report.id}.",
        metadata={
            "report_id": str(report.id),
            "employee_email": report.employee.user.email,
            "approved_by": profile.user.email,
            "actor_role": actor_role,
            "step_order": current_step.step_order,
            "approver_type": current_step.approver_type,
            "approver_role": (
                current_step.approver_role.name
                if current_step.approver_role else None
            ),
            "specific_user": (
                current_step.specific_user.user.email
                if current_step.specific_user else None
            ),
            "notes": notes,
            "steps_skipped": steps_skipped,
            "workflow_completed": result.get("completed", False),
            "report_status": report.status,
        },
    )

    if result.get("completed"):

        send_workflow_status_email(
            report=report,
            subject="Reimbursement Report Fully Approved",
            message="Your reimbursement report has completed all approval steps.",
            action="APPROVED",
            action_by=profile,
            current_step=current_step,
            notes=notes,
            steps_skipped=steps_skipped,
            notify_previous_approvers=True,
        )

        serializer = ExpenseReportSerializer(report)

        return Response(
            {
                "message": "Workflow completed successfully.",
                "workflow_completed": True,
                "steps_skipped": steps_skipped,
                "approved_by": actor_role,
                "status": report.status,
                "report": serializer.data,
            },
            status=status.HTTP_200_OK
        )

    next_step = result["next_step"]
    next_approver = result["next_approver"]

    send_workflow_status_email(
        report=report,
        subject="Reimbursement Report Moved to Next Approval Step",
        message="Your reimbursement report has moved to the next approval step.",
        action="STEP_APPROVED",
        action_by=profile,
        current_step=current_step,
        notes=notes,
        next_step=next_step,
        next_approver=next_approver,
        steps_skipped=steps_skipped,
        notify_previous_approvers=True,
    )

    serializer = ExpenseReportSerializer(report)

    return Response(
        {
            "message": "Step approved successfully.",
            "workflow_completed": False,
            "steps_skipped": steps_skipped,
            "approved_by": actor_role,
            "next_step": {
                "id": str(next_step.id),
                "step_order": next_step.step_order,
                "approver_type": next_step.approver_type,
                "approver_type_name": next_step.get_approver_type_display(),
                "approver_role": (
                    next_step.approver_role.name
                    if next_step.approver_role else None
                ),
                "specific_user": (
                    next_step.specific_user.user.email
                    if next_step.specific_user else None
                ),
                "routing_type": next_step.routing_type,
                "department": (
                    next_step.department.name
                    if next_step.department else None
                ),
                "next_approver": {
                    "id": str(next_approver.id),
                    "name": (
                        next_approver.user.get_full_name()
                        or next_approver.user.email
                    ),
                    "email": next_approver.user.email,
                },
            },
            "report": serializer.data,
        },
        status=status.HTTP_200_OK
    )
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_report_step(request, report_id):

    profile = request.user.profile

    notes = request.data.get("notes", "").strip()

    if not notes:
        return Response(
            {"error": "Rejection reason is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        report = ExpenseReport.objects.select_related(
            "employee",
            "employee__user",
            "department",
            "current_workflow_step",
            "current_workflow_step__workflow",
            "current_workflow_step__approver_role",
            "current_workflow_step__specific_user",
            "current_workflow_step__specific_user__user",
            "current_workflow_step__department",
            "current_approver",
            "current_approver__user",
        ).get(
            id=report_id,
            company=profile.company,
            workflow_completed=False,
            status=ExpenseReport.STATUS_SUBMITTED
        )

    except ExpenseReport.DoesNotExist:
        return Response(
            {"error": "Report not found or not pending approval."},
            status=status.HTTP_404_NOT_FOUND
        )

    current_step = report.current_workflow_step

    if not current_step:
        return Response(
            {"error": "Workflow step not found."},
            status=status.HTTP_400_BAD_REQUEST
        )

    success, result = reject_current_step(
        report=report,
        approver_profile=profile,
        notes=notes,
    )

    if not success:
        return Response(
            {"error": result},
            status=status.HTTP_403_FORBIDDEN
        )

    report.refresh_from_db()

    actor_role = (
        "COMPANY_ADMIN"
        if profile.role == "COMPANY_ADMIN"
        else profile.company_role.name
    )

    create_audit_log(
        company=profile.company,
        action="STEP_REJECTED",
        action_by=profile,
        message=f"{actor_role} rejected expense report {report.id}.",
        metadata={
    "report_id": str(report.id),
    "employee_email": report.employee.user.email,
    "rejected_by": profile.user.email,
    "actor_role": actor_role,
    "step_order": current_step.step_order,
    "approver_type": current_step.approver_type,
    "approver_role": (
        current_step.approver_role.name
        if current_step.approver_role
        else None
    ),
    "specific_user": (
        current_step.specific_user.user.email
        if current_step.specific_user
        else None
    ),
    "reason": notes,
    "workflow_completed": True,
    "report_status": report.status,
})
    send_workflow_status_email(
        report=report,
        subject="Reimbursement Report Rejected",
        message="Your reimbursement report has been rejected.",
        action="REJECTED",
        action_by=profile,
        current_step=current_step,
        notes=notes,
        notify_previous_approvers=True,
    )

    serializer = ExpenseReportSerializer(report)

    return Response(
        {
            "message": "Report rejected successfully.",
            "workflow_completed": True,
            "rejected_by": actor_role,
            "status": report.status,
            "report": serializer.data,
        },
        status=status.HTTP_200_OK
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_uploaded_expenses(request):

    profile = request.user.profile

    if not profile.company_role:
        return Response(
            {"error": "Your company role is not assigned."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not profile.company_role.can_submit_expense:
        return Response(
            {"error": "Your role is not allowed to view uploaded expenses."},
            status=status.HTTP_403_FORBIDDEN
        )

    reports = ExpenseReport.objects.filter(
        company=profile.company,
        employee=profile
    )

    status_filter = request.GET.get("status")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    min_amount = request.GET.get("min_amount")
    max_amount = request.GET.get("max_amount")

    if status_filter:
        reports = reports.filter(
            status=status_filter.upper()
        )

    if start_date:
        reports = reports.filter(
            submitted_at__date__gte=start_date
        )

    if end_date:
        reports = reports.filter(
            submitted_at__date__lte=end_date
        )

    if min_amount:
        reports = reports.filter(
            total_amount__gte=min_amount
        )

    if max_amount:
        reports = reports.filter(
            total_amount__lte=max_amount
        )

    reports = reports.select_related(
        "department",
        "current_workflow_step",
        "current_workflow_step__approver_role",
        "current_workflow_step__department"
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history"
    ).order_by(
        "-month",
        "-created_at"
    )

    serializer = ExpenseReportSerializer(
        reports,
        many=True
    )

    return Response({
        "count": reports.count(),

        "filters": {
            "status": status_filter,
            "start_date": start_date,
            "end_date": end_date,
            "min_amount": min_amount,
            "max_amount": max_amount,
        },

        "results": serializer.data
    })

from .models import DuplicateReceiptLog
from .serializers import DuplicateReceiptLogSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def duplicate_receipts(request):

    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can view duplicate receipts."},
            status=status.HTTP_403_FORBIDDEN
        )

    duplicates = DuplicateReceiptLog.objects.filter(
        original_receipt__company=profile.company
    ).select_related(
        "original_receipt",
        "duplicate_receipt",
        "original_receipt__employee__user",
        "duplicate_receipt__employee__user",
    ).order_by("-created_at")

    duplicate_type = request.GET.get("type")

    if duplicate_type:
        duplicates = duplicates.filter(
            duplicate_type=duplicate_type.upper()
        )

    serializer = DuplicateReceiptLogSerializer(
        duplicates,
        many=True
    )

    return Response({
        "count": duplicates.count(),
        "filters": {
            "type": duplicate_type,
        },
        "results": serializer.data
    })
from .models import DuplicateReceiptLog
from .serializers import DuplicateReceiptLogSerializer

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def duplicate_receipts(request):
    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can view duplicate receipts."},
            status=status.HTTP_403_FORBIDDEN
        )

    duplicates = DuplicateReceiptLog.objects.filter(
        original_receipt__company=profile.company
    ).select_related(
        "original_receipt",
        "duplicate_receipt",
        "original_receipt__employee__user",
        "duplicate_receipt__employee__user",
    ).order_by("-created_at")

    duplicate_type = request.GET.get("type")

    if duplicate_type:
        duplicates = duplicates.filter(
            duplicate_type=duplicate_type.upper()
        )

    serializer = DuplicateReceiptLogSerializer(
        duplicates,
        many=True
    )

    return Response({
        "count": duplicates.count(),
        "results": serializer.data
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_reports_list(request):

    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {"error": "Only company admin can view reports."},
            status=status.HTTP_403_FORBIDDEN
        )

    reports = ExpenseReport.objects.filter(
        company=profile.company
    )

    status_filter = request.GET.get("status")
    employee_id = request.GET.get("employee_id")
    employee_email = request.GET.get("employee_email")
    department_id = request.GET.get("department_id")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if status_filter:
        reports = reports.filter(status=status_filter.upper())

    if employee_id:
        reports = reports.filter(employee_id=employee_id)

    if employee_email:
        reports = reports.filter(
            employee__user__email__icontains=employee_email
        )

    if department_id:
        reports = reports.filter(department_id=department_id)

    if start_date:
        reports = reports.filter(created_at__date__gte=start_date)

    if end_date:
        reports = reports.filter(created_at__date__lte=end_date)

    reports = reports.select_related(
        "employee",
        "employee__user",
        "department",
        "current_workflow_step",
        "current_workflow_step__approver_role",
        "current_workflow_step__department",
    ).prefetch_related(
        "receipts",
        "receipts__line_items",
        "approval_history"
    ).order_by("-created_at")

    page = request.GET.get("page", 1)

    paginator = Paginator(reports, 10)
    page_obj = paginator.get_page(page)

    serializer = ExpenseReportSerializer(
        page_obj,
        many=True
    )

    return Response({
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "filters": {
            "status": status_filter,
            "employee_id": employee_id,
            "employee_email": employee_email,
            "department_id": department_id,
            "start_date": start_date,
            "end_date": end_date,
        },
        "results": serializer.data
    })

from expenses.workflow_engine import simulate_workflow

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def simulate_workflow_api(request):

    profile = request.user.profile

    if profile.role != "COMPANY_ADMIN":
        return Response(
            {
                "error": "Only company admin can simulate workflow."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    employee_id = request.data.get("employee_id")

    if not employee_id:
        return Response(
            {
                "error": "employee_id is required."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:

        employee = UserProfile.objects.select_related(
            "user",
            "company_role",
            "department",
            "department__manager",
            "reporting_manager",
            "reporting_manager__user",
        ).get(
            id=employee_id,
            company=profile.company,
        )

    except UserProfile.DoesNotExist:

        return Response(
            {
                "error": "Employee not found."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    success, result = simulate_workflow(employee)

    if not success:

        return Response(
            {
                "success": False,
                "error": result,
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    return Response({

        "success": True,

        "employee": {
            "id": str(employee.id),
            "name": employee.user.get_full_name(),
            "email": employee.user.email,
            "company_role": (
                employee.company_role.name
                if employee.company_role else None
            ),
            "department": (
                employee.department.name
                if employee.department else None
            ),
            "reporting_manager": (
                employee.reporting_manager.user.get_full_name()
                if employee.reporting_manager else None
            ),
        },

        "simulation": result,

    })

from expenses.workflow_validator import validate_workflow