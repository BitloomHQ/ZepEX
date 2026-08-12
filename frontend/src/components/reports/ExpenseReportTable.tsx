import { ChevronDown, ChevronRight } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { WorkflowStepper } from '@/components/reports/WorkflowStepper'
import { UserAvatar } from '@/components/ui/user-avatar'
import {
  tableBodyCellClass,
  tableGridClass,
  tableHeadCellClass,
  tableHeadRowClass,
} from '@/lib/tableStyles'
import { formatDate } from '@/lib/utils'
import { formatReportTotal } from '@/lib/receiptDisplay'
import type { ExpenseReport } from '@/types'
import { cn } from '@/lib/utils'

interface ExpenseReportTableProps {
  reports: ExpenseReport[]
  renderExpanded: (report: ExpenseReport) => ReactNode
  renderRowActions?: (report: ExpenseReport) => ReactNode
  defaultExpandedId?: string | null
}

export function ExpenseReportTable({
  reports,
  renderExpanded,
  renderRowActions,
  defaultExpandedId = null,
}: ExpenseReportTableProps) {
  const [expandedId, setExpandedId] = useState<string | null>(defaultExpandedId ?? null)
  const columnCount = renderRowActions ? 7 : 6

  useEffect(() => {
    if (defaultExpandedId) {
      setExpandedId(defaultExpandedId)
    }
  }, [defaultExpandedId])

  if (!reports.length) return null

  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <table className={cn(tableGridClass, 'min-w-[48rem]')}>
        <thead>
          <tr className={tableHeadRowClass}>
            <th className={cn(tableHeadCellClass, 'w-10 px-3')} aria-label="Expand" />
            <th className={tableHeadCellClass}>Employee</th>
            <th className={tableHeadCellClass}>Department</th>
            <th className={tableHeadCellClass}>Report month</th>
            <th className={tableHeadCellClass}>Total</th>
            <th className={tableHeadCellClass}>Status</th>
            {renderRowActions && <th className={tableHeadCellClass}>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {reports.map((report) => {
            const expanded = expandedId === report.id
            return (
              <ExpenseReportRow
                key={report.id}
                report={report}
                expanded={expanded}
                columnCount={columnCount}
                onToggle={() => setExpandedId(expanded ? null : report.id)}
                renderExpanded={renderExpanded}
                renderRowActions={renderRowActions}
              />
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ExpenseReportRow({
  report,
  expanded,
  columnCount,
  onToggle,
  renderExpanded,
  renderRowActions,
}: {
  report: ExpenseReport
  expanded: boolean
  columnCount: number
  onToggle: () => void
  renderExpanded: (report: ExpenseReport) => ReactNode
  renderRowActions?: (report: ExpenseReport) => ReactNode
}) {
  const rowActions = renderRowActions?.(report)

  return (
    <>
      <tr
        className="cursor-pointer text-gray-700 transition-colors hover:bg-gray-50/80"
        onClick={onToggle}
      >
        <td className={cn(tableBodyCellClass, 'px-3 py-3 text-muted-foreground')}>
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </td>
        <td className={cn(tableBodyCellClass, 'font-medium text-gray-900')}>
          <div className="flex items-center gap-3">
            <UserAvatar
              src={report.employee_profile_picture}
              name={report.employee_name}
              email={report.employee_email}
            />
            <div className="min-w-0">
              <p className="truncate">{report.employee_name || report.employee_email}</p>
              <p className="truncate text-xs font-normal text-gray-500">{report.employee_email}</p>
            </div>
          </div>
        </td>
        <td className={tableBodyCellClass}>{report.department_name}</td>
        <td className={tableBodyCellClass}>{formatDate(report.month)}</td>
        <td className={cn(tableBodyCellClass, 'text-right font-semibold tabular-nums text-gray-900')}>
          {formatReportTotal(report)}
        </td>
        <td className={tableBodyCellClass}>
          <WorkflowStepper timeline={report.workflow_timeline ?? []} />
        </td>
        {renderRowActions && (
          <td className={tableBodyCellClass} onClick={(e) => e.stopPropagation()}>
            {rowActions}
          </td>
        )}
      </tr>
      {expanded && (
        <tr className="bg-gray-50/60">
          <td colSpan={columnCount} className="border-b border-[#e2e8f0] px-4 py-5">
            <div onClick={(e) => e.stopPropagation()}>{renderExpanded(report)}</div>
          </td>
        </tr>
      )}
    </>
  )
}
