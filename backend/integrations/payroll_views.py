from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from expenses.models import ExpenseReport
from expenses.report_utils import get_reports_awaiting_payment

from .models import (
    BambooHRPayrollBatch,
    BambooHRPayrollBatchItem,
    IntegrationEmployeeMapping,
)
from .services.bamboohr_payroll import (
    BambooHRPayrollError,
    add_report_to_payroll_batch,
    build_payroll_batch_csv,
    can_manage_bamboohr_payroll,
    confirm_payroll_batch,
    create_payroll_batch,
    get_connected_bamboohr_integration,
    mark_payroll_batch_ready,
    remove_report_from_payroll_batch,
)


def _parse_date(value, field_name):
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise BambooHRPayrollError(
            f"{field_name} must use YYYY-MM-DD format.",
            code="INVALID_DATE",
        ) from exc


def _require_payroll_manager(request):
    profile = request.user.profile
    if not profile.company:
        raise BambooHRPayrollError(
            "Company is not assigned.",
            code="COMPANY_NOT_ASSIGNED",
        )
    if not can_manage_bamboohr_payroll(profile):
        raise BambooHRPayrollError(
            "You are not allowed to manage BambooHR payroll batches.",
            code="PAYROLL_PERMISSION_DENIED",
        )
    return profile


def _error_response(exc):
    response_status = status.HTTP_400_BAD_REQUEST
    if exc.code in {"PAYROLL_BATCH_NOT_FOUND", "REPORT_NOT_FOUND"}:
        response_status = status.HTTP_404_NOT_FOUND
    elif exc.code == "PAYROLL_PERMISSION_DENIED":
        response_status = status.HTTP_403_FORBIDDEN
    elif exc.code in {
        "REPORT_ALREADY_IN_PAYROLL",
        "PAYROLL_BATCH_NOT_DRAFT",
        "PAYROLL_BATCH_NOT_READY",
        "PAYROLL_BATCH_NOT_EXPORTED",
        "INVALID_PAYROLL_BATCH_STATUS",
    }:
        response_status = status.HTTP_409_CONFLICT

    return Response(
        {
            "success": False,
            "error": str(exc),
            "code": exc.code,
        },
        status=response_status,
    )


def _serialize_item(item):
    return {
        "id": str(item.id),
        "report_id": str(item.report_id),
        "external_employee_id": item.external_employee_id,
        "employee_number": item.employee_number,
        "employee_name": item.employee_name,
        "external_email": item.external_email,
        "bamboohr_employee_status": item.bamboohr_employee_status,
        "include_in_payroll": item.include_in_payroll,
        "amount": str(item.amount),
        "currency": item.currency,
        "earning_code": item.earning_code,
        "status": item.status,
        "error_message": item.error_message,
        "exported_at": item.exported_at,
        "confirmed_at": item.confirmed_at,
        "created_at": item.created_at,
    }


