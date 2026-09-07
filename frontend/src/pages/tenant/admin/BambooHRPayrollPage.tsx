import { Landmark, Plug, Plus } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  addPayrollBatchReport,
  createPayrollBatch,
  getPayrollEligibleReports,
  listPayrollBatches,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminDataTable, AdminTableCell, AdminTableRow } from '@/components/admin/AdminDataTable'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { AdminModalFooter } from '@/components/admin/AdminModalFooter'
import { StatusBadge } from '@/components/StatusBadge'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { AdminListPanelShimmer } from '@/components/ui/shimmer'
import { useAdminNav } from '@/hooks/useAdminNav'
import { fetchBambooHRConnected } from '@/lib/bambooHRConnection'
import { toast } from '@/lib/toast'
import { formatDate } from '@/lib/utils'
import type { PayrollBatch, PayrollEligibleReport } from '@/types'

const selectClassName =
  'flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm'

type Tab = 'eligible' | 'open' | 'history'

const OPEN_STATUSES = new Set(['DRAFT', 'READY', 'EXPORTED'])
const HISTORY_STATUSES = new Set(['CONFIRMED', 'CANCELLED'])

const emptyBatchForm = {
  payroll_period_start: '',
  payroll_period_end: '',
  pay_date: '',
  earning_code: 'EXPENSE_REIMBURSEMENT',
  notes: '',
}

