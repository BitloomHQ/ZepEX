import { Banknote, Check, ClipboardList, Copy, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  accountsMarkPaid,
  approveReport,
  getAdminReports,
  getDuplicateReceipts,
  listDepartments,
  listEmployees,
  rejectReport,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import {
  tableBodyCellClass,
  tableGridClass,
  tableHeadCellClass,
  tableHeadRowClass,
} from '@/lib/tableStyles'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { DashboardEmptyState } from '@/components/dashboard/DashboardEmptyState'
import { ReportDetail } from '@/components/ReportDetail'
import { ExpenseReportTable } from '@/components/reports/ExpenseReportTable'
import { ReportFiltersBar } from '@/components/reports/ReportFiltersBar'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { Button } from '@/components/ui/button'
import { FilterTogglePanel } from '@/components/ui/FilterTogglePanel'
import { Label } from '@/components/ui/label'
import { PaginationControls } from '@/components/ui/pagination-controls'
import { Textarea } from '@/components/ui/textarea'
import { TabbedTablePageShimmer } from '@/components/ui/shimmer'
import { useAdminNav } from '@/hooks/useAdminNav'
import { showReportActionToast } from '@/lib/reportActions'
import { createReportApprovalContext } from '@/lib/reportApprovalHandlers'
import { fetchAllPages } from '@/lib/pagination'
import { toAdminApiParams, type AdminReportFilters } from '@/lib/reportFilters'
import { toast } from '@/lib/toast'
import { formatDate } from '@/lib/utils'
import { cn } from '@/lib/utils'
import type { DepartmentRecord, DuplicateReceiptLog, EmployeeRecord, ExpenseReport } from '@/types'

const STATUS_TABS = [
  { label: 'Pending', value: 'SUBMITTED' },
  { label: 'Approved', value: 'APPROVED' },
  { label: 'Rejected', value: 'REJECTED' },
  { label: 'Paid', value: 'PAID' },
] as const

const DUPLICATES_TAB = 'DUPLICATES'

const selectClassName =
  'flex h-10 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

const DUPLICATE_TYPE_OPTIONS = [
  { label: 'All types', value: '' },
  { label: 'Same employee', value: 'SAME_EMPLOYEE' },
  { label: 'Cross employee', value: 'CROSS_EMPLOYEE' },
] as const

function AdminReportExpandedPanel({
  report,
  status,
  notes,
  actionId,
  onNotesChange,
  onApprove,
  onReject,
  onMarkPaid,
  onRefresh,
}: {
  report: ExpenseReport
  status: string
  notes: string
  actionId: string | null
  onNotesChange: (value: string) => void
  onApprove: (reportId: string) => void
  onReject: (reportId: string) => void
  onMarkPaid: (reportId: string) => void
  onRefresh: () => Promise<void>
}) {
  const showActions = status === 'SUBMITTED' || status === 'APPROVED'
  const employeeLabel = report.employee_name || report.employee_email
  const approvalContext =
    status === 'SUBMITTED'
      ? createReportApprovalContext(report.id, {
          enabled: true,
          busy: actionId === report.id,
          onRefresh,
        })
      : undefined

  return (
    <div className="space-y-4">
      {showActions && (
        <div className="space-y-3 rounded-lg border border-[#e2e8f0] bg-white px-4 py-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-medium text-gray-900">{employeeLabel}</p>
          </div>
          <Textarea
            placeholder={
              status === 'SUBMITTED'
                ? 'Notes (required for rejection)'
                : 'Payment notes (optional)'
            }
            value={notes}
            onChange={(e) => onNotesChange(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            {status === 'SUBMITTED' && (
              <>
                <Button
                  variant="success"
                  disabled={actionId === report.id}
                  onClick={() => onApprove(report.id)}
                >
                  <Check className="h-4 w-4" />
                  Approve
                </Button>
                <Button
                  variant="destructive"
                  disabled={actionId === report.id}
                  onClick={() => onReject(report.id)}
                >
                  <X className="h-4 w-4" />
                  Reject
                </Button>
              </>
            )}
            {status === 'APPROVED' && (
              <Button
                disabled={actionId === report.id}
                onClick={() => onMarkPaid(report.id)}
              >
                <Banknote className="h-4 w-4" />
                Mark as paid
              </Button>
            )}
          </div>
        </div>
      )}
      <ReportDetail
        report={report}
        showEmployee={false}
        showAdminOverride
        approvalContext={approvalContext}
      />
    </div>
  )
}

function DuplicatesTable({ duplicates }: { duplicates: DuplicateReceiptLog[] }) {
  if (!duplicates.length) {
    return (
      <DashboardEmptyState
        image="folder"
        title="No duplicate receipts"
        description="Duplicate receipt detections will appear here when the system flags matching uploads."
      />
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className={cn(tableGridClass, 'min-w-[720px] text-left')}>
        <thead>
          <tr className={tableHeadRowClass}>
            <th className={tableHeadCellClass}>Type</th>
            <th className={tableHeadCellClass}>Original</th>
            <th className={tableHeadCellClass}>Duplicate</th>
            <th className={tableHeadCellClass}>Detected</th>
          </tr>
        </thead>
        <tbody>
          {duplicates.map((entry) => (
            <tr key={entry.id}>
              <td className={cn(tableBodyCellClass, 'capitalize')}>
                {entry.duplicate_type.replace(/_/g, ' ').toLowerCase()}
              </td>
              <td className={tableBodyCellClass}>
                <p className="font-medium">{entry.original_vendor || 'Unknown vendor'}</p>
                <p className="text-muted-foreground">{entry.original_employee_email}</p>
              </td>
              <td className={tableBodyCellClass}>
                <p className="font-medium">{entry.duplicate_vendor || 'Unknown vendor'}</p>
                <p className="text-muted-foreground">{entry.duplicate_employee_email}</p>
              </td>
              <td className={cn(tableBodyCellClass, 'text-muted-foreground')}>
                {formatDate(entry.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AdminReportsPage() {
  const { navItems } = useAdminNav()
  const [reports, setReports] = useState<ExpenseReport[]>([])
  const [duplicates, setDuplicates] = useState<DuplicateReceiptLog[]>([])
  const [status, setStatus] = useState<string>('SUBMITTED')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [duplicateCount, setDuplicateCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [actionId, setActionId] = useState<string | null>(null)
  const [departments, setDepartments] = useState<DepartmentRecord[]>([])
  const [employees, setEmployees] = useState<EmployeeRecord[]>([])
  const [draftFilters, setDraftFilters] = useState<AdminReportFilters>({})
  const [appliedFilters, setAppliedFilters] = useState<AdminReportFilters>({})
  const [duplicateType, setDuplicateType] = useState('')
  const [appliedDuplicateType, setAppliedDuplicateType] = useState('')

  const isDuplicatesView = status === DUPLICATES_TAB

  useEffect(() => {
    Promise.all([
      fetchAllPages((p) => listDepartments({ page: p })),
      fetchAllPages((p) => listEmployees({ page: p })),
    ])
      .then(([deptData, employeeData]) => {
        setDepartments(deptData)
        setEmployees(employeeData)
      })
      .catch(() => {
        setDepartments([])
        setEmployees([])
      })
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      if (isDuplicatesView) {
        const { data } = await getDuplicateReceipts(
          appliedDuplicateType ? { type: appliedDuplicateType } : undefined,
        )
        setDuplicates(data.results)
        setDuplicateCount(data.count)
        return
      }

      const { data } = await getAdminReports({
        status,
        ...toAdminApiParams(appliedFilters, page),
      })
      setReports(data.results)
      setTotalPages(data.total_pages)
      setTotalCount(data.count)
    } catch (err) {
      toast.error(getApiErrorMessage(err))
      setReports([])
      setDuplicates([])
    } finally {
      setLoading(false)
    }
  }, [appliedDuplicateType, appliedFilters, isDuplicatesView, page, status])

  useEffect(() => {
    load()
  }, [load])

  const handleApprove = async (reportId: string) => {
    setActionId(reportId)
    try {
      const { data } = await approveReport(reportId, notes[reportId] || 'Approved by company admin.')
      showReportActionToast(data, 'approve')
      await load()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setActionId(null)
    }
  }

  const handleReject = async (reportId: string) => {
    const reason = notes[reportId]?.trim()
    if (!reason) {
      toast.error('Rejection reason is required.')
      return
    }
    setActionId(reportId)
    try {
      const { data } = await rejectReport(reportId, reason)
      showReportActionToast(data, 'reject')
      await load()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setActionId(null)
    }
  }

  const handleMarkPaid = async (reportId: string) => {
    setActionId(reportId)
    try {
      const { data } = await accountsMarkPaid(
        reportId,
        notes[reportId] || 'Paid by company admin.',
      )
      showReportActionToast(data, 'paid')
      await load()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setActionId(null)
    }
  }

  const applyFilters = () => {
    if (isDuplicatesView) {
      setAppliedDuplicateType(duplicateType)
      return
    }
    setAppliedFilters(draftFilters)
    setPage(1)
  }

  const clearFilters = () => {
    if (isDuplicatesView) {
      setDuplicateType('')
      setAppliedDuplicateType('')
      return
    }
    setDraftFilters({})
    setAppliedFilters({})
    setPage(1)
  }

  if (loading && reports.length === 0 && duplicates.length === 0) {
    return (
      <DashboardLayout
        title="Company Reports"
        subtitle="Monitor and act on expense reports across your company"
        breadcrumb="Reports"
        icon={ClipboardList}
        navItems={navItems}
      >
        <TabbedTablePageShimmer />
      </DashboardLayout>
    )
  }

  const activeTabLabel = isDuplicatesView
    ? 'Duplicates'
    : STATUS_TABS.find((tab) => tab.value === status)?.label ?? 'Reports'

  return (
    <DashboardLayout
      title="Company Reports"
      subtitle="Monitor and act on expense reports across your company"
      breadcrumb="Reports"
      icon={ClipboardList}
      navItems={navItems}
    >
      <div className="mb-4 flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => (
          <Button
            key={tab.value}
            size="sm"
            variant={status === tab.value ? 'default' : 'outline'}
            onClick={() => {
              setStatus(tab.value)
              setPage(1)
            }}
          >
            {tab.label}
          </Button>
        ))}
        <Button
          size="sm"
          variant={isDuplicatesView ? 'default' : 'outline'}
          onClick={() => {
            setStatus(DUPLICATES_TAB)
            setPage(1)
          }}
        >
          <Copy className="h-4 w-4" />
          Duplicates
        </Button>
      </div>

      {isDuplicatesView ? (
        <FilterTogglePanel>
          <div className="rounded-xl border bg-card p-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1.5">
                <Label htmlFor="duplicate-type">Duplicate type</Label>
                <select
                  id="duplicate-type"
                  className={selectClassName}
                  value={duplicateType}
                  onChange={(e) => setDuplicateType(e.target.value)}
                >
                  {DUPLICATE_TYPE_OPTIONS.map((option) => (
                    <option key={option.value || 'all'} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button size="sm" onClick={applyFilters}>
                Apply filters
              </Button>
              <Button size="sm" variant="outline" onClick={clearFilters}>
                Clear
              </Button>
            </div>
          </div>
        </FilterTogglePanel>
      ) : (
        <ReportFiltersBar
          mode="admin"
          values={draftFilters}
          onChange={setDraftFilters}
          departments={departments}
          employees={employees}
          onApply={applyFilters}
          onClear={clearFilters}
          disabled={actionId !== null}
        />
      )}

      <AdminListPanel
        title={activeTabLabel}
        count={isDuplicatesView ? duplicateCount : totalCount}
        description={
          isDuplicatesView
            ? 'Receipts flagged as potential duplicates across your company.'
            : 'Click a row to view full report details. Company admins can approve, reject, or mark reports as paid.'
        }
      >
        {isDuplicatesView ? (
          <div className="p-4 sm:p-6">
            <DuplicatesTable duplicates={duplicates} />
          </div>
        ) : reports.length === 0 ? (
          <DashboardEmptyState
            image="folder"
            title="No reports in this view"
            description="Try another status filter or check back when employees submit expenses."
            onRefresh={load}
          />
        ) : (
          <div className="p-4 sm:p-6">
            <ExpenseReportTable
              reports={reports}
              renderRowActions={(report) => {
                if (status === 'SUBMITTED') {
                  return (
                    <div className="flex flex-wrap gap-1.5">
                      <Button
                        size="sm"
                        variant="success"
                        disabled={actionId === report.id}
                        onClick={() => handleApprove(report.id)}
                      >
                        <Check className="h-3.5 w-3.5" />
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={actionId === report.id}
                        onClick={() => handleReject(report.id)}
                      >
                        <X className="h-3.5 w-3.5" />
                        Reject
                      </Button>
                    </div>
                  )
                }

                if (status === 'APPROVED') {
                  return (
                    <Button
                      size="sm"
                      disabled={actionId === report.id}
                      onClick={() => handleMarkPaid(report.id)}
                    >
                      <Banknote className="h-3.5 w-3.5" />
                      Mark paid
                    </Button>
                  )
                }

                return null
              }}
              renderExpanded={(report) => (
                <AdminReportExpandedPanel
                  report={report}
                  status={status}
                  notes={notes[report.id] || ''}
                  actionId={actionId}
                  onNotesChange={(value) =>
                    setNotes((current) => ({ ...current, [report.id]: value }))
                  }
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onMarkPaid={handleMarkPaid}
                  onRefresh={load}
                />
              )}
            />
          </div>
        )}
        {!isDuplicatesView && (
          <PaginationControls
            currentPage={page}
            totalPages={totalPages}
            totalCount={totalCount}
            onPageChange={setPage}
            disabled={actionId !== null}
          />
        )}
      </AdminListPanel>
    </DashboardLayout>
  )
}