def _serialize_batch(batch, *, include_items=False):
    active_items = batch.items.exclude(
        status=BambooHRPayrollBatchItem.STATUS_REMOVED
    )
    totals = active_items.aggregate(total_amount=Sum("amount"))
    payload = {
        "id": str(batch.id),
        "integration_id": str(batch.integration_id),
        "provider": "BAMBOOHR",
        "status": batch.status,
        "payroll_period_start": batch.payroll_period_start,
        "payroll_period_end": batch.payroll_period_end,
        "pay_date": batch.pay_date,
        "earning_code": batch.earning_code,
        "notes": batch.notes,
        "payroll_run_reference": batch.payroll_run_reference,
        "report_count": active_items.count(),
        "total_amount": str(totals["total_amount"] or Decimal("0.00")),
        "exported_at": batch.exported_at,
        "confirmed_at": batch.confirmed_at,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
    }
    if include_items:
        payload["items"] = [
            _serialize_item(item)
            for item in active_items.select_related("report")
        ]
    return payload


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bamboohr_payroll_eligible_reports(request):
    try:
        profile = _require_payroll_manager(request)
        integration = get_connected_bamboohr_integration(profile.company)
    except BambooHRPayrollError as exc:
        return _error_response(exc)

    reports = (
        get_reports_awaiting_payment(profile.company)
        .select_related("employee", "employee__user", "department")
        .order_by("month", "employee__user__first_name")
    )
    employee_ids = [report.employee_id for report in reports]
    mappings = {
        mapping.user_profile_id: mapping
        for mapping in IntegrationEmployeeMapping.objects.filter(
            integration=integration,
            user_profile_id__in=employee_ids,
        )
    }
    active_report_ids = set(
        BambooHRPayrollBatchItem.objects.filter(
            batch__integration=integration,
            status__in=[
                BambooHRPayrollBatchItem.STATUS_PENDING,
                BambooHRPayrollBatchItem.STATUS_EXPORTED,
                BambooHRPayrollBatchItem.STATUS_CONFIRMED,
            ],
        ).values_list("report_id", flat=True)
    )

    results = []
    for report in reports:
        mapping = mappings.get(report.employee_id)
        results.append(
            {
                "report_id": str(report.id),
                "month": report.month,
                "employee": {
                    "id": str(report.employee_id),
                    "name": (
                        report.employee.user.get_full_name().strip()
                        or report.employee.user.email
                    ),
                    "email": report.employee.user.email,
                },
                "department": report.department.name if report.department else None,
                "total_amount": str(report.total_amount),
                "status": report.status,
                "workflow_completed": report.workflow_completed,
                "bamboohr_mapping": {
                    "mapped": bool(mapping),
                    "external_employee_id": (
                        mapping.external_employee_id if mapping else None
                    ),
                },
                "already_in_payroll": report.id in active_report_ids,
                "can_add": bool(mapping) and report.id not in active_report_ids,
            }
        )

    return Response(
        {
            "success": True,
            "provider": "BAMBOOHR",
            "count": len(results),
            "results": results,
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def bamboohr_payroll_batches(request):
    try:
        profile = _require_payroll_manager(request)
        integration = get_connected_bamboohr_integration(profile.company)

        if request.method == "POST":
            batch = create_payroll_batch(
                integration=integration,
                actor_profile=profile,
                payroll_period_start=_parse_date(
                    request.data.get("payroll_period_start"),
                    "payroll_period_start",
                ),
                payroll_period_end=_parse_date(
                    request.data.get("payroll_period_end"),
                    "payroll_period_end",
                ),
                pay_date=_parse_date(request.data.get("pay_date"), "pay_date"),
                earning_code=request.data.get(
                    "earning_code",
                    "EXPENSE_REIMBURSEMENT",
                ),
                notes=request.data.get("notes", ""),
            )
            return Response(
                {
                    "success": True,
                    "message": "BambooHR payroll batch created.",
                    "batch": _serialize_batch(batch, include_items=True),
                },
                status=status.HTTP_201_CREATED,
            )

        queryset = (
            BambooHRPayrollBatch.objects
            .filter(integration=integration)
            .select_related("integration")
            .prefetch_related("items")
        )
        requested_status = str(request.query_params.get("status") or "").upper()
        if requested_status:
            queryset = queryset.filter(status=requested_status)

        results = [_serialize_batch(batch) for batch in queryset[:100]]
        return Response(
            {
                "success": True,
                "provider": "BAMBOOHR",
                "count": len(results),
                "results": results,
            }
        )
    except BambooHRPayrollError as exc:
        return _error_response(exc)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bamboohr_payroll_batch_detail(request, batch_id):
    try:
        profile = _require_payroll_manager(request)
        batch = (
            BambooHRPayrollBatch.objects
            .select_related("integration")
            .prefetch_related("items")
            .get(id=batch_id, integration__company=profile.company)
        )
    except BambooHRPayrollBatch.DoesNotExist:
        return _error_response(
            BambooHRPayrollError(
                "BambooHR payroll batch was not found.",
                code="PAYROLL_BATCH_NOT_FOUND",
            )
        )
    except BambooHRPayrollError as exc:
        return _error_response(exc)

    return Response(
        {
            "success": True,
            "batch": _serialize_batch(batch, include_items=True),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bamboohr_payroll_add_report(request, batch_id):
    try:
        profile = _require_payroll_manager(request)
        report_id = request.data.get("report_id")
        if not report_id:
            raise BambooHRPayrollError(
                "report_id is required.",
                code="REPORT_ID_REQUIRED",
            )
        item = add_report_to_payroll_batch(
            batch_id=batch_id,
            report_id=report_id,
            company=profile.company,
        )
        return Response(
            {
                "success": True,
                "message": "Approved report added to the payroll batch.",
                "item": _serialize_item(item),
            },
            status=status.HTTP_201_CREATED,
        )
    except BambooHRPayrollError as exc:
        return _error_response(exc)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def bamboohr_payroll_remove_report(request, batch_id, report_id):
    try:
        profile = _require_payroll_manager(request)
        remove_report_from_payroll_batch(
            batch_id=batch_id,
            report_id=report_id,
            company=profile.company,
        )
        return Response(
            {
                "success": True,
                "message": "Report removed from the payroll batch.",
            }
        )
    except BambooHRPayrollError as exc:
        return _error_response(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bamboohr_payroll_mark_ready(request, batch_id):
    try:
        profile = _require_payroll_manager(request)
        batch = mark_payroll_batch_ready(
            batch_id=batch_id,
            company=profile.company,
        )
        return Response(
            {
                "success": True,
                "message": "Payroll batch is ready for CSV export.",
                "batch": _serialize_batch(batch, include_items=True),
            }
        )
    except BambooHRPayrollError as exc:
        return _error_response(exc)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bamboohr_payroll_csv(request, batch_id):
    try:
        profile = _require_payroll_manager(request)
        batch, csv_content = build_payroll_batch_csv(
            batch_id=batch_id,
            company=profile.company,
        )
    except BambooHRPayrollError as exc:
        return _error_response(exc)

    filename = f"zepex-bamboohr-payroll-{batch.pay_date}-{batch.id}.csv"
    response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-ZepEx-Payroll-Batch-ID"] = str(batch.id)
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bamboohr_payroll_confirm(request, batch_id):
    try:
        profile = _require_payroll_manager(request)
        batch, payment_results = confirm_payroll_batch(
            batch_id=batch_id,
            company=profile.company,
            actor_profile=profile,
            payroll_run_reference=request.data.get("payroll_run_reference"),
            notes=request.data.get("notes", ""),
        )
        return Response(
            {
                "success": True,
                "message": (
                    "Payroll batch confirmed. Reports were marked PAID after "
                    "finance confirmation."
                ),
                "batch": _serialize_batch(batch, include_items=True),
                "payments": payment_results,
            }
        )
    except BambooHRPayrollError as exc:
        return _error_response(exc)
