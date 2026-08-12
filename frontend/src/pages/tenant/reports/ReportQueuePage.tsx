import { useCallback, useEffect, useState } from 'react'
import { approveReport, accountsMarkPaid, listDepartments, listEmployees, rejectReport } from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { showReportActionToast } from '@/lib/reportActions'
import { toast } from '@/lib/toast'
import { DashboardEmptyState } from '@/components/dashboard/DashboardEmptyState'
import { DashboardPanel } from '@/components/dashboard/DashboardPanel'
import { ReportFiltersBar } from '@/components/reports/ReportFiltersBar'
import { ReportQueueHelp } from '@/components/reports/ReportQueueHelp'
import { ReportQueueTable } from '@/components/reports/ReportQueueTable'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { AdminListPanelShimmer } from '@/components/ui/shimmer'
import { useAuth } from '@/context/AuthContext'
import { fetchAllPages } from '@/lib/pagination'
import type { ApprovalReportFilters } from '@/lib/reportFilters'
import {
  loadApprovedQueueReports,
  loadPendingQueueReports,
  type QueuedReport,
} from '@/lib/reportQueue'
import { canApproveExpense, canMarkPaid, navItemsForUser } from '@/lib/rolePermissions'
import type { DepartmentRecord, EmployeeRecord } from '@/types'

interface ReportQueuePageProps {
  mode: 'pending' | 'approved'
}

export function ReportQueuePage({ mode }: ReportQueuePageProps) {
  const { user } = useAuth()
  const navItems = navItemsForUser(user)
  const canApprove = canApproveExpense(user)
  const canPay = canMarkPaid(user)
  const [items, setItems] = useState<QueuedReport[]>([])
  const [loading, setLoading] = useState(true)
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [actionId, setActionId] = useState<string | null>(null)
  const [departments, setDepartments] = useState<DepartmentRecord[]>([])
  const [employees, setEmployees] = useState<EmployeeRecord[]>([])
  const [draftFilters, setDraftFilters] = useState<ApprovalReportFilters>({})
  const [appliedFilters, setAppliedFilters] = useState<ApprovalReportFilters>({})

  useEffect(() => {
    Promise.all([
      fetchAllPages((page) => listDepartments({ page })),
      fetchAllPages((page) => listEmployees({ page })),
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
      const data =
        mode === 'pending'
          ? await loadPendingQueueReports({
              canApprove,
              canMarkPaid: canPay,
              filters: appliedFilters,
            })
          : await loadApprovedQueueReports({
              canApprove,
              canMarkPaid: canPay,
              filters: appliedFilters,
            })
      setItems(data)
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [mode, canApprove, canPay, appliedFilters])

  useEffect(() => {
    load()
  }, [load])

  const handleApprove = async (reportId: string) => {
    setActionId(reportId)
    try {
      const { data } = await approveReport(reportId, notes[reportId] || 'Approved')
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
        notes[reportId] || 'Payment completed successfully',
      )
      showReportActionToast(data, 'paid')
      await load()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setActionId(null)
    }
  }

  const title = mode === 'pending' ? 'Pending Reports' : 'Approved Reports'
  const subtitle =
    mode === 'pending'
      ? 'Reports that need your action'
      : 'Reports you have already processed'

  if (loading && items.length === 0) {
    return (
      <DashboardLayout
        title={title}
        subtitle={subtitle}
        breadcrumb={title}
        navItems={navItems}
      >
        <AdminListPanelShimmer />
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout
      title={title}
      subtitle={subtitle}
      breadcrumb={title}
      navItems={navItems}
    >
      <ReportQueueHelp mode={mode} user={user} />

      <ReportFiltersBar
        mode="approval"
        values={draftFilters}
        onChange={setDraftFilters}
        departments={departments}
        employees={employees}
        onApply={() => setAppliedFilters(draftFilters)}
        onClear={() => {
          setDraftFilters({})
          setAppliedFilters({})
        }}
        disabled={actionId !== null}
      />

      {items.length === 0 ? (
        <DashboardPanel title={title}>
          <DashboardEmptyState
            image="folder"
            title={mode === 'pending' ? 'No pending reports' : 'No approved reports yet'}
            description={
              mode === 'pending'
                ? 'Reports waiting for your approval or payment action will appear here.'
                : 'Reports you have approved or marked as paid will appear here.'
            }
            onRefresh={load}
          />
        </DashboardPanel>
      ) : (
        <ReportQueueTable
          items={items}
          actionId={actionId}
          notes={notes}
          onNotesChange={(reportId, value) =>
            setNotes((current) => ({ ...current, [reportId]: value }))
          }
          onApprove={canApprove ? handleApprove : undefined}
          onReject={canApprove ? handleReject : undefined}
          onMarkPaid={canPay ? handleMarkPaid : undefined}
          onRefresh={load}
          showAdminOverride={user?.role === 'COMPANY_ADMIN'}
        />
      )}
    </DashboardLayout>
  )
}
