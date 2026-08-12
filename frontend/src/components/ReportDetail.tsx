import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { ApprovalHistoryPanel } from '@/components/reports/ApprovalHistoryPanel'
import { CompanyAdminOverrideBadge } from '@/components/reports/CompanyAdminOverrideBadge'
import { ReceiptExpenseCard } from '@/components/reports/ReceiptExpenseCard'
import { WorkflowTimeline } from '@/components/reports/WorkflowTimeline'
import { UserAvatar } from '@/components/ui/user-avatar'
import type { ExpenseReport, ReportApprovalContext } from '@/types'
import { formatDate, formatDateTime } from '@/lib/utils'
import { formatReportTotal } from '@/lib/receiptDisplay'

interface ReportDetailProps {
  report: ExpenseReport
  showEmployee?: boolean
  showAdminOverride?: boolean
  approvalContext?: ReportApprovalContext
}

function approvalTypeLabel(approvalType: string | null | undefined): string | null {
  if (!approvalType) return null
  const labels: Record<string, string> = {
    SYSTEM_AUTO_APPROVED: 'System auto-approved',
    MANUAL_APPROVED: 'Manually approved',
    MANUAL_APPROVAL_REQUIRED: 'Manual approval required',
    REJECTED: 'Rejected',
    NOT_SUBMITTED: 'Not submitted',
  }
  return labels[approvalType] ?? approvalType.replace(/_/g, ' ').toLowerCase()
}

export function ReportDetail({
  report,
  showEmployee = true,
  showAdminOverride = false,
  approvalContext,
}: ReportDetailProps) {
  const approvalLabel = approvalTypeLabel(report.approval_type)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge status={report.status} />
        {report.is_auto_approved && (
          <Badge variant="outline" className="border-green-200 bg-green-50 text-green-800">
            Auto-approved
          </Badge>
        )}
        {approvalLabel && !report.is_auto_approved && (
          <Badge variant="outline" className="capitalize">
            {approvalLabel}
          </Badge>
        )}
        {showAdminOverride && <CompanyAdminOverrideBadge />}
        {showEmployee && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <UserAvatar
              src={report.employee_profile_picture}
              name={report.employee_name}
              email={report.employee_email}
              size="sm"
            />
            <span>{report.employee_name || report.employee_email}</span>
          </div>
        )}
        <span className="text-sm text-muted-foreground">
          {report.department_name} · {formatDate(report.month)}
        </span>
        <span className="w-full text-2xl font-semibold tabular-nums tracking-tight text-slate-900 sm:ml-auto sm:w-auto sm:text-xl">
          {formatReportTotal(report)}
        </span>
      </div>

      {report.workflow_timeline && report.workflow_timeline.length > 0 && (
        <WorkflowTimeline timeline={report.workflow_timeline} />
      )}

      {report.approval_history && report.approval_history.length > 0 && (
        <ApprovalHistoryPanel history={report.approval_history} />
      )}

      <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="text-muted-foreground">Submitted</p>
          <p className="font-medium">{formatDateTime(report.submitted_at)}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Auto-approved</p>
          <p className="font-medium">{formatDateTime(report.auto_approved_at)}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Total amount</p>
          <p className="font-medium">{formatReportTotal(report)}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Paid at</p>
          <p className="font-medium">{formatDateTime(report.paid_at)}</p>
        </div>
      </div>

      {report.latest_rejection_reason && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
          <p className="font-medium">
            Rejected by {report.latest_rejection_reason.rejected_by} (
            {report.latest_rejection_reason.role})
          </p>
          <p className="mt-1">{report.latest_rejection_reason.reason}</p>
          <p className="mt-1 text-xs text-red-700">
            {formatDateTime(report.latest_rejection_reason.rejected_at)}
          </p>
        </div>
      )}

      {report.paid_notes && (
        <div className="rounded-lg bg-muted/60 p-4 text-sm">
          <p>
            <strong>Payment:</strong> {report.paid_notes}
          </p>
        </div>
      )}

      {report.receipts.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Receipts ({report.receipts.length})
          </p>
          {report.receipts.map((receipt) => (
            <ReceiptExpenseCard
              key={receipt.id}
              receipt={receipt}
              approvalContext={approvalContext}
            />
          ))}
        </div>
      )}
    </div>
  )
}
