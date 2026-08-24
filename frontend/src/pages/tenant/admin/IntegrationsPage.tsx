import { Plug, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  connectQuickBooks,
  deleteQuickBooksCategoryMapping,
  disconnectQuickBooks,
  getQuickBooksAccounts,
  getQuickBooksCategoryMappings,
  getQuickBooksExportHistory,
  getQuickBooksPaymentAccounts,
  getQuickBooksStatus,
  listIntegrationProviders,
  listPolicyRules,
  retryQuickBooksExport,
  saveQuickBooksCategoryMapping,
  saveQuickBooksPaymentAccount,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminConfirmDialog } from '@/components/admin/AdminConfirmDialog'
import { AdminDataTable, AdminTableCell, AdminTableRow } from '@/components/admin/AdminDataTable'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { StatusBadge } from '@/components/StatusBadge'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { Button } from '@/components/ui/button'
import { AdminListPanelShimmer } from '@/components/ui/shimmer'
import { useAuth } from '@/context/AuthContext'
import { useAdminNav } from '@/hooks/useAdminNav'
import { hasPermission } from '@/lib/rolePermissions'
import { fetchAllPages } from '@/lib/pagination'
import { toast } from '@/lib/toast'
import { formatDateTime } from '@/lib/utils'
import type {
  IntegrationProviderCatalogItem,
  QuickBooksAccount,
  QuickBooksCategoryMapping,
  QuickBooksExportHistoryItem,
  QuickBooksStatusResponse,
} from '@/types'

const selectClassName =
  'flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm'

export function IntegrationsPage() {
  const { user } = useAuth()
  const { navItems } = useAdminNav()
  const [searchParams, setSearchParams] = useSearchParams()
  const canManage =
    user?.role === 'COMPANY_ADMIN' || hasPermission(user, 'can_manage_integrations')

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [providers, setProviders] = useState<IntegrationProviderCatalogItem[]>([])
  const [status, setStatus] = useState<QuickBooksStatusResponse | null>(null)
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

  const connected = Boolean(status?.connected)
  const comingSoon = useMemo(
    () => providers.filter((item) => item.provider !== 'QUICKBOOKS'),
    [providers],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [catalogRes, statusRes] = await Promise.all([
        listIntegrationProviders(),
        getQuickBooksStatus(),
      ])
      setProviders(catalogRes.data.providers ?? [])
      setStatus(statusRes.data)

      if (!statusRes.data.connected) {
        setAccounts([])
        setMappings([])
        setPaymentAccounts([])
        setSelectedPaymentAccountId('')
        setExports([])
        return
      }

      const [accountsRes, mappingsRes, paymentRes, historyRes, policyRules] = await Promise.all([
        getQuickBooksAccounts().catch(() => null),
        getQuickBooksCategoryMappings().catch(() => null),
        getQuickBooksPaymentAccounts().catch(() => null),
        getQuickBooksExportHistory().catch(() => null),
        fetchAllPages((page) => listPolicyRules({ page })).catch(() => []),
      ])

      setAccounts(accountsRes?.data.accounts ?? [])
      setMappings(mappingsRes?.data.mappings ?? [])
      setPaymentAccounts(paymentRes?.data.accounts ?? [])
      setSelectedPaymentAccountId(paymentRes?.data.selected_account?.id ?? '')
      setExports(historyRes?.data.results ?? [])
      setCategories(
        [...new Set(policyRules.map((rule) => rule.category_name).filter(Boolean))].sort(),
      )
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

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
    void load()
  }, [load, searchParams, setSearchParams])

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
      await load()
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
      await load()
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
      await load()
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
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleRetryExport = async (reportId: string) => {
    setSaving(true)
    setError('')
    try {
      const { data } = await retryQuickBooksExport(reportId)
      toast.success(data.message || 'Export retry queued.')
      await load()
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

  return (
    <DashboardLayout
      title="Third-party integrations"
      subtitle="Connect accounting and HR tools used by your company"
      breadcrumb="Integrations"
      icon={Plug}
      navItems={navItems}
    >
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <AdminListPanel
        title="QuickBooks"
        description="Export paid expense reports to QuickBooks as purchases."
      >
        <div className="space-y-5 px-5 py-5 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-gray-900">
                {connected ? status?.company?.name || 'Connected' : 'Not connected'}
              </p>
              <p className="mt-1 text-sm text-gray-500">
                {connected
                  ? status?.healthy === false
                    ? status?.error || 'Connected, but QuickBooks is not responding.'
                    : 'Connection is healthy. Map categories before exporting reports.'
                  : 'Connect your Intuit company to sync expense accounts and exports.'}
              </p>
            </div>
            {canManage && (
              connected ? (
                <Button variant="outline" disabled={saving} onClick={() => setDisconnectOpen(true)}>
                  Disconnect
                </Button>
              ) : (
                <Button disabled={saving} onClick={() => void handleConnect()}>
                  Connect QuickBooks
                </Button>
              )
            )}
          </div>
        </div>
      </AdminListPanel>

      {connected && (
        <>
          <AdminListPanel
            className="mt-8"
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
              <p className="px-5 py-8 text-sm text-gray-400 sm:px-6">No category mappings yet.</p>
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
            className="mt-8"
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

          <AdminListPanel
            className="mt-8"
            title="Export history"
            count={exports.length}
            description="Paid reports sent to QuickBooks."
          >
            {exports.length === 0 ? (
              <p className="px-5 py-8 text-sm text-gray-400 sm:px-6">No QuickBooks exports yet.</p>
            ) : (
              <AdminDataTable columns={['Report', 'Employee', 'Amount', 'Status', 'Exported', '']}>
                {exports.map((item) => (
                  <AdminTableRow key={`${item.report.id}-${item.created_at}`}>
                    <AdminTableCell className="font-medium text-gray-900">
                      {item.report.month || item.report.id}
                    </AdminTableCell>
                    <AdminTableCell>{item.report.employee?.name || '—'}</AdminTableCell>
                    <AdminTableCell>{item.exported_amount || item.report.total_amount || '—'}</AdminTableCell>
                    <AdminTableCell>
                      <StatusBadge status={item.status} />
                    </AdminTableCell>
                    <AdminTableCell className="text-gray-500">
                      {formatDateTime(item.exported_at || item.created_at)}
                    </AdminTableCell>
                    <AdminTableCell className="text-right">
                      {canManage && item.status === 'FAILED' && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={saving}
                          onClick={() => void handleRetryExport(item.report.id)}
                        >
                          Retry
                        </Button>
                      )}
                    </AdminTableCell>
                  </AdminTableRow>
                ))}
              </AdminDataTable>
            )}
          </AdminListPanel>
        </>
      )}

      {comingSoon.length > 0 && (
        <AdminListPanel
          className="mt-8"
          title="Other providers"
          description="These connectors are listed in the catalog and will be enabled as they ship."
        >
          <AdminDataTable columns={['Provider', 'Status']}>
            {comingSoon.map((provider) => (
              <AdminTableRow key={provider.provider}>
                <AdminTableCell className="font-medium text-gray-900">
                  {provider.provider_name}
                </AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {provider.is_connected ? 'Connected' : 'Coming soon'}
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </AdminDataTable>
        </AdminListPanel>
      )}

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
