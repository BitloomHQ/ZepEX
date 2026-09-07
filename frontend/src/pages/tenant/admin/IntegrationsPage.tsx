import {
  AlertTriangle,
  ArrowRight,
  Briefcase,
  Building2,
  Plug,
  Plus,
  Receipt,
  RefreshCw,
  Sprout,
  Trash2,
  Users,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  connectBambooHR,
  connectQuickBooks,
  deleteQuickBooksCategoryMapping,
  disconnectQuickBooks,
  exportReportToQuickBooks,
  getAdminReports,
  getBambooHRChangeHistory,
  getBambooHRHealth,
  getBambooHRStatus,
  getBambooHRSyncHistory,
  getIntegrationActivity,
  getIntegrationDashboard,
  getQuickBooksAccounts,
  getQuickBooksCategoryMappings,
  getQuickBooksExportHistory,
  getQuickBooksExportStatus,
  getQuickBooksHealth,
  getQuickBooksPaymentAccounts,
  getQuickBooksSettings,
  getQuickBooksStatus,
  listIntegrationProviders,
  listPolicyRules,
  previewBambooHREmployees,
  reconcileQuickBooksReport,
  retryQuickBooksExport,
  saveQuickBooksCategoryMapping,
  saveQuickBooksPaymentAccount,
  syncBambooHRAll,
  syncBambooHRDepartments,
  syncBambooHREmployees,
  syncBambooHRManagers,
  updateQuickBooksAutoExport,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminConfirmDialog } from '@/components/admin/AdminConfirmDialog'
import { AdminDataTable, AdminTableCell, AdminTableRow } from '@/components/admin/AdminDataTable'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { AdminModalFooter } from '@/components/admin/AdminModalFooter'
import { StatusBadge } from '@/components/StatusBadge'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { AdminListPanelShimmer } from '@/components/ui/shimmer'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAuth } from '@/context/AuthContext'
import { useAdminNav } from '@/hooks/useAdminNav'
import { hasPermission } from '@/lib/rolePermissions'
import { fetchAllPages } from '@/lib/pagination'
import { toast } from '@/lib/toast'
import { cn } from '@/lib/utils'
import { formatDateTime } from '@/lib/utils'
import type {
  BambooHRChangeHistoryItem,
  BambooHREmployeePreview,
  BambooHRHealthResponse,
  BambooHRStatusResponse,
  BambooHRSyncHistoryItem,
  ExpenseReport,
  IntegrationActivityItem,
  IntegrationDashboardSummary,
  IntegrationProviderCatalogItem,
  QuickBooksAccount,
  QuickBooksCategoryMapping,
  QuickBooksExportHistoryItem,
  QuickBooksHealthResponse,
  QuickBooksReconcileResponse,
  QuickBooksSettingsResponse,
  QuickBooksStatusResponse,
} from '@/types'

const selectClassName =
  'flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm'

type BambooResource = 'ALL' | 'DEPARTMENTS' | 'EMPLOYEES' | 'MANAGERS'

const BAMBOO_RESOURCE_LABEL: Record<BambooResource, string> = {
  ALL: 'Full sync',
  DEPARTMENTS: 'Departments',
  EMPLOYEES: 'Employees',
  MANAGERS: 'Managers',
}

const COMING_SOON_ICON: Record<string, LucideIcon> = {
  RIPPLING: Users,
  WORKDAY: Building2,
  ADP: Briefcase,
}

interface IntegrationRowProps {
  icon: LucideIcon
  iconClassName: string
  name: string
  description: string
  status: 'connected' | 'not_connected' | 'coming_soon'
  canManage: boolean
  actionLabel?: string
  actionDisabled?: boolean
  onAction?: () => void
}

function IntegrationRow({
  icon: Icon,
  iconClassName,
  name,
  description,
  status,
  canManage,
  actionLabel = 'Connect',
  actionDisabled,
  onAction,
}: IntegrationRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-4 sm:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div
          className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
            iconClassName,
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-gray-900">{name}</p>
          <p className="truncate text-sm text-gray-500">{description}</p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {status === 'coming_soon' ? (
          <Badge variant="muted">Coming soon</Badge>
        ) : status === 'connected' ? (
          <Badge variant="success">Connected</Badge>
        ) : canManage ? (
          <Button size="sm" disabled={actionDisabled} onClick={onAction}>
            {actionLabel}
          </Button>
        ) : (
          <span className="text-xs text-gray-400">Not connected</span>
        )}
      </div>
    </div>
  )
}

function CatalogList({ children }: { children: ReactNode }) {
  return (
    <div className="divide-y divide-[#e2e8f0] overflow-hidden rounded-lg border border-[#e2e8f0] bg-white">
      {children}
    </div>
  )
}