export function BambooHRPayrollPage() {
  const navigate = useNavigate()
  const { navItems } = useAdminNav()

  const [tab, setTab] = useState<Tab>('eligible')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [eligible, setEligible] = useState<PayrollEligibleReport[]>([])
  const [batches, setBatches] = useState<PayrollBatch[]>([])
  const [bambooConnected, setBambooConnected] = useState<boolean | null>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [batchForm, setBatchForm] = useState(emptyBatchForm)
  const [pendingReport, setPendingReport] = useState<PayrollEligibleReport | null>(null)

  const [addTarget, setAddTarget] = useState<PayrollEligibleReport | null>(null)
  const [addBatchId, setAddBatchId] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const connected = await fetchBambooHRConnected()
      setBambooConnected(connected)
      if (!connected) return

      const [eligibleRes, batchesRes] = await Promise.all([
        getPayrollEligibleReports().catch(() => null),
        listPayrollBatches().catch(() => null),
      ])
      setEligible(eligibleRes?.data.results ?? [])
      setBatches(batchesRes?.data.results ?? [])
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const draftBatches = batches.filter((b) => b.status === 'DRAFT')
  const openBatches = batches.filter((b) => OPEN_STATUSES.has(b.status))
  const historyBatches = batches.filter((b) => HISTORY_STATUSES.has(b.status))

  const openAddDialog = (report: PayrollEligibleReport) => {
    setAddTarget(report)
    setAddBatchId(draftBatches[0]?.id ?? '')
    setError('')
  }

  const handleAddToExistingBatch = async () => {
    if (!addTarget || !addBatchId) return
    setSaving(true)
    setError('')
    try {
      await addPayrollBatchReport(addBatchId, addTarget.report_id)
      toast.success('Report added to the payroll batch.')
      setAddTarget(null)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const openCreateForReport = (report: PayrollEligibleReport | null) => {
    setPendingReport(report)
    setAddTarget(null)
    setBatchForm(emptyBatchForm)
    setError('')
    setCreateOpen(true)
  }

  const handleCreateBatch = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const { data } = await createPayrollBatch({
        payroll_period_start: batchForm.payroll_period_start,
        payroll_period_end: batchForm.payroll_period_end,
        pay_date: batchForm.pay_date,
        earning_code: batchForm.earning_code || 'EXPENSE_REIMBURSEMENT',
        notes: batchForm.notes || undefined,
      })
      const batchId = data.batch.id
      if (pendingReport) {
        await addPayrollBatchReport(batchId, pendingReport.report_id)
        toast.success('Batch created and report added.')
      } else {
        toast.success('Payroll batch created.')
      }
      setCreateOpen(false)
      navigate(`/admin/payroll/${batchId}`)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <DashboardLayout
        title="BambooHR Payroll"
        subtitle="Stage and confirm reimbursement payroll batches"
        breadcrumb="Payroll"
        icon={Landmark}
        navItems={navItems}
      >
        <AdminListPanelShimmer />
      </DashboardLayout>
    )
  }

  if (!bambooConnected) {
    return (
      <DashboardLayout
        title="BambooHR Payroll"
        subtitle="Stage approved reimbursements into Finance-controlled payroll batches"
        breadcrumb="Payroll"
        icon={Landmark}
        navItems={navItems}
      >
        <div className="flex flex-col items-center gap-4 rounded-lg border border-[#e2e8f0] bg-white px-6 py-16 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50">
            <Plug className="h-6 w-6 text-blue-600" />
          </div>
          <div className="space-y-1">
            <p className="text-base font-semibold text-gray-900">Connect BambooHR to use payroll</p>
            <p className="max-w-md text-sm text-gray-500">
              Payroll batches stage approved reimbursements for BambooHR Payroll. Connect BambooHR
              from Integrations before creating a batch.
            </p>
          </div>
          <Button asChild>
            <Link to="/admin/integrations">Go to Integrations</Link>
          </Button>
        </div>
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout
      title="BambooHR Payroll"
      subtitle="Stage approved reimbursements into Finance-controlled payroll batches"
      breadcrumb="Payroll"
      icon={Landmark}
      navItems={navItems}
      headerAction={
        <Button onClick={() => openCreateForReport(null)}>
          <Plus className="mr-1.5 h-4 w-4" />
          Create batch
        </Button>
      }
    >
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="mb-6 flex gap-2 border-b border-[#e2e8f0]">
        {(
          [
            { key: 'eligible', label: `Eligible reports (${eligible.length})` },
            { key: 'open', label: `Open batches (${openBatches.length})` },
            { key: 'history', label: `Confirmed history (${historyBatches.length})` },
          ] as { key: Tab; label: string }[]
        ).map((item) => (
          <button
            key={item.key}
            onClick={() => setTab(item.key)}
            className={`border-b-2 px-3 py-2 text-sm font-medium ${
              tab === item.key
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'eligible' && (
        <AdminListPanel
          title="Eligible reports"
          count={eligible.length}
          description="Approved reports awaiting payroll handling. Only mapped, not-yet-batched reports can be added."
        >
          {eligible.length === 0 ? (
            <p className="px-5 py-8 text-sm text-gray-400 sm:px-6">
              No approved reports are waiting for payroll handling.
            </p>
          ) : (
            <AdminDataTable columns={['Employee', 'Department', 'Month', 'Amount', 'Mapping', '']}>
              {eligible.map((report) => (
                <AdminTableRow key={report.report_id}>
                  <AdminTableCell className="font-medium text-gray-900">
                    <div>{report.employee.name}</div>
                    <div className="text-xs text-gray-400">{report.employee.email}</div>
                  </AdminTableCell>
                  <AdminTableCell>{report.department || '—'}</AdminTableCell>
                  <AdminTableCell className="text-gray-500">
                    {formatDate(report.month)}
                  </AdminTableCell>
                  <AdminTableCell>{report.total_amount}</AdminTableCell>
                  <AdminTableCell>
                    {report.bamboohr_mapping.mapped ? (
                      <StatusBadge status="ACTIVE" />
                    ) : (
                      <span className="text-xs text-amber-700">Not mapped</span>
                    )}
                  </AdminTableCell>
                  <AdminTableCell className="text-right">
                    {report.can_add ? (
                      <Button size="sm" onClick={() => openAddDialog(report)}>
                        Add to batch
                      </Button>
                    ) : report.already_in_payroll ? (
                      <span className="text-xs text-gray-400">Already in a batch</span>
                    ) : (
                      <span className="text-xs text-amber-700">
                        Sync or map this employee in BambooHR before adding to payroll.
                      </span>
                    )}
                  </AdminTableCell>
                </AdminTableRow>
              ))}
            </AdminDataTable>
          )}
        </AdminListPanel>
      )}

      {tab === 'open' && (
        <AdminListPanel
          title="Open batches"
          count={openBatches.length}
          description="Draft, ready, and exported payroll batches."
        >
          {openBatches.length === 0 ? (
            <p className="px-5 py-8 text-sm text-gray-400 sm:px-6">No open payroll batches.</p>
          ) : (
            <BatchTable batches={openBatches} onOpen={(id) => navigate(`/admin/payroll/${id}`)} />
          )}
        </AdminListPanel>
      )}

      {tab === 'history' && (
        <AdminListPanel
          title="Confirmed history"
          count={historyBatches.length}
          description="Confirmed payroll batches and their payroll run references."
        >
          {historyBatches.length === 0 ? (
            <p className="px-5 py-8 text-sm text-gray-400 sm:px-6">No confirmed batches yet.</p>
          ) : (
            <BatchTable batches={historyBatches} onOpen={(id) => navigate(`/admin/payroll/${id}`)} />
          )}
        </AdminListPanel>
      )}

      {/* Add report to an existing DRAFT batch */}
      <Dialog open={Boolean(addTarget)} onOpenChange={(open) => !open && setAddTarget(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add report to a payroll batch</DialogTitle>
          </DialogHeader>
          {draftBatches.length === 0 ? (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">
                There are no draft batches yet. Create one to add this report.
              </p>
              <AdminModalFooter
                onCancel={() => setAddTarget(null)}
                submitLabel="Create batch"
                submitType="button"
                onSubmit={() => openCreateForReport(addTarget)}
              />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Draft batch</Label>
                <select
                  className={selectClassName}
                  value={addBatchId}
                  onChange={(e) => setAddBatchId(e.target.value)}
                >
                  {draftBatches.map((batch) => (
                    <option key={batch.id} value={batch.id}>
                      {formatDate(batch.payroll_period_start)} – {formatDate(batch.payroll_period_end)}{' '}
                      ({batch.report_count} reports)
                    </option>
                  ))}
                </select>
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <AdminModalFooter
                onCancel={() => setAddTarget(null)}
                submitLabel="Add report"
                submitType="button"
                submitting={saving}
                onSubmit={() => void handleAddToExistingBatch()}
                extra={
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => openCreateForReport(addTarget)}
                  >
                    New batch instead
                  </Button>
                }
              />
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Create batch */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create payroll batch</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreateBatch} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Payroll period start</Label>
                <Input
                  type="date"
                  required
                  value={batchForm.payroll_period_start}
                  onChange={(e) =>
                    setBatchForm({ ...batchForm, payroll_period_start: e.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label>Payroll period end</Label>
                <Input
                  type="date"
                  required
                  value={batchForm.payroll_period_end}
                  onChange={(e) =>
                    setBatchForm({ ...batchForm, payroll_period_end: e.target.value })
                  }
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Pay date</Label>
              <Input
                type="date"
                required
                value={batchForm.pay_date}
                onChange={(e) => setBatchForm({ ...batchForm, pay_date: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Earning code</Label>
              <Input
                value={batchForm.earning_code}
                onChange={(e) => setBatchForm({ ...batchForm, earning_code: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Notes (optional)</Label>
              <Input
                value={batchForm.notes}
                onChange={(e) => setBatchForm({ ...batchForm, notes: e.target.value })}
              />
            </div>
            {pendingReport && (
              <p className="text-xs text-gray-500">
                {pendingReport.employee.name}&rsquo;s report will be added automatically once this
                batch is created.
              </p>
            )}
            {error && <p className="text-sm text-red-600">{error}</p>}
            <AdminModalFooter
              onCancel={() => setCreateOpen(false)}
              submitLabel="Create"
              submitting={saving}
            />
          </form>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  )
}

function BatchTable({
  batches,
  onOpen,
}: {
  batches: PayrollBatch[]
  onOpen: (id: string) => void
}) {
  return (
    <AdminDataTable
      columns={['Status', 'Period', 'Pay date', 'Reports', 'Total', 'Earning code', '']}
    >
      {batches.map((batch) => (
        <AdminTableRow key={batch.id}>
          <AdminTableCell>
            <StatusBadge status={batch.status} />
          </AdminTableCell>
          <AdminTableCell className="text-gray-500">
            {formatDate(batch.payroll_period_start)} – {formatDate(batch.payroll_period_end)}
          </AdminTableCell>
          <AdminTableCell className="text-gray-500">{formatDate(batch.pay_date)}</AdminTableCell>
          <AdminTableCell>{batch.report_count}</AdminTableCell>
          <AdminTableCell>{batch.total_amount}</AdminTableCell>
          <AdminTableCell className="text-gray-500">{batch.earning_code}</AdminTableCell>
          <AdminTableCell className="text-right">
            <Button size="sm" variant="outline" onClick={() => onOpen(batch.id)}>
              View
            </Button>
          </AdminTableCell>
        </AdminTableRow>
      ))}
    </AdminDataTable>
  )
}
