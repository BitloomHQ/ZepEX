import { StatusBadge } from '@/components/StatusBadge'
import { WorkflowTimeline } from '@/components/reports/WorkflowTimeline'
import type { ExpenseReport } from '@/types'
import { formatDate, formatDateTime } from '@/lib/utils'
import { formatReportTotal, reportDisplayCurrency } from '@/lib/receiptDisplay'

interface EmployeeReportSummaryProps {
  report: ExpenseReport
}

export function EmployeeReportSummary({ report }: EmployeeReportSummaryProps) {
  const receiptCount = report.receipts?.length ?? 0
  const isDraft = report.status === 'DRAFT'
  const currency = reportDisplayCurrency(report)

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 bg-slate-50/80 px-4 py-3 sm:px-5">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
              {isDraft ? 'Draft claim' : 'Expense report'}
            </p>
            <p className="mt-0.5 text-sm text-slate-600">{formatDate(report.month)}</p>
          </div>
          <StatusBadge status={report.status} />
        </div>

        <div className="flex flex-wrap items-end justify-between gap-4 px-4 py-5 sm:px-5">
          <div>
            <p className="text-xs font-medium text-slate-500">Claim total · {currency}</p>
            <p className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">
              {formatReportTotal(report)}
            </p>
            <p className="mt-2 text-sm text-slate-500">
              {receiptCount} receipt{receiptCount === 1 ? '' : 's'}
              {report.department_name ? ` · ${report.department_name}` : ''}
            </p>
          </div>
        </div>
      </div>

      {!isDraft && report.workflow_timeline && report.workflow_timeline.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4 sm:px-5">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
            Approval progress
          </p>
          <WorkflowTimeline timeline={report.workflow_timeline} />
        </div>
      )}

      {!isDraft && (
        <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-4 text-sm sm:grid-cols-3 sm:px-5">
          <div>
            <p className="text-slate-500">Submitted</p>
            <p className="font-medium text-slate-900">
              {formatDateTime(report.submitted_at) || '—'}
            </p>
          </div>
          <div>
            <p className="text-slate-500">Auto-approved</p>
            <p className="font-medium text-slate-900">
              {formatDateTime(report.auto_approved_at) || '—'}
            </p>
          </div>
          <div>
            <p className="text-slate-500">Paid</p>
            <p className="font-medium text-slate-900">{formatDateTime(report.paid_at) || '—'}</p>
          </div>
        </div>
      )}

      {report.latest_rejection_reason && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900 sm:px-5">
          <p className="font-medium">
            Rejected by {report.latest_rejection_reason.rejected_by} (
            {report.latest_rejection_reason.role})
          </p>
          <p className="mt-1">{report.latest_rejection_reason.reason}</p>
        </div>
      )}
    </div>
  )
}
