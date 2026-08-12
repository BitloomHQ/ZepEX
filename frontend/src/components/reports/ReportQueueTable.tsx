import { Banknote, Check, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { ReportDetail } from '@/components/ReportDetail'
import { ExpenseReportTable } from '@/components/reports/ExpenseReportTable'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { createReportApprovalContext } from '@/lib/reportApprovalHandlers'
import type { QueuedReport } from '@/lib/reportQueue'

interface ReportQueueTableProps {
  items: QueuedReport[]
  actionId: string | null
  notes: Record<string, string>
  onNotesChange: (reportId: string, value: string) => void
  onApprove?: (reportId: string) => void
  onReject?: (reportId: string) => void
  onMarkPaid?: (reportId: string) => void
  onRefresh?: () => Promise<void>
  showAdminOverride?: boolean
}

export function ReportQueueTable({
  items,
  actionId,
  notes,
  onNotesChange,
  onApprove,
  onReject,
  onMarkPaid,
  onRefresh,
  showAdminOverride,
}: ReportQueueTableProps) {
  return (
    <ExpenseReportTable
      reports={items.map((item) => item.report)}
      renderRowActions={(report) => {
        const item = items.find((entry) => entry.report.id === report.id)
        if (!item) return null

        if (item.queueKind === 'approval_pending' && onApprove && onReject) {
          return (
            <div className="flex flex-wrap gap-1.5">
              <Button
                size="sm"
                variant="success"
                disabled={actionId === report.id}
                onClick={() => onApprove(report.id)}
              >
                <Check className="h-3.5 w-3.5" />
                Approve
              </Button>
              <Button
                size="sm"
                variant="destructive"
                disabled={actionId === report.id}
                onClick={() => onReject(report.id)}
              >
                <X className="h-3.5 w-3.5" />
                Reject
              </Button>
            </div>
          )
        }

        if (item.queueKind === 'payment_pending' && onMarkPaid) {
          return (
            <Button
              size="sm"
              disabled={actionId === report.id}
              onClick={() => onMarkPaid(report.id)}
            >
              <Banknote className="h-3.5 w-3.5" />
              Mark paid
            </Button>
          )
        }

        return null
      }}
      renderExpanded={(report) => {
        const item = items.find((entry) => entry.report.id === report.id)
        if (!item) return null

        const showApprovalActions = item.queueKind === 'approval_pending' && onApprove && onReject
        const showPaymentActions = item.queueKind === 'payment_pending' && onMarkPaid

        return (
          <ExpandedReportPanel
            report={report}
            employeeLabel={report.employee_name || report.employee_email}
            notes={notes[report.id] || ''}
            onNotesChange={(value) => onNotesChange(report.id, value)}
            showApprovalActions={Boolean(showApprovalActions)}
            showPaymentActions={Boolean(showPaymentActions)}
            actionId={actionId}
            onApprove={onApprove}
            onReject={onReject}
            onMarkPaid={onMarkPaid}
            onRefresh={onRefresh}
            showAdminOverride={showAdminOverride}
          />
        )
      }}
    />
  )
}

function ExpandedReportPanel({
  report,
  employeeLabel,
  notes,
  onNotesChange,
  showApprovalActions,
  showPaymentActions,
  actionId,
  onApprove,
  onReject,
  onMarkPaid,
  onRefresh,
  showAdminOverride,
}: {
  report: QueuedReport['report']
  employeeLabel: string
  notes: string
  onNotesChange: (value: string) => void
  showApprovalActions: boolean
  showPaymentActions: boolean
  actionId: string | null
  onApprove?: (reportId: string) => void
  onReject?: (reportId: string) => void
  onMarkPaid?: (reportId: string) => void
  onRefresh?: () => Promise<void>
  showAdminOverride?: boolean
}) {
  const approvalContext =
    showApprovalActions && onRefresh
      ? createReportApprovalContext(report.id, {
          enabled: true,
          busy: actionId === report.id,
          onRefresh,
        })
      : undefined

  let actions: ReactNode = null

  if (showApprovalActions) {
    actions = (
      <div className="space-y-3 rounded-lg border border-[#e2e8f0] bg-white px-4 py-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-sm font-medium text-gray-900">{employeeLabel}</p>
        </div>
        <Textarea
          placeholder="Notes (required for rejection)"
          value={notes}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => onNotesChange(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <Button
            variant="success"
            disabled={actionId === report.id}
            onClick={(e) => {
              e.stopPropagation()
              onApprove?.(report.id)
            }}
          >
            <Check className="h-4 w-4" />
            Approve
          </Button>
          <Button
            variant="destructive"
            disabled={actionId === report.id}
            onClick={(e) => {
              e.stopPropagation()
              onReject?.(report.id)
            }}
          >
            <X className="h-4 w-4" />
            Reject
          </Button>
        </div>
      </div>
    )
  } else if (showPaymentActions) {
    actions = (
      <div className="space-y-3 rounded-lg border border-[#e2e8f0] bg-white px-4 py-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-sm font-medium text-gray-900">{employeeLabel}</p>
        </div>
        <Textarea
          placeholder="Payment notes (optional)"
          value={notes}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => onNotesChange(e.target.value)}
        />
        <Button
          disabled={actionId === report.id}
          onClick={(e) => {
            e.stopPropagation()
            onMarkPaid?.(report.id)
          }}
        >
          <Banknote className="h-4 w-4" />
          Mark as paid
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {actions}
      <ReportDetail
        report={report}
        showEmployee={false}
        showAdminOverride={showAdminOverride}
        approvalContext={approvalContext}
      />
    </div>
  )
}
