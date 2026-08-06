import { FileText, Send, Upload, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import {
  deleteLineItem,
  deleteReceipt,
  getCurrentMonthReport,
  getMyUploadedExpenses,
  retryReceiptAi,
  submitMonthlyReport,
  uploadReceipt,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { DashboardEmptyState } from '@/components/dashboard/DashboardEmptyState'
import { DashboardPanel } from '@/components/dashboard/DashboardPanel'
import { ExpenseReportTable } from '@/components/reports/ExpenseReportTable'
import { ExpenseProcessingPanel } from '@/components/reports/ExpenseProcessingPanel'
import { EmployeeReportSummary } from '@/components/reports/EmployeeReportSummary'
import { ReceiptExpenseCard } from '@/components/reports/ReceiptExpenseCard'
import { ReportFiltersBar } from '@/components/reports/ReportFiltersBar'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { useAuth } from '@/context/AuthContext'
import { defaultHomeForUser } from '@/lib/auth'
import {
  canManageOwnExpenses,
  canSubmitExpense,
  canUploadReceipt,
  expensePathForUser,
  navItemsForUser,
} from '@/lib/rolePermissions'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { TableShimmer } from '@/components/ui/shimmer'
import type { ExpenseReport } from '@/types'
import { countPendingAiReceipts } from '@/lib/receiptAi'
import { fireImportConfetti } from '@/lib/confetti'
import {
  mergeServerReportIntoReports,
  normalizeCurrentMonthReport,
} from '@/lib/expenseReport'
import {
  hasEmployeeExpenseFilters,
  toEmployeeExpenseApiParams,
  type EmployeeExpenseFilters,
} from '@/lib/reportFilters'
import { toast } from '@/lib/toast'
import UploadIcon from '@/assets/upload.png'

function formatUploadError(message: string) {
  if (message.includes('company role is not assigned')) {
    return 'Your account has no company role assigned. Ask your company admin to open Employees → Assign default roles, or edit your user and set a company role.'
  }
  if (message.includes('not allowed to upload receipts')) {
    return 'Your company role does not allow receipt uploads. Ask your admin to assign a role with upload permission (e.g. Employee).'
  }
  if (message.includes('generativelanguage.googleapis.com') || message.includes('Gemini API')) {
    return 'Gemini API is not enabled for your API key. Create a key at Google AI Studio or enable the Generative Language API in Cloud Console, then try again.'
  }
  return message
}

function MyExpenseExpandedPanel({
  report,
  canEditReceipts,
  onDeleteLineItem,
  onDeleteReceipt,
  onRetryReceipt,
  retryingReceiptId,
  deletingReceiptId,
}: {
  report: ExpenseReport
  canEditReceipts: boolean
  onDeleteLineItem: (lineItemId: string) => void
  onDeleteReceipt: (receiptId: string) => void
  onRetryReceipt: (receiptId: string) => void
  retryingReceiptId: string | null
  deletingReceiptId: string | null
}) {
  return (
    <div className="space-y-4">
      <EmployeeReportSummary report={report} />

      {!report.receipts.length ? (
        <p className="rounded-xl border border-dashed border-[#e2e8f0] bg-white px-5 py-8 text-center text-sm text-muted-foreground">
          No receipts uploaded yet. Use Upload receipt to add expenses.
        </p>
      ) : (
        <div className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
            Receipts in this claim
          </p>
          {report.receipts.map((receipt) => (
            <ReceiptExpenseCard
              key={receipt.id}
              receipt={receipt}
              canEdit={canEditReceipts}
              onDeleteLineItem={onDeleteLineItem}
              onDeleteReceipt={onDeleteReceipt}
              onRetryReceipt={onRetryReceipt}
              retrying={retryingReceiptId === receipt.id}
              deleting={deletingReceiptId === receipt.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function ExpensesPage() {
  const { user } = useAuth()
  const location = useLocation()
  const navItems = navItemsForUser(user)
  const allowUpload = canUploadReceipt(user)
  const allowSubmit = canSubmitExpense(user)
  const expensePath = expensePathForUser(user)

  const [reports, setReports] = useState<ExpenseReport[]>([])
  const [loading, setLoading] = useState(true)
  const [backgroundUploads, setBackgroundUploads] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [retryingReceiptId, setRetryingReceiptId] = useState<string | null>(null)
  const [deletingReceiptId, setDeletingReceiptId] = useState<string | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [draftFilters, setDraftFilters] = useState<EmployeeExpenseFilters>({})
  const [appliedFilters, setAppliedFilters] = useState<EmployeeExpenseFilters>({})
  const fileRef = useRef<HTMLInputElement>(null)
  const hadPendingAiRef = useRef(false)

  const filtersActive = hasEmployeeExpenseFilters(appliedFilters)
  const pendingAiCount = useMemo(() => countPendingAiReceipts(reports), [reports])
  const isProcessingInBackground = backgroundUploads > 0 || pendingAiCount > 0

  const resetUploadModal = () => {
    setSelectedFiles([])
    setDragOver(false)
    if (fileRef.current) fileRef.current.value = ''
  }

  const handleFileSelect = (files: FileList | null) => {
    if (!files?.length) return
    setSelectedFiles(Array.from(files))
  }

  const removeSelectedFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index))
    if (fileRef.current) fileRef.current.value = ''
  }

  const load = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) setLoading(true)
    try {
      if (filtersActive) {
        const { data } = await getMyUploadedExpenses(toEmployeeExpenseApiParams(appliedFilters))
        setReports(
          data.results.map((report) => ({
            ...report,
            employee_email: report.employee_email || user?.email || '',
          })),
        )
        return
      }

      const { data } = await getCurrentMonthReport()
      setReports((prev) => mergeServerReportIntoReports(prev, data, user?.email))
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 404) {
        return
      }
      if (!options?.silent) {
        toast.error(getApiErrorMessage(err))
      }
    } finally {
      if (!options?.silent) setLoading(false)
    }
  }, [appliedFilters, filtersActive, user?.email])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (pendingAiCount > 0) {
      hadPendingAiRef.current = true
      return
    }

    if (hadPendingAiRef.current && reports.some((report) => (report.receipts?.length ?? 0) > 0)) {
      hadPendingAiRef.current = false
      toast.success('AI extraction finished for your receipt(s).')
    }
  }, [pendingAiCount, reports])

  useEffect(() => {
    if (pendingAiCount === 0 && backgroundUploads === 0) return

    const intervalId = window.setInterval(() => {
      void load({ silent: true })
    }, 3000)

    return () => window.clearInterval(intervalId)
  }, [pendingAiCount, backgroundUploads, load])

  const runBackgroundUploads = async (files: File[]) => {
    setBackgroundUploads((count) => count + files.length)

    try {
      let reportId =
        reports.find((report) => report.status === 'DRAFT')?.id || reports[0]?.id || ''

      if (!reportId) {
        try {
          const { data: current } = await getCurrentMonthReport()
          const normalized = normalizeCurrentMonthReport(current)
          reportId = normalized.id
          if (reportId) {
            setReports((prev) => mergeServerReportIntoReports(prev, current, user?.email))
          }
        } catch {
          // First upload of the month — backend creates the draft report.
        }
      }

      const { data } = await uploadReceipt(files, reportId || undefined)
      toast.success(
        data.message ||
          (files.length === 1
            ? 'Receipt uploaded. AI is extracting details in the background.'
            : `${files.length} receipts uploaded. AI is extracting details in the background.`),
      )
      void load({ silent: true })
    } catch (err) {
      toast.error(formatUploadError(getApiErrorMessage(err)))
    } finally {
      setBackgroundUploads((count) => Math.max(0, count - files.length))
    }
  }

  const handleConfirmUpload = () => {
    if (!selectedFiles.length) return

    const files = [...selectedFiles]
    setUploadOpen(false)
    resetUploadModal()
    void runBackgroundUploads(files)
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      const { data } = await submitMonthlyReport()
      if (data.auto_approved) {
        fireImportConfetti()
        toast.success(data.message || 'Monthly report approved automatically.')
        if (data.next_action) {
          toast(data.next_action)
        }
      } else {
        toast.success(data.message || 'Monthly report submitted for approval.')
        const step = data.current_approval_step
        if (step) {
          const dept =
            step.routing_type === 'DEPARTMENT' && step.department
              ? ` (${step.department})`
              : ''
          toast(`Awaiting ${step.approver_role}${dept} — step ${step.step_order}`)
        }
      }
      if (data.report) {
        const normalized = normalizeCurrentMonthReport(data.report)
        setReports([
          {
            ...normalized,
            employee_email: normalized.employee_email || user?.email || '',
          },
        ])
      } else {
        await load()
      }
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const handleRetryReceipt = async (receiptId: string) => {
    setRetryingReceiptId(receiptId)
    try {
      const { data } = await retryReceiptAi(receiptId)
      if (data.ai_result?.success === false) {
        const message = data.ai_result.error || 'AI extraction failed. Try a clearer receipt.'
        if (data.ai_result.retry_allowed) {
          toast.error(message)
        } else {
          toast.error(`${message} Upload a clearer receipt to try again.`)
        }
      } else {
        toast.success(data.message || 'AI extraction completed.')
      }
      await load()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setRetryingReceiptId(null)
    }
  }

  const handleDeleteLineItem = async (lineItemId: string) => {
    try {
      await deleteLineItem(lineItemId)
      await load()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    }
  }

  const handleDeleteReceipt = async (receiptId: string) => {
    const confirmed = window.confirm(
      'Delete this receipt from your draft claim? This cannot be undone.',
    )
    if (!confirmed) return

    setDeletingReceiptId(receiptId)
    try {
      const { data } = await deleteReceipt(receiptId)
      toast.success(data.message || 'Receipt deleted successfully.')
      await load()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setDeletingReceiptId(null)
    }
  }

  if (!canManageOwnExpenses(user)) {
    return <Navigate to={defaultHomeForUser(user!)} replace />
  }

  if (location.pathname !== expensePath) {
    return <Navigate to={expensePath} replace />
  }

  if (loading) {
    return (
      <DashboardLayout title="My Expenses" subtitle="Upload receipts for this month" navItems={navItems}>
        <TableShimmer rows={3} />
      </DashboardLayout>
    )
  }

  const displayReports = reports
  const draftReport = displayReports.find((report) => report.status === 'DRAFT')
  const canSubmitDraft =
    allowSubmit &&
    !!draftReport &&
    (draftReport.receipts?.length ?? 0) > 0 &&
    !filtersActive &&
    pendingAiCount === 0 &&
    backgroundUploads === 0
  const showProcessingOnly = !displayReports.length && isProcessingInBackground
  const expandReportId = draftReport?.id ?? displayReports[0]?.id ?? null

  return (
    <DashboardLayout title="My Expenses" subtitle="Upload receipts for this month" navItems={navItems}>
      <ReportFiltersBar
        mode="employee"
        values={draftFilters}
        onChange={setDraftFilters}
        onApply={() => setAppliedFilters(draftFilters)}
        onClear={() => {
          setDraftFilters({})
          setAppliedFilters({})
        }}
        disabled={submitting}
      />

      <div className="mb-4 flex flex-wrap items-center justify-end gap-2">
        {isProcessingInBackground && (
          <p className="text-sm text-muted-foreground">
            {backgroundUploads > 0
              ? `Uploading ${backgroundUploads} receipt${backgroundUploads === 1 ? '' : 's'}…`
              : `Processing ${pendingAiCount} receipt${pendingAiCount === 1 ? '' : 's'} with AI…`}
          </p>
        )}
        {canSubmitDraft && (
          <Button variant="success" disabled={submitting} onClick={handleSubmit}>
            <Send className="h-4 w-4" />
            {submitting ? 'Submitting...' : 'Submit report'}
          </Button>
        )}
        {allowUpload && (
          <Button
            onClick={() => {
              resetUploadModal()
              setUploadOpen(true)
            }}
          >
            Upload receipt
            <img src={UploadIcon} alt="Upload" className="w-6 h-6" />
          </Button>
        )}
      </div>

      {!displayReports.length ? (
        showProcessingOnly ? (
          <ExpenseProcessingPanel
            uploadingCount={backgroundUploads}
            processingCount={pendingAiCount}
          />
        ) : (
          <DashboardPanel title="My expenses">
            <DashboardEmptyState
              image="folder"
              title={filtersActive ? 'No matching reports' : 'No expense report yet'}
              description={
                filtersActive
                  ? 'Try adjusting your filters or clear them to view the current month report.'
                  : 'Upload a receipt to start your monthly expense report.'
              }
              onRefresh={() => void load()}
              action={
                !filtersActive && allowUpload ? (
                  <Button
                    onClick={() => {
                      resetUploadModal()
                      setUploadOpen(true)
                    }}
                  >
                    Upload receipt
                    <img src={UploadIcon} alt="Upload" className="w-6 h-6" />
                  </Button>
                ) : undefined
              }
            />
          </DashboardPanel>
        )
      ) : (
        <ExpenseReportTable
          reports={displayReports}
          defaultExpandedId={expandReportId}
          renderExpanded={(expandedReport) => {
            const isDraftReport = expandedReport.status === 'DRAFT'
            const canEditReceipts = allowSubmit && isDraftReport

            return (
              <MyExpenseExpandedPanel
                report={expandedReport}
                canEditReceipts={canEditReceipts}
                onDeleteLineItem={handleDeleteLineItem}
                onDeleteReceipt={handleDeleteReceipt}
                onRetryReceipt={handleRetryReceipt}
                retryingReceiptId={retryingReceiptId}
                deletingReceiptId={deletingReceiptId}
              />
            )
          }}
        />
      )}

      <Dialog
        open={uploadOpen}
        onOpenChange={(open) => {
          setUploadOpen(open)
          if (!open) resetUploadModal()
        }}
      >
        <DialogContent className="flex max-h-[min(90vh,640px)] w-[calc(100vw-2rem)] max-w-md flex-col overflow-hidden p-6 sm:max-w-lg">
          <DialogHeader className="shrink-0">
            <DialogTitle>Upload Receipt</DialogTitle>
          </DialogHeader>

          <div className="min-h-0 min-w-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden pr-1">
            <div
              className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
                dragOver
                  ? 'border-primary bg-blue-50'
                  : 'border-gray-300 bg-gray-50 hover:border-primary/50'
              }`}
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                handleFileSelect(e.dataTransfer.files)
              }}
              onKeyDown={(e) => e.key === 'Enter' && fileRef.current?.click()}
              role="button"
              tabIndex={0}
            >
              <Upload className="h-8 w-8 text-muted-foreground" />
              <p className="mt-2 text-sm font-medium">Click or drag files here</p>
              <p className="mt-1 text-xs text-muted-foreground">PNG, JPG, or PDF</p>
            </div>

            <input
              ref={fileRef}
              type="file"
              accept="image/*,.pdf"
              multiple
              className="hidden"
              onChange={(e) => handleFileSelect(e.target.files)}
            />

            {selectedFiles.length > 0 && (
              <ul className="space-y-2">
                {selectedFiles.map((file, index) => (
                  <li key={`${file.name}-${index}`} className="flex items-center gap-2 text-sm">
                    <FileText className="h-4 w-4 shrink-0 text-red-500" />
                    <span className="min-w-0 flex-1 truncate text-gray-700" title={file.name}>
                      {file.name}
                    </span>
                    <button
                      type="button"
                      className="shrink-0 rounded p-0.5 text-red-500 hover:bg-red-50"
                      onClick={() => removeSelectedFile(index)}
                      aria-label={`Remove ${file.name}`}
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <DialogFooter className="mt-2 shrink-0 gap-2 border-t border-gray-100 pt-4 sm:justify-end">
            <Button
              type="button"
              variant="outline"
              onClick={() => setUploadOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={selectedFiles.length === 0}
              onClick={handleConfirmUpload}
            >
              {`Upload${selectedFiles.length > 1 ? ` (${selectedFiles.length})` : ''}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  )
}