export function IntegrationsPage() {
  const { user } = useAuth()
  const { navItems } = useAdminNav()
  const [searchParams, setSearchParams] = useSearchParams()
  const canManage =
    user?.role === 'COMPANY_ADMIN' || hasPermission(user, 'can_manage_integrations')
  const isCompanyAdmin = user?.role === 'COMPANY_ADMIN'

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [providers, setProviders] = useState<IntegrationProviderCatalogItem[]>([])
  const [dashboard, setDashboard] = useState<IntegrationDashboardSummary | null>(null)
  const [activity, setActivity] = useState<IntegrationActivityItem[]>([])
  const [addIntegrationOpen, setAddIntegrationOpen] = useState(false)

  // QuickBooks
  const [status, setStatus] = useState<QuickBooksStatusResponse | null>(null)
  const [qbHealth, setQbHealth] = useState<QuickBooksHealthResponse | null>(null)
  const [qbSettings, setQbSettings] = useState<QuickBooksSettingsResponse | null>(null)
  const [accounts, setAccounts] = useState<QuickBooksAccount[]>([])
  const [mappings, setMappings] = useState<QuickBooksCategoryMapping[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [paymentAccounts, setPaymentAccounts] = useState<QuickBooksAccount[]>([])
  const [selectedPaymentAccountId, setSelectedPaymentAccountId] = useState('')
  const [exports, setExports] = useState<QuickBooksExportHistoryItem[]>([])
  const [disconnectOpen, setDisconnectOpen] = useState(false)
  const [mappingForm, setMappingForm] = useState({
    zepex_category: '',
    quickbooks_account_id: '',
  })
  const [pollingReportId, setPollingReportId] = useState<string | null>(null)
  const [reconcileResults, setReconcileResults] = useState<
    Record<string, QuickBooksReconcileResponse>
  >({})
  const [reconcilingReportId, setReconcilingReportId] = useState<string | null>(null)
  const [unexportedReports, setUnexportedReports] = useState<ExpenseReport[]>([])

  // BambooHR
  const [bambooStatus, setBambooStatus] = useState<BambooHRStatusResponse | null>(null)
  const [bambooHealth, setBambooHealth] = useState<BambooHRHealthResponse | null>(null)
  const [bambooSyncHistory, setBambooSyncHistory] = useState<BambooHRSyncHistoryItem[]>([])
  const [bambooChangeHistory, setBambooChangeHistory] = useState<BambooHRChangeHistoryItem[]>([])
  const [bambooDomain, setBambooDomain] = useState('')
  const [bambooSyncing, setBambooSyncing] = useState<BambooResource | null>(null)
  const [bambooConnectOpen, setBambooConnectOpen] = useState(false)
  const [bambooPreviewOpen, setBambooPreviewOpen] = useState(false)
  const [bambooPreviewLoading, setBambooPreviewLoading] = useState(false)
  const [bambooPreviewEmployees, setBambooPreviewEmployees] = useState<BambooHREmployeePreview[]>(
    [],
  )

  const [bambooDetailsLoading, setBambooDetailsLoading] = useState(false)
  const [qbDetailsLoading, setQbDetailsLoading] = useState(false)

  const connected = Boolean(status?.connected)
  const bambooConnected = Boolean(bambooStatus?.connected)
  const comingSoon = useMemo(
    () => providers.filter((item) => item.provider !== 'QUICKBOOKS' && item.provider !== 'BAMBOOHR'),
    [providers],
  )

  // Core connection status only — fast, local DB reads. This is the only
  // fetch allowed to gate the full-page loading state, so a slow secondary
  // call (health checks hit the real provider API) can never blank the page.
  const fetchCore = useCallback(async () => {
    setError('')
    const [catalogResult, statusResult, bambooStatusResult] = await Promise.allSettled([
      listIntegrationProviders(),
      getQuickBooksStatus(),
      getBambooHRStatus(),
    ])

    if (catalogResult.status === 'fulfilled') {
      setProviders(catalogResult.value.data.providers ?? [])
    } else {
      setProviders([])
      setError(getApiErrorMessage(catalogResult.reason))
    }

    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value.data)
    } else {
      setStatus({ success: false, provider: 'QUICKBOOKS', connected: false })
      setError((current) => current || getApiErrorMessage(statusResult.reason))
    }

    if (bambooStatusResult.status === 'fulfilled') {
      setBambooStatus(bambooStatusResult.value.data)
    } else {
      setBambooStatus(null)
    }

    return {
      qbConnected: statusResult.status === 'fulfilled' && Boolean(statusResult.value.data.connected),
      bambooConnected:
        bambooStatusResult.status === 'fulfilled' &&
        Boolean(bambooStatusResult.value.data.connected),
    }
  }, [])

  const fetchOverview = useCallback(async () => {
    const [dashboardRes, activityRes] = await Promise.all([
      getIntegrationDashboard().catch(() => null),
      getIntegrationActivity({ limit: 10 }).catch(() => null),
    ])
    setDashboard(dashboardRes?.data ?? null)
    setActivity(activityRes?.data.results ?? [])
  }, [])

  const fetchBambooDetails = useCallback(async () => {
    setBambooDetailsLoading(true)
    try {
      const [healthRes, historyRes, changesRes] = await Promise.all([
        getBambooHRHealth().catch(() => null),
        getBambooHRSyncHistory({ limit: 10 }).catch(() => null),
        getBambooHRChangeHistory({ limit: 10 }).catch(() => null),
      ])
      setBambooHealth(healthRes?.data ?? null)
      setBambooSyncHistory(historyRes?.data.results ?? [])
      setBambooChangeHistory(changesRes?.data.results ?? [])
    } finally {
      setBambooDetailsLoading(false)
    }
  }, [])

  const fetchQuickBooksDetails = useCallback(async () => {
    setQbDetailsLoading(true)
    try {
      const [
        accountsRes,
        mappingsRes,
        paymentRes,
        historyRes,
        policyRules,
        healthRes,
        settingsRes,
        paidReportsRes,
      ] = await Promise.all([
        getQuickBooksAccounts().catch(() => null),
        getQuickBooksCategoryMappings().catch(() => null),
        getQuickBooksPaymentAccounts().catch(() => null),
        getQuickBooksExportHistory().catch(() => null),
        fetchAllPages((page) => listPolicyRules({ page })).catch(() => []),
        getQuickBooksHealth().catch(() => null),
        getQuickBooksSettings().catch(() => null),
        getAdminReports({ status: 'PAID' }).catch(() => null),
      ])

      setAccounts(accountsRes?.data.accounts ?? [])
      setMappings(mappingsRes?.data.mappings ?? [])
      setPaymentAccounts(paymentRes?.data.accounts ?? [])
      setSelectedPaymentAccountId(paymentRes?.data.selected_account?.id ?? '')
      const exportedReports = historyRes?.data.results ?? []
      setExports(exportedReports)
      setCategories(
        [...new Set(policyRules.map((rule) => rule.category_name).filter(Boolean))].sort(),
      )
      setQbHealth(healthRes?.data ?? null)
      setQbSettings(settingsRes?.data ?? null)

      const exportedReportIds = new Set(exportedReports.map((item) => item.report.id))
      setUnexportedReports(
        (paidReportsRes?.data.results ?? []).filter((report) => !exportedReportIds.has(report.id)),
      )
    } finally {
      setQbDetailsLoading(false)
    }
  }, [])

  // Full refresh used after a mutation (connect/disconnect/save/etc). Never
  // toggles the page-level `loading` flag, so the already-rendered page stays
  // in place while sections update in place.
  const refreshAll = useCallback(async () => {
    const { qbConnected, bambooConnected: bambooIsConnected } = await fetchCore()
    await Promise.all([
      fetchOverview(),
      bambooIsConnected
        ? fetchBambooDetails()
        : Promise.resolve().then(() => {
            setBambooHealth(null)
            setBambooSyncHistory([])
            setBambooChangeHistory([])
          }),
      qbConnected
        ? fetchQuickBooksDetails()
        : Promise.resolve().then(() => {
            setAccounts([])
            setMappings([])
            setPaymentAccounts([])
            setSelectedPaymentAccountId('')
            setExports([])
            setQbHealth(null)
            setQbSettings(null)
            setUnexportedReports([])
          }),
    ])
  }, [fetchCore, fetchOverview, fetchBambooDetails, fetchQuickBooksDetails])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchCore()
      .then(({ qbConnected, bambooConnected: bambooIsConnected }) => {
        if (cancelled) return
        if (bambooIsConnected) void fetchBambooDetails()
        if (qbConnected) void fetchQuickBooksDetails()
      })
      .catch((err) => setError(getApiErrorMessage(err)))
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    void fetchOverview()
    return () => {
      cancelled = true
    }
  }, [fetchCore, fetchOverview, fetchBambooDetails, fetchQuickBooksDetails])

  useEffect(() => {
    const result = searchParams.get('quickbooks')
    if (!result) return
    if (result === 'connected') {
      toast.success('QuickBooks connected successfully.')
    } else {
      toast.error(searchParams.get('quickbooks_error') || 'QuickBooks connection failed.')
    }
    searchParams.delete('quickbooks')
    searchParams.delete('quickbooks_error')
    setSearchParams(searchParams, { replace: true })
    void refreshAll()
  }, [refreshAll, searchParams, setSearchParams])

  const handleConnect = async () => {
    setSaving(true)
    setError('')
    try {
      const { data } = await connectQuickBooks()
      if (!data.authorization_url) {
        throw new Error('QuickBooks did not return an authorization URL.')
      }
      window.location.assign(data.authorization_url)
    } catch (err) {
      setError(getApiErrorMessage(err))
      setSaving(false)
    }
  }

  const handleDisconnect = async () => {
    setSaving(true)
    setError('')
    try {
      const { data } = await disconnectQuickBooks()
      toast.success(data.message || 'QuickBooks disconnected.')
      setDisconnectOpen(false)
      await refreshAll()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveMapping = async () => {
    if (!mappingForm.zepex_category || !mappingForm.quickbooks_account_id) {
      setError('Choose a ZepEX category and a QuickBooks expense account.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const { data } = await saveQuickBooksCategoryMapping(mappingForm)
      toast.success(data.message || 'Category mapping saved.')
      setMappingForm({ zepex_category: '', quickbooks_account_id: '' })
      await refreshAll()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteMapping = async (mappingId: number) => {
    setSaving(true)
    setError('')
    try {
      const { data } = await deleteQuickBooksCategoryMapping(mappingId)
      toast.success(data.message || 'Mapping removed.')
      await refreshAll()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleSavePaymentAccount = async () => {
    if (!selectedPaymentAccountId) {
      setError('Choose a QuickBooks payment account.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const { data } = await saveQuickBooksPaymentAccount(selectedPaymentAccountId)
      toast.success(data.message || 'Payment account saved.')
      await refreshAll()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const pollExportStatus = useCallback(async (reportId: string) => {
    setPollingReportId(reportId)
    const start = Date.now()
    while (Date.now() - start < 60_000) {
      await new Promise((resolve) => setTimeout(resolve, 2_000))
      try {
        const { data } = await getQuickBooksExportStatus(reportId)
        if (data.export_status === 'SUCCESS' || data.export_status === 'FAILED') {
          break
        }
      } catch {
        break
      }
    }
    setPollingReportId(null)
    await refreshAll()
  }, [refreshAll])

  const handleRetryExport = async (reportId: string) => {
    setSaving(true)
    setError('')
    try {
      const { data } = await retryQuickBooksExport(reportId)
      toast.success(data.message || 'Export retry queued.')
      void pollExportStatus(reportId)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleReconcile = async (reportId: string) => {
    setReconcilingReportId(reportId)
    setError('')
    try {
      const { data } = await reconcileQuickBooksReport(reportId)
      setReconcileResults((current) => ({ ...current, [reportId]: data }))
      if (data.reconciliation_status === 'VERIFIED') {
        toast.success('Reconciliation verified — no mismatches.')
      } else {
        toast.error(`Reconciliation status: ${data.reconciliation_status}`)
      }
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setReconcilingReportId(null)
    }
  }

  const handleToggleAutoExport = async () => {
    if (!qbSettings) return
    setSaving(true)
    setError('')
    try {
      const { data } = await updateQuickBooksAutoExport(!qbSettings.quickbooks.auto_export)
      toast.success(data.message || 'QuickBooks automatic export updated.')
      await refreshAll()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleConnectBambooHR = async () => {
    if (!bambooDomain.trim()) {
      setError('Enter your BambooHR company domain.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const { data } = await connectBambooHR(bambooDomain.trim())
      if (!data.authorization_url) {
        throw new Error('BambooHR did not return an authorization URL.')
      }
      window.location.assign(data.authorization_url)
    } catch (err) {
      setError(getApiErrorMessage(err))
      setSaving(false)
    }
  }

  const handleSyncBambooHR = async (resource: BambooResource) => {
    setBambooSyncing(resource)
    setError('')
    try {
      const syncFn =
        resource === 'ALL'
          ? syncBambooHRAll
          : resource === 'DEPARTMENTS'
            ? syncBambooHRDepartments
            : resource === 'EMPLOYEES'
              ? syncBambooHREmployees
              : syncBambooHRManagers
      const { data } = await syncFn()
      const { received, created, updated, skipped } = data.records
      toast.success(
        `${BAMBOO_RESOURCE_LABEL[resource]} sync complete: ${received} received, ${created} created, ${updated} updated, ${skipped} skipped.`,
      )
      if (data.errors.length > 0) {
        toast.error(`${data.errors.length} record(s) had errors during sync. See sync history for details.`)
      }
      await refreshAll()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setBambooSyncing(null)
    }
  }

  const openBambooConnect = () => {
    setError('')
    setAddIntegrationOpen(false)
    setBambooConnectOpen(true)
  }

  const openBambooPreview = async () => {
    setBambooPreviewOpen(true)
    if (bambooPreviewEmployees.length > 0) return
    setBambooPreviewLoading(true)
    setError('')
    try {
      const { data } = await previewBambooHREmployees()
      setBambooPreviewEmployees(data.employees)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setBambooPreviewLoading(false)
    }
  }

  const handleExportReport = async (reportId: string) => {
    setSaving(true)
    setError('')
    try {
      const { data } = await exportReportToQuickBooks(reportId)
      toast.success(data.message || 'QuickBooks export queued.')
      void pollExportStatus(reportId)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <DashboardLayout
        title="Third-party integrations"
        subtitle="Connect accounting and HR tools"
        breadcrumb="Integrations"
        icon={Plug}
        navItems={navItems}
      >
        <AdminListPanelShimmer />
      </DashboardLayout>
    )
  }

  const bambooOverallStatus = bambooHealth?.overall_status
  const qbOverallStatus = qbHealth?.overall_status

  const bambooRow = (
    <IntegrationRow
      key="bamboohr"
      icon={Sprout}
      iconClassName="bg-emerald-50 text-emerald-600"
      name="BambooHR"
      description="Sync employees, departments, and managers; stage payroll batches."
      status={bambooConnected ? 'connected' : 'not_connected'}
      canManage={canManage}
      actionDisabled={saving}
      onAction={openBambooConnect}
    />
  )

  const quickBooksRow = (
    <IntegrationRow
      key="quickbooks"
      icon={Receipt}
      iconClassName="bg-blue-50 text-blue-600"
      name="QuickBooks"
      description="Export paid expense reports to QuickBooks as purchases."
      status={connected ? 'connected' : 'not_connected'}
      canManage={canManage}
      actionDisabled={saving}
      onAction={() => void handleConnect()}
    />
  )

  const comingSoonRows = comingSoon.map((provider) => (
    <IntegrationRow
      key={provider.provider}
      icon={COMING_SOON_ICON[provider.provider] ?? Plug}
      iconClassName="bg-gray-100 text-gray-500"
      name={provider.provider_name}
      description="This connector will be enabled as it ships."
      status="coming_soon"
      canManage={canManage}
    />
  ))

  const addableRows = [
    !bambooConnected && bambooRow,
    !connected && quickBooksRow,
    ...comingSoonRows,
  ].filter(Boolean) as ReactNode[]

  const bambooPanelContent = (
    <div className="space-y-8">
      <AdminListPanel
        title="BambooHR"
        description="Sync employees, departments, and managers, then stage payroll reimbursement batches."
      >
        <div className="space-y-5 px-5 py-5 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-gray-900">Connected</p>
                {bambooOverallStatus && <StatusBadge status={bambooOverallStatus} />}
              </div>
              <p className="mt-1 text-sm text-gray-500">
                {bambooDetailsLoading
                  ? 'Checking connection health…'
                  : bambooOverallStatus && bambooOverallStatus !== 'HEALTHY'
                    ? bambooHealth?.connection.error ||
                      bambooHealth?.issues?.[0]?.message ||
                      'BambooHR needs attention.'
                    : 'Connection is healthy. Run a sync to pull the latest employee data.'}
              </p>
            </div>
            {canManage && (
              <div className="flex gap-2">
                <Button variant="outline" disabled={saving} onClick={() => void openBambooPreview()}>
                  Preview employees
                </Button>
                <Button variant="outline" disabled={saving} onClick={() => void refreshAll()}>
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                  Refresh
                </Button>
              </div>
            )}
          </div>

          {canManage && (
            <div className="flex flex-wrap gap-2 border-t border-[#e2e8f0] pt-4">
              {(['ALL', 'DEPARTMENTS', 'EMPLOYEES', 'MANAGERS'] as BambooResource[]).map(
                (resource) => (
                  <Button
                    key={resource}
                    size="sm"
                    variant={resource === 'ALL' ? 'default' : 'outline'}
                    disabled={Boolean(bambooSyncing)}
                    onClick={() => void handleSyncBambooHR(resource)}
                  >
                    <RefreshCw
                      className={`mr-1.5 h-3.5 w-3.5 ${bambooSyncing === resource ? 'animate-spin' : ''}`}
                    />
                    {bambooSyncing === resource ? 'Syncing…' : `Sync ${BAMBOO_RESOURCE_LABEL[resource]}`}
                  </Button>
                ),
              )}
            </div>
          )}

          <div className="border-t border-[#e2e8f0] pt-4">
            <Link
              to="/admin/payroll"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:underline"
            >
              Manage BambooHR payroll batches
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </AdminListPanel>

      {bambooSyncHistory.length > 0 && (
        <AdminListPanel
          title="Sync history"
          count={bambooSyncHistory.length}
          description="Most recent synchronization runs."
        >
          <AdminDataTable columns={['Resource', 'Trigger', 'Status', 'Received/Created/Updated/Skipped', 'Started', '']}>
            {bambooSyncHistory.map((entry) => (
              <AdminTableRow key={entry.id}>
                <AdminTableCell className="font-medium text-gray-900">
                  {entry.resource ?? entry.stats?.resource ?? '—'}
                </AdminTableCell>
                <AdminTableCell className="text-gray-500">{entry.trigger}</AdminTableCell>
                <AdminTableCell>
                  <StatusBadge status={entry.status} />
                </AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {entry.records_received}/{entry.records_created}/{entry.records_updated}/
                  {entry.records_skipped}
                </AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {formatDateTime(entry.started_at)}
                </AdminTableCell>
                <AdminTableCell className="text-red-600">{entry.error_message || ''}</AdminTableCell>
              </AdminTableRow>
            ))}
          </AdminDataTable>
        </AdminListPanel>
      )}

      {bambooChangeHistory.length > 0 && (
        <AdminListPanel
          title="Change history"
          count={bambooChangeHistory.length}
          description="Recent field-level changes synced from BambooHR."
        >
          <AdminDataTable columns={['Type', 'Record', 'Change', 'Field', 'Old → new', 'When']}>
            {bambooChangeHistory.map((change) => (
              <AdminTableRow key={change.id}>
                <AdminTableCell className="text-gray-500">{change.resource_type}</AdminTableCell>
                <AdminTableCell className="font-medium text-gray-900">
                  {change.resource_name}
                </AdminTableCell>
                <AdminTableCell>
                  <StatusBadge status={change.change_type} />
                </AdminTableCell>
                <AdminTableCell className="text-gray-500">{change.field_name || '—'}</AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {change.field_name
                    ? `${change.old_value ?? '—'} → ${change.new_value ?? '—'}`
                    : '—'}
                </AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {formatDateTime(change.created_at)}
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </AdminDataTable>
        </AdminListPanel>
      )}
    </div>
  )

  const quickBooksPanelContent = (
    <div className="space-y-8">
      <AdminListPanel
        title="QuickBooks"
        description="Export paid expense reports to QuickBooks as purchases."
      >
        <div className="space-y-5 px-5 py-5 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-gray-900">
                  {status?.company?.name || 'Connected'}
                </p>
                {qbOverallStatus && <StatusBadge status={qbOverallStatus} />}
              </div>
              <p className="mt-1 text-sm text-gray-500">
                {status?.healthy === false
                  ? status?.error || 'Connected, but QuickBooks is not responding.'
                  : 'Connection is healthy. Map categories before exporting reports.'}
              </p>
            </div>
            {canManage && (
              <Button variant="outline" disabled={saving} onClick={() => setDisconnectOpen(true)}>
                Disconnect
              </Button>
            )}
          </div>

          {qbSettings && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#e2e8f0] pt-4">
              <div>
                <p className="text-sm font-medium text-gray-900">Automatic export</p>
                <p className="mt-1 text-sm text-gray-500">
                  {qbSettings.quickbooks.auto_export
                    ? 'Paid reports export to QuickBooks automatically.'
                    : 'Paid reports must be exported manually or retried below.'}
                </p>
              </div>
              {isCompanyAdmin && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={saving}
                  onClick={() => void handleToggleAutoExport()}
                >
                  {qbSettings.quickbooks.auto_export ? 'Disable' : 'Enable'} auto-export
                </Button>
              )}
            </div>
          )}

          {qbHealth && qbHealth.issues.length > 0 && (
            <div className="flex items-start gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{qbHealth.issues.map((issue) => issue.message).join(' ')}</span>
            </div>
          )}
        </div>
      </AdminListPanel>

      <AdminListPanel
        title="Category mappings"
        count={mappings.length}
        description="Map each ZepEX expense category to a QuickBooks expense account."
      >
        {canManage && (
          <div className="grid gap-3 border-b border-[#e2e8f0] px-5 py-4 sm:grid-cols-[1fr_1fr_auto] sm:px-6">
            <select
              className={selectClassName}
              value={mappingForm.zepex_category}
              onChange={(e) =>
                setMappingForm((current) => ({ ...current, zepex_category: e.target.value }))
              }
            >
              <option value="">ZepEX category</option>
              {categories.map((category) => (
                <option key={category} value={category.toLowerCase()}>
                  {category}
                </option>
              ))}
            </select>
            <select
              className={selectClassName}
              value={mappingForm.quickbooks_account_id}
              onChange={(e) =>
                setMappingForm((current) => ({
                  ...current,
                  quickbooks_account_id: e.target.value,
                }))
              }
            >
              <option value="">QuickBooks account</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
            <Button disabled={saving} onClick={() => void handleSaveMapping()}>
              Save mapping
            </Button>
          </div>
        )}
        {mappings.length === 0 ? (
          <p className="px-5 py-8 text-sm text-gray-400 sm:px-6">
            {qbDetailsLoading ? 'Loading category mappings…' : 'No category mappings yet.'}
          </p>
        ) : (
          <AdminDataTable columns={['Category', 'QuickBooks account', 'Type', '']}>
            {mappings.map((mapping) => (
              <AdminTableRow key={mapping.id}>
                <AdminTableCell className="font-medium text-gray-900">
                  {mapping.zepex_category}
                </AdminTableCell>
                <AdminTableCell>{mapping.quickbooks_account_name}</AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {mapping.quickbooks_account_type || '—'}
                </AdminTableCell>
                <AdminTableCell className="text-right">
                  {canManage && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={saving}
                      onClick={() => void handleDeleteMapping(mapping.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </AdminDataTable>
        )}
      </AdminListPanel>

      <AdminListPanel
        title="Payment account"
        description="Bank or credit card account used when exporting paid reports."
      >
        <div className="flex flex-wrap items-end gap-3 px-5 py-5 sm:px-6">
          <label className="min-w-[16rem] flex-1 text-sm text-gray-700">
            QuickBooks payment account
            <select
              className={`${selectClassName} mt-1`}
              value={selectedPaymentAccountId}
              disabled={!canManage || saving}
              onChange={(e) => setSelectedPaymentAccountId(e.target.value)}
            >
              <option value="">Select account</option>
              {paymentAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </label>
          {canManage && (
            <Button disabled={saving} onClick={() => void handleSavePaymentAccount()}>
              Save account
            </Button>
          )}
        </div>
      </AdminListPanel>

      {unexportedReports.length > 0 && (
        <AdminListPanel
          title="Reports awaiting export"
          count={unexportedReports.length}
          description="Paid reports that have not been sent to QuickBooks yet."
        >
          <AdminDataTable columns={['Report', 'Employee', 'Amount', 'Paid', '']}>
            {unexportedReports.map((report) => (
              <AdminTableRow key={report.id}>
                <AdminTableCell className="font-medium text-gray-900">{report.month}</AdminTableCell>
                <AdminTableCell>{report.employee_name || report.employee_email}</AdminTableCell>
                <AdminTableCell>{report.total_amount}</AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {formatDateTime(report.paid_at)}
                </AdminTableCell>
                <AdminTableCell className="text-right">
                  {canManage && (
                    <Button
                      size="sm"
                      disabled={saving || pollingReportId === report.id}
                      onClick={() => void handleExportReport(report.id)}
                    >
                      {pollingReportId === report.id ? 'Exporting…' : 'Export'}
                    </Button>
                  )}
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </AdminDataTable>
        </AdminListPanel>
      )}

      <AdminListPanel
        title="Export history"
        count={exports.length}
        description="Paid reports sent to QuickBooks."
      >
        {exports.length === 0 ? (
          <p className="px-5 py-8 text-sm text-gray-400 sm:px-6">
            {qbDetailsLoading ? 'Loading export history…' : 'No QuickBooks exports yet.'}
          </p>
        ) : (
          <AdminDataTable columns={['Report', 'Employee', 'Amount', 'Status', 'Exported', 'Reconciliation', '']}>
            {exports.map((item) => {
              const reconcile = reconcileResults[item.report.id]
              return (
                <AdminTableRow key={`${item.report.id}-${item.created_at}`}>
                  <AdminTableCell className="font-medium text-gray-900">
                    {item.report.month || item.report.id}
                  </AdminTableCell>
                  <AdminTableCell>{item.report.employee?.name || '—'}</AdminTableCell>
                  <AdminTableCell>
                    {item.exported_amount || item.report.total_amount || '—'}
                  </AdminTableCell>
                  <AdminTableCell>
                    <StatusBadge
                      status={pollingReportId === item.report.id ? 'PROCESSING' : item.status}
                    />
                  </AdminTableCell>
                  <AdminTableCell className="text-gray-500">
                    {formatDateTime(item.exported_at || item.created_at)}
                  </AdminTableCell>
                  <AdminTableCell>
                    {reconcile ? (
                      <StatusBadge status={reconcile.reconciliation_status} />
                    ) : (
                      <span className="text-gray-400">Not checked</span>
                    )}
                  </AdminTableCell>
                  <AdminTableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      {canManage && item.status === 'FAILED' && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={saving || pollingReportId === item.report.id}
                          onClick={() => void handleRetryExport(item.report.id)}
                        >
                          Retry
                        </Button>
                      )}
                      {canManage && item.status === 'SUCCESS' && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={reconcilingReportId === item.report.id}
                          onClick={() => void handleReconcile(item.report.id)}
                        >
                          {reconcilingReportId === item.report.id ? 'Checking…' : 'Reconcile'}
                        </Button>
                      )}
                    </div>
                  </AdminTableCell>
                </AdminTableRow>
              )
            })}
          </AdminDataTable>
        )}
      </AdminListPanel>
    </div>
  )

  const connectedTabs = [
    bambooConnected && {
      key: 'bamboohr',
      label: 'BambooHR',
      icon: Sprout,
      content: bambooPanelContent,
    },
    connected && {
      key: 'quickbooks',
      label: 'QuickBooks',
      icon: Receipt,
      content: quickBooksPanelContent,
    },
  ].filter(Boolean) as Array<{ key: string; label: string; icon: LucideIcon; content: ReactNode }>

  return (
    <DashboardLayout
      title="Third-party integrations"
      subtitle="Connect accounting and HR tools used by your company"
      breadcrumb="Integrations"
      icon={Plug}
      navItems={navItems}
      headerAction={
        <Button onClick={() => setAddIntegrationOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" />
          Add integration
        </Button>
      }
    >
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {dashboard && (
        <div className="mb-8 grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg border border-[#e2e8f0] bg-white px-5 py-4">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
              Supported integrations
            </p>
            <p className="mt-1 text-2xl font-semibold text-gray-900">
              {dashboard.summary.supported_integrations}
            </p>
          </div>
          <div className="rounded-lg border border-[#e2e8f0] bg-white px-5 py-4">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Configured</p>
            <p className="mt-1 text-2xl font-semibold text-gray-900">
              {dashboard.summary.configured_integrations}
            </p>
          </div>
          <div className="rounded-lg border border-[#e2e8f0] bg-white px-5 py-4">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Connected</p>
            <p className="mt-1 text-2xl font-semibold text-gray-900">
              {dashboard.summary.connected_integrations}
            </p>
          </div>
        </div>
      )}

      {connectedTabs.length === 0 ? (
        <AdminListPanel
          title="Available integrations"
          description="Connect a provider to sync HR data or export paid reports."
        >
          <CatalogList>
            {bambooRow}
            {quickBooksRow}
            {comingSoonRows}
          </CatalogList>
        </AdminListPanel>
      ) : connectedTabs.length === 1 ? (
        connectedTabs[0].content
      ) : (
        <Tabs defaultValue={connectedTabs[0].key}>
          <TabsList>
            {connectedTabs.map((tab) => (
              <TabsTrigger key={tab.key} value={tab.key}>
                <tab.icon className="h-4 w-4" />
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
          {connectedTabs.map((tab) => (
            <TabsContent key={tab.key} value={tab.key}>
              {tab.content}
            </TabsContent>
          ))}
        </Tabs>
      )}

      {activity.length > 0 && (
        <AdminListPanel
          className="mt-8"
          title="Recent activity"
          count={activity.length}
          description="Latest integration events across BambooHR and QuickBooks."
        >
          <AdminDataTable columns={['Provider', 'Event', 'Message', 'When']}>
            {activity.map((item) => (
              <AdminTableRow key={item.id}>
                <AdminTableCell className="font-medium text-gray-900">{item.provider}</AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {item.action_label || item.action}
                </AdminTableCell>
                <AdminTableCell className="text-gray-500">{item.message}</AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {formatDateTime(item.created_at)}
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </AdminDataTable>
        </AdminListPanel>
      )}

      <Dialog open={addIntegrationOpen} onOpenChange={setAddIntegrationOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add integration</DialogTitle>
            <DialogDescription>Connect another accounting or HR tool.</DialogDescription>
          </DialogHeader>
          {addableRows.length === 0 ? (
            <p className="text-sm text-gray-500">
              Every available integration is already connected.
            </p>
          ) : (
            <CatalogList>{addableRows}</CatalogList>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={bambooConnectOpen} onOpenChange={setBambooConnectOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Connect BambooHR</DialogTitle>
            <DialogDescription>
              Enter your BambooHR company domain to start the authorization.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="bamboo-domain">BambooHR company domain</Label>
            <Input
              id="bamboo-domain"
              placeholder="yourcompany"
              value={bambooDomain}
              onChange={(e) => setBambooDomain(e.target.value)}
            />
            <p className="text-xs text-gray-400">
              The first part of your BambooHR URL: https://
              {bambooDomain || 'yourcompany'}.bamboohr.com
            </p>
          </div>
          {error && bambooConnectOpen && <p className="text-sm text-red-600">{error}</p>}
          <AdminModalFooter
            onCancel={() => setBambooConnectOpen(false)}
            submitLabel="Connect"
            submitType="button"
            submitting={saving}
            onSubmit={() => void handleConnectBambooHR()}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={bambooPreviewOpen} onOpenChange={setBambooPreviewOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>BambooHR employee directory</DialogTitle>
            <DialogDescription>
              Live preview from BambooHR
              {bambooPreviewEmployees.length > 0 ? ` — ${bambooPreviewEmployees.length} employees` : ''}
              .
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[28rem] overflow-y-auto">
            {bambooPreviewLoading ? (
              <p className="py-8 text-center text-sm text-gray-400">Loading…</p>
            ) : bambooPreviewEmployees.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-400">No employees returned.</p>
            ) : (
              <AdminDataTable columns={['Employee', 'Job title', 'Department', 'Status', 'Supervisor']}>
                {bambooPreviewEmployees.map((employee) => (
                  <AdminTableRow key={employee.employeeId}>
                    <AdminTableCell className="font-medium text-gray-900">
                      <div>
                        {[employee.firstName, employee.lastName].filter(Boolean).join(' ') ||
                          employee.preferredName ||
                          '—'}
                      </div>
                      <div className="text-xs text-gray-400">{employee.workEmail || '—'}</div>
                    </AdminTableCell>
                    <AdminTableCell className="text-gray-500">
                      {employee.jobTitle || employee.jobTitleName || '—'}
                    </AdminTableCell>
                    <AdminTableCell className="text-gray-500">
                      {employee.department || '—'}
                    </AdminTableCell>
                    <AdminTableCell>
                      <StatusBadge status={employee.status || 'UNKNOWN'} />
                    </AdminTableCell>
                    <AdminTableCell className="text-gray-500">
                      {employee.supervisor || '—'}
                    </AdminTableCell>
                  </AdminTableRow>
                ))}
              </AdminDataTable>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <AdminConfirmDialog
        open={disconnectOpen}
        onOpenChange={setDisconnectOpen}
        title="Disconnect QuickBooks?"
        description="ZepEX will stop exporting paid reports until you connect again. Existing export history is kept."
        confirmLabel="Disconnect"
        loading={saving}
        onConfirm={() => void handleDisconnect()}
      />
    </DashboardLayout>
  )
}
