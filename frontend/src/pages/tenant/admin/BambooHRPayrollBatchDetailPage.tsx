import axios from 'axios'
import { ArrowLeft, Download, Landmark, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  addPayrollBatchReport,
  confirmPayrollBatch,
  downloadPayrollBatchCsv,
  getPayrollBatch,
  getPayrollEligibleReports,
  markPayrollBatchReady,
  removePayrollBatchReport,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminConfirmDialog } from '@/components/admin/AdminConfirmDialog'
import { AdminDataTable, AdminTableCell, AdminTableRow } from '@/components/admin/AdminDataTable'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { AdminModalFooter } from '@/components/admin/AdminModalFooter'
import { StatusBadge } from '@/components/StatusBadge'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PageLoader } from '@/components/ui/shimmer'
import { useAdminNav } from '@/hooks/useAdminNav'
import { toast } from '@/lib/toast'
import { formatDate, formatDateTime, formatCurrency } from '@/lib/utils'
import type { PayrollBatch, PayrollEligibleReport } from '@/types'

export function BambooHRPayrollBatchDetailPage() {
  const { batchId } = useParams<{ batchId: string }>()
  const navigate = useNavigate()
  const { navItems } = useAdminNav()

  const [batch, setBatch] = useState<PayrollBatch | null>(null)
  const [eligible, setEligible] = useState<PayrollEligibleReport[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const [addOpen, setAddOpen] = useState(false)
  const [removeTarget, setRemoveTarget] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmForm, setConfirmForm] = useState({ payroll_run_reference: '', notes: '' })

  const load = useCallback(async () => {
    if (!batchId) return
    setLoading(true)
    setError('')
    try {
      const { data } = await getPayrollBatch(batchId)
      setBatch(data.batch)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [batchId])

  useEffect(() => {
    void load()
  }, [load])

  const handleStaleState = useCallback(
    async (err: unknown) => {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        toast.error('This batch changed since it was loaded. Refreshing…')
        await load()
        return true
      }
      return false
    },
    [load],
  )

  const openAddDialog = async () => {
    setError('')
    setAddOpen(true)
    try {
      const { data } = await getPayrollEligibleReports()
      setEligible(data.results.filter((report) => report.can_add))
    } catch (err) {
      setError(getApiErrorMessage(err))
    }
  }

  const handleAddReport = async (reportId: string) => {
    if (!batchId) return
    setSaving(true)
    setError('')
    try {
      await addPayrollBatchReport(batchId, reportId)
      toast.success('Report added to the payroll batch.')
      setEligible((current) => current.filter((r) => r.report_id !== reportId))
      await load()
    } catch (err) {
      if (!(await handleStaleState(err))) {
        setError(getApiErrorMessage(err))
      }
    } finally {
      setSaving(false)
    }
  }

  const handleRemoveReport = async () => {
    if (!batchId || !removeTarget) return
    setSaving(true)
    setError('')
    try {
      await removePayrollBatchReport(batchId, removeTarget)
      toast.success('Report removed from the batch.')
      setRemoveTarget(null)
      await load()
    } catch (err) {
      if (!(await handleStaleState(err))) {
        setError(getApiErrorMessage(err))
      }
    } finally {
      setSaving(false)
    }
  }

  const handleMarkReady = async () => {
    if (!batchId) return
    setSaving(true)
    setError('')
    try {
      await markPayrollBatchReady(batchId)
      toast.success('Batch is ready for CSV export.')
      await load()
    } catch (err) {
      if (!(await handleStaleState(err))) {
        setError(getApiErrorMessage(err))
      }
    } finally {
      setSaving(false)
    }
  }

  const handleDownloadCsv = async () => {
    if (!batchId) return
    setSaving(true)
    setError('')
    try {
      await downloadPayrollBatchCsv(batchId)
      toast.success('CSV downloaded. The batch moved to EXPORTED.')
      await load()
    } catch (err) {
      if (!(await handleStaleState(err))) {
        setError(getApiErrorMessage(err))
      }
    } finally {
      setSaving(false)
    }
  }

  const handleConfirm = async (e: FormEvent) => {
    e.preventDefault()
    if (!batchId) return
    setSaving(true)
    setError('')
    try {
      await confirmPayrollBatch(batchId, {
        payroll_run_reference: confirmForm.payroll_run_reference,
        notes: confirmForm.notes || undefined,
      })
      toast.success('Payroll batch confirmed. Reports were marked PAID.')
      setConfirmOpen(false)
      await load()
    } catch (err) {
      if (!(await handleStaleState(err))) {
        setError(getApiErrorMessage(err))
      }
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <DashboardLayout
        title="Payroll batch"
        subtitle="Loading batch detail"
        breadcrumb="Payroll"
        icon={Landmark}
        navItems={navItems}
      >
        <PageLoader />
      </DashboardLayout>
    )
  }

  if (!batch) {
    return (
      <DashboardLayout
        title="Payroll batch"
        subtitle="Batch not found"
        breadcrumb="Payroll"
        icon={Landmark}
        navItems={navItems}
      >
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          {error || 'This payroll batch could not be found.'}
        </div>
        <Button className="mt-4" variant="outline" onClick={() => navigate('/admin/payroll')}>
          <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
          Back to payroll
        </Button>
      </DashboardLayout>
    )
  }

  const items = batch.items ?? []

  return (
    <DashboardLayout
      title={`Payroll batch — ${formatDate(batch.payroll_period_start)} to ${formatDate(batch.payroll_period_end)}`}
      subtitle={`Pay date ${formatDate(batch.pay_date)} · ${batch.earning_code}`}
      breadcrumb="Payroll"
      icon={Landmark}
      navItems={navItems}
      headerAction={
        <Button variant="outline" onClick={() => navigate('/admin/payroll')}>
          <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
          Back to payroll
        </Button>
      }
    >
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="mb-8 rounded-lg border border-[#e2e8f0] bg-white px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-500">Status</p>
              <div className="mt-1">
                <StatusBadge status={batch.status} />
              </div>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-500">Reports</p>
              <p className="mt-1 text-sm font-medium text-gray-900">{batch.report_count}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-500">Total amount</p>
              <p className="mt-1 text-sm font-medium text-gray-900">{batch.total_amount}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-500">Payroll run reference</p>
              <p className="mt-1 text-sm font-medium text-gray-900">
                {batch.payroll_run_reference || '—'}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {batch.status === 'DRAFT' && (
              <>
                <Button variant="outline" disabled={saving} onClick={() => void openAddDialog()}>
                  <Plus className="mr-1.5 h-3.5 w-3.5" />
                  Add report
                </Button>
                <Button disabled={saving || items.length === 0} onClick={() => void handleMarkReady()}>
                  Mark ready
                </Button>
              </>
            )}
            {batch.status === 'READY' && (
              <Button disabled={saving} onClick={() => void handleDownloadCsv()}>
                <Download className="mr-1.5 h-3.5 w-3.5" />
                Download CSV
              </Button>
            )}
            {batch.status === 'EXPORTED' && (
              <>
                <Button variant="outline" disabled={saving} onClick={() => void handleDownloadCsv()}>
                  <Download className="mr-1.5 h-3.5 w-3.5" />
                  Re-download CSV
                </Button>
                <Button
                  disabled={saving}
                  onClick={() => {
                    setConfirmForm({ payroll_run_reference: '', notes: '' })
                    setError('')
                    setConfirmOpen(true)
                  }}
                >
                  Confirm payroll processing
                </Button>
              </>
            )}
          </div>
        </div>

        {batch.notes && <p className="mt-4 text-sm text-gray-500">Notes: {batch.notes}</p>}

        <div className="mt-4 flex flex-wrap gap-x-8 gap-y-1 border-t border-[#e2e8f0] pt-4 text-xs text-gray-400">
          <span>Created {formatDateTime(batch.created_at)}</span>
          <span>Exported {formatDateTime(batch.exported_at)}</span>
          <span>Confirmed {formatDateTime(batch.confirmed_at)}</span>
        </div>
      </div>

      <AdminListPanel
        title="Batch items"
        count={items.length}
        description="Employees and amounts staged in this payroll batch."
      >
        {items.length === 0 ? (
          <p className="px-5 py-8 text-sm text-gray-400 sm:px-6">No reports in this batch yet.</p>
        ) : (
          <AdminDataTable
            columns={[
              'Employee',
              'BambooHR employee ID',
              'Report ID',
              'Amount',
              'Status',
              'Error',
              '',
            ]}
          >
            {items.map((item) => (
              <AdminTableRow key={item.id}>
                <AdminTableCell className="font-medium text-gray-900">
                  <div>{item.employee_name}</div>
                  <div className="text-xs text-gray-400">{item.external_email}</div>
                </AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {item.external_employee_id || '—'}
                </AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  <span className="font-mono text-xs">{item.report_id}</span>
                </AdminTableCell>
                <AdminTableCell>{formatCurrency(item.amount, item.currency)}</AdminTableCell>
                <AdminTableCell>
                  <StatusBadge status={item.status} />
                </AdminTableCell>
                <AdminTableCell className="text-red-600">{item.error_message || ''}</AdminTableCell>
                <AdminTableCell className="text-right">
                  {batch.status === 'DRAFT' && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={saving}
                      onClick={() => setRemoveTarget(item.report_id)}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-red-500" />
                    </Button>
                  )}
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </AdminDataTable>
        )}
      </AdminListPanel>

      {/* Add report */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add an approved report</DialogTitle>
          </DialogHeader>
          {eligible.length === 0 ? (
            <p className="text-sm text-gray-500">
              No mapped, unbatched approved reports are available right now.
            </p>
          ) : (
            <div className="max-h-96 space-y-2 overflow-y-auto">
              {eligible.map((report) => (
                <div
                  key={report.report_id}
                  className="flex items-center justify-between rounded-md border border-[#e2e8f0] px-3 py-2"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-900">{report.employee.name}</p>
                    <p className="text-xs text-gray-500">
                      {report.department || '—'} · {formatDate(report.month)} ·{' '}
                      {report.total_amount}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    disabled={saving}
                    onClick={() => void handleAddReport(report.report_id)}
                  >
                    Add
                  </Button>
                </div>
              ))}
            </div>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
        </DialogContent>
      </Dialog>

      <AdminConfirmDialog
        open={Boolean(removeTarget)}
        onOpenChange={(open) => !open && setRemoveTarget(null)}
        title="Remove report from batch?"
        description="This report will be removed from the draft batch and can be added to a different batch."
        confirmLabel="Remove"
        loading={saving}
        onConfirm={() => void handleRemoveReport()}
      />

      {/* Confirm payroll processing */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm BambooHR payroll processing</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleConfirm} className="space-y-4">
            <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
              This action marks every report in this batch PAID and cannot be repeated.
            </p>
            <div className="grid grid-cols-2 gap-3 text-sm text-gray-600">
              <span>Reports: {batch.report_count}</span>
              <span>Total: {batch.total_amount}</span>
              <span>Pay date: {formatDate(batch.pay_date)}</span>
              <span>Earning code: {batch.earning_code}</span>
            </div>
            <div className="space-y-2">
              <Label>Payroll run / reference</Label>
              <Input
                required
                value={confirmForm.payroll_run_reference}
                onChange={(e) =>
                  setConfirmForm({ ...confirmForm, payroll_run_reference: e.target.value })
                }
                placeholder="e.g. BHR-PAYROLL-2026-09-001"
              />
            </div>
            <div className="space-y-2">
              <Label>Finance notes (optional)</Label>
              <Input
                value={confirmForm.notes}
                onChange={(e) => setConfirmForm({ ...confirmForm, notes: e.target.value })}
              />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <AdminModalFooter
              onCancel={() => setConfirmOpen(false)}
              submitLabel="Confirm and mark paid"
              submitting={saving}
            />
          </form>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  )
}
