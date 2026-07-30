import { FileUp, Shield } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  activatePolicyRule,
  createCompanyPolicy,
  createPolicyRule,
  deactivatePolicyRule,
  downloadPolicyRulesTemplate,
  getFinanceSettings,
  importPolicyRulesCsv,
  listCompanyRoles,
  listPolicyRules,
  listPolicyVersions,
  activatePolicyVersion,
  archivePolicyVersion,
  deleteDraftPolicyVersion,
  updatePolicyRule,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminBulkActions } from '@/components/admin/AdminBulkActions'
import { CsvImportDialog } from '@/components/admin/CsvImportDialog'
import { AdminConfirmDialog } from '@/components/admin/AdminConfirmDialog'
import { AdminListSearchBar } from '@/components/admin/AdminListSearchBar'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { AdminModalFooter } from '@/components/admin/AdminModalFooter'
import { AdminPolicyRuleCard } from '@/components/admin/AdminPolicyRuleCard'
import { PolicyDocumentImportDialog } from '@/components/admin/PolicyDocumentImportDialog'
import { PolicyToolsPanel } from '@/components/admin/PolicyToolsPanel'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { useAdminNav } from '@/hooks/useAdminNav'
import {
  usePersistedPolicyDocumentImportJob,
} from '@/hooks/usePersistedPolicyDocumentImportJob'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { CardsGridShimmer } from '@/components/ui/shimmer'
import { PaginationControls } from '@/components/ui/pagination-controls'
import { toast } from '@/lib/toast'
import { financeCurrencyCode } from '@/lib/financeSettings'
import type { CompanyRole, PolicyRule, PolicyVersion } from '@/types'
import AssignIcon from '@/assets/assign.png'
import UploadIcon from '@/assets/upload.png'

const selectClassName =
  'flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm'

export function PolicyPage() {
  const { navItems } = useAdminNav()
  const [rules, setRules] = useState<PolicyRule[]>([])
  const [roles, setRoles] = useState<CompanyRole[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<PolicyRule | null>(null)
  const [form, setForm] = useState({
    company_role_id: '' as number | '',
    category_name: '',
    max_amount: '',
    category_description: '',
  })
  const [editForm, setEditForm] = useState({
    company_role_id: '' as number | '',
    category_name: '',
    max_amount: '',
    category_description: '',
  })
  const [searchDraft, setSearchDraft] = useState('')
  const [search, setSearch] = useState('')
  const [filterRoleId, setFilterRoleId] = useState('')
  const [importOpen, setImportOpen] = useState(false)
  const [policyCurrency, setPolicyCurrency] = useState('USD')
  const [policyDocOpen, setPolicyDocOpen] = useState(false)
  const [reviewImportId, setReviewImportId] = useState<string | null>(null)
  const [confirmDeactivate, setConfirmDeactivate] = useState<PolicyRule | null>(null)

  const handlePolicyDocReady = useCallback((preview: import('@/types').PolicyDocumentPreviewResponse) => {
    setReviewImportId(preview.import.id)
    setPolicyDocOpen(true)
    toast.success('Policy document extracted. Review the extracted rules.')
  }, [])

  const handlePolicyDocFailed = useCallback((_importId: string, message: string) => {
    toast.error(message)
  }, [])

  const { job: policyDocJob, setJob: setPolicyDocJob } = usePersistedPolicyDocumentImportJob({
    onReady: handlePolicyDocReady,
    onFailed: handlePolicyDocFailed,
  })

  const [policyVersions, setPolicyVersions] = useState<PolicyVersion[]>([])
  const [confirmPolicyVersionAction, setConfirmPolicyVersionAction] = useState<null | {
    mode: 'activate' | 'archive' | 'delete'
    versionId: string
  }>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [rulesRes, financeRes, rolesRes, versionsRes] = await Promise.all([
        listPolicyRules({
          page,
          search: search || undefined,
          company_role_id: filterRoleId || undefined,
        }),
        getFinanceSettings().catch(() => null),
        listCompanyRoles(),
        listPolicyVersions().catch(() => null),
      ])
      setRules(rulesRes.data.results)
      setTotalPages(rulesRes.data.total_pages)
      setTotalCount(rulesRes.data.count)
      setRoles(rolesRes.data.results.filter((role) => role.is_active !== false))
      if (versionsRes?.data) {
        setPolicyVersions(versionsRes.data.results)
      } else {
        setPolicyVersions([])
      }
      if (financeRes?.data.settings) {
        setPolicyCurrency(financeCurrencyCode(financeRes.data.settings))
      }
    } catch {
      setRules([])
      setTotalPages(1)
      setTotalCount(0)
      setPolicyVersions([])
    } finally {
      setLoading(false)
    }
  }, [page, search, filterRoleId])

  useEffect(() => {
    setPage(1)
  }, [search, filterRoleId])

  useEffect(() => {
    load()
  }, [load])

  const initPolicy = async () => {
    setSaving(true)
    setError('')
    try {
      await createCompanyPolicy()
      toast.success('Company policy created. You can now add rules.')
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.company_role_id) {
      toast.error('Select a company role for this rule.')
      return
    }

    setSaving(true)
    setError('')
    try {
      await createPolicyRule({
        company_role: form.company_role_id,
        category_name: form.category_name,
        max_amount: form.max_amount,
        is_unlimited: false,
        category_description: form.category_description,
        is_active: true,
      })
      setForm({
        company_role_id: '',
        category_name: '',
        max_amount: '',
        category_description: '',
      })
      setOpen(false)
      toast.success('Policy rule created successfully.')
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const openEdit = (rule: PolicyRule) => {
    setEditing(rule)
    setEditForm({
      company_role_id: rule.company_role,
      category_name: rule.category_name,
      max_amount: rule.max_amount ?? '',
      category_description: rule.category_description,
    })
    setError('')
    setEditOpen(true)
  }

  const handleUpdate = async (e: FormEvent) => {
    e.preventDefault()
    if (!editing) return
    setSaving(true)
    setError('')
    try {
      await updatePolicyRule(editing.id, {
        company_role: editForm.company_role_id || undefined,
        category_name: editForm.category_name,
        max_amount: editForm.max_amount,
        is_unlimited: false,
        category_description: editForm.category_description,
      })
      setEditOpen(false)
      setEditing(null)
      toast.success('Policy rule updated successfully.')
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const toggleRule = async (rule: PolicyRule) => {
    setSaving(true)
    setError('')
    try {
      if (rule.is_active === false) {
        await activatePolicyRule(rule.id)
        toast.success('Policy rule activated.')
      } else {
        await deactivatePolicyRule(rule.id)
        toast.success('Policy rule deactivated.')
      }
      setConfirmDeactivate(null)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
      toast.error(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const requestToggle = (rule: PolicyRule) => {
    if (rule.is_active === false) {
      void toggleRule(rule)
      return
    }
    setConfirmDeactivate(rule)
  }

  const handlePolicyVersionAction = async (
    mode: 'activate' | 'archive' | 'delete',
    versionId: string,
  ) => {
    setSaving(true)
    setError('')
    try {
      if (mode === 'activate') {
        await activatePolicyVersion(versionId)
        toast.success('Policy version activated.')
      } else if (mode === 'archive') {
        await archivePolicyVersion(versionId)
        toast.success('Policy version archived.')
      } else {
        const res = await deleteDraftPolicyVersion(versionId)
        toast.success(res.data.message || 'Draft policy version deleted.')
      }
      setConfirmPolicyVersionAction(null)
      await load()
    } catch (err) {
      const message = getApiErrorMessage(err)
      setError(message)
      toast.error(message)
    } finally {
      setSaving(false)
    }
  }

  const activeRules = rules.filter((r) => r.is_active !== false)
  const inactiveRules = rules.filter((r) => r.is_active === false)

  if (loading) {
    return (
      <DashboardLayout
        title="Expense Policy"
        subtitle="Set category spending limits per company role"
        breadcrumb="Expense Policy"
        icon={Shield}
        navItems={navItems}
      >
        <CardsGridShimmer />
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout
      title="Expense Policy"
      subtitle="Set category spending limits per company role"
      breadcrumb="Expense Policy"
      icon={Shield}
      navItems={navItems}
      headerAction={
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={initPolicy} disabled={saving}>
            Initialize Company Policy
            <img src={AssignIcon} alt="Assign" className="w-6 h-6" />
          </Button>
          <AdminBulkActions
            onImport={() => setImportOpen(true)}
            onDownloadTemplate={downloadPolicyRulesTemplate}
            disabled={saving}
          />
          <Button onClick={() => { setError(''); setOpen(true) }}>
            Add Policy Rules
            <img src={UploadIcon} alt="Upload" className="w-6 h-6" />
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={saving}
            onClick={() => setPolicyDocOpen(true)}
          >
            <FileUp className="h-4 w-4" />
            Import Policy Document
          </Button>
          <PolicyToolsPanel roles={roles} currency={policyCurrency} disabled={saving} onCopied={load} />
        </div>
      }
    >
      {error && !open && !editOpen && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {policyDocJob?.status === 'PROCESSING' && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
          <p>
            Extracting policy rules from <span className="font-medium">{policyDocJob.filename}</span> in the
            background…
          </p>
        </div>
      )}

      {policyDocJob?.status === 'REVIEW_REQUIRED' && !policyDocOpen && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p>
            Policy document <span className="font-medium">{policyDocJob.filename}</span> is ready for review.
          </p>
          <Button
            type="button"
            size="sm"
            onClick={() => {
              setReviewImportId(policyDocJob.importId)
              setPolicyDocOpen(true)
            }}
          >
            Review import
          </Button>
        </div>
      )}

      {policyDocJob?.status === 'FAILED' && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <p>
            Policy extraction failed
            {policyDocJob.errorMessage ? `: ${policyDocJob.errorMessage}` : '.'}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setPolicyDocJob(null)
              setReviewImportId(null)
              setPolicyDocOpen(true)
            }}
          >
            Retry upload
          </Button>
        </div>
      )}

      <AdminListPanel
        title="Policy Rules"
        count={activeRules.length}
        description="Role-based limits. Roles without a rule inherit Employee policy."
        toolbar={
          <div className="space-y-3">
            <AdminListSearchBar
              value={searchDraft}
              onChange={setSearchDraft}
              onApply={() => setSearch(searchDraft.trim())}
              onClear={() => {
                setSearchDraft('')
                setSearch('')
              }}
              placeholder="Search policy rules…"
              disabled={saving}
            />
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <select
                className={selectClassName}
                value={filterRoleId}
                onChange={(e) => setFilterRoleId(e.target.value)}
                disabled={saving}
              >
                <option value="">All roles</option>
                {roles.map((role) => (
                  <option key={role.id} value={String(role.id)}>
                    {role.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        }
      >
        {activeRules.length === 0 ? (
          <p className="px-5 py-8 text-sm text-gray-400 sm:px-6">No policy rules configured.</p>
        ) : (
          <div>
            <div className="hidden border-b border-[#e2e8f0] px-5 py-2 text-xs font-medium uppercase tracking-wide text-gray-400 sm:grid sm:grid-cols-[minmax(0,1fr)_8rem_14rem] sm:gap-4 sm:px-6">
              <span>Rule</span>
              <span className="text-right">Limit</span>
              <span className="text-right">Action</span>
            </div>
            {activeRules.map((rule) => (
              <AdminPolicyRuleCard
                key={rule.id}
                rule={rule}
                currency={policyCurrency}
                disabled={saving}
                onEdit={() => openEdit(rule)}
                onToggleActive={() => requestToggle(rule)}
              />
            ))}
          </div>
        )}
        <PaginationControls
          currentPage={page}
          totalPages={totalPages}
          totalCount={totalCount}
          onPageChange={setPage}
          disabled={saving}
        />
      </AdminListPanel>

      <AdminListPanel
        title="Policy Versions"
        count={policyVersions.length}
        description="Drafts and active policy versions created from policy document imports."
      >
        {policyVersions.length === 0 ? (
          <p className="px-5 py-6 text-sm text-gray-400 sm:px-6">No policy versions yet.</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {policyVersions.map((version) => {
              const status = String(version.status ?? '').toUpperCase()
              const isDraft = status === 'DRAFT'
              const isArchived = status === 'ARCHIVED'
              return (
                <div
                  key={version.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 sm:px-6"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-gray-900">
                      {version.title} <span className="text-gray-500">· v{version.version_number}</span>
                    </p>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {status}
                      {version.is_active ? ' · Active' : ''}
                      {version.activated_at ? ` · ${new Date(version.activated_at).toLocaleDateString('en-US')}` : ''}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {!version.is_active && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={saving}
                        onClick={() =>
                          setConfirmPolicyVersionAction({ mode: 'activate', versionId: version.id })
                        }
                      >
                        Activate
                      </Button>
                    )}
                    {!isArchived && !version.is_active && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={saving}
                        onClick={() =>
                          setConfirmPolicyVersionAction({ mode: 'archive', versionId: version.id })
                        }
                      >
                        Archive
                      </Button>
                    )}
                    {isDraft && (
                      <Button
                        type="button"
                        size="sm"
                        variant="destructive"
                        disabled={saving}
                        onClick={() =>
                          setConfirmPolicyVersionAction({ mode: 'delete', versionId: version.id })
                        }
                      >
                        Delete
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </AdminListPanel>

      {inactiveRules.length > 0 && (
        <div className="mt-6">
          <AdminListPanel
            title="Inactive Rules"
            count={inactiveRules.length}
          >
            {inactiveRules.map((rule) => (
              <AdminPolicyRuleCard
                key={rule.id}
                rule={rule}
                currency={policyCurrency}
                disabled={saving}
                onEdit={() => openEdit(rule)}
                onToggleActive={() => requestToggle(rule)}
              />
            ))}
          </AdminListPanel>
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Policy Rule</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-3">
            <div className="space-y-2">
              <Label>Company role</Label>
              <select
                className={selectClassName}
                value={form.company_role_id}
                onChange={(e) =>
                  setForm({
                    ...form,
                    company_role_id: e.target.value ? Number(e.target.value) : '',
                  })
                }
                required
              >
                <option value="" disabled>
                  Select role
                </option>
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Rule Name</Label>
              <Input
                value={form.category_name}
                onChange={(e) => setForm({ ...form, category_name: e.target.value })}
                placeholder="Flight Ticket"
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea
                value={form.category_description}
                onChange={(e) => setForm({ ...form, category_description: e.target.value })}
                placeholder="This is just a small description for this section"
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Limit Amount ({policyCurrency})</Label>
              <Input
                type="number"
                value={form.max_amount}
                onChange={(e) => setForm({ ...form, max_amount: e.target.value })}
                required
              />
            </div>
            {error && open && <p className="text-sm text-red-600">{error}</p>}
            <AdminModalFooter onCancel={() => setOpen(false)} submitLabel="Add" submitting={saving} />
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="capitalize">
              Edit {editing?.category_name.replace(/_/g, ' ')}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleUpdate} className="space-y-3">
            <div className="space-y-2">
              <Label>Company role</Label>
              <select
                className={selectClassName}
                value={editForm.company_role_id}
                onChange={(e) =>
                  setEditForm({
                    ...editForm,
                    company_role_id: e.target.value ? Number(e.target.value) : '',
                  })
                }
                required
              >
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Rule name</Label>
              <Input
                value={editForm.category_name}
                onChange={(e) => setEditForm({ ...editForm, category_name: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Limit Amount ({policyCurrency})</Label>
              <Input
                type="number"
                value={editForm.max_amount}
                onChange={(e) => setEditForm({ ...editForm, max_amount: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea
                value={editForm.category_description}
                onChange={(e) =>
                  setEditForm({ ...editForm, category_description: e.target.value })
                }
                required
              />
            </div>
            {error && editOpen && <p className="text-sm text-red-600">{error}</p>}
            <AdminModalFooter onCancel={() => setEditOpen(false)} submitLabel="Save" submitting={saving} />
          </form>
        </DialogContent>
      </Dialog>

      <AdminConfirmDialog
        open={Boolean(confirmDeactivate)}
        onOpenChange={(next) => !next && setConfirmDeactivate(null)}
        title="Deactivate policy rule"
        description={
          confirmDeactivate
            ? `Deactivate "${confirmDeactivate.category_name.replace(/_/g, ' ')}" for ${confirmDeactivate.company_role_name}?`
            : 'Deactivate this policy rule?'
        }
        confirmLabel="Deactivate"
        onConfirm={() => confirmDeactivate && toggleRule(confirmDeactivate)}
        loading={saving}
      />

      <AdminConfirmDialog
        open={Boolean(confirmPolicyVersionAction)}
        onOpenChange={(next) => !next && setConfirmPolicyVersionAction(null)}
        title={
          confirmPolicyVersionAction?.mode === 'activate'
            ? 'Activate policy version'
            : confirmPolicyVersionAction?.mode === 'archive'
              ? 'Archive policy version'
              : 'Delete draft policy version'
        }
        description={
          confirmPolicyVersionAction
            ? `${confirmPolicyVersionAction.mode === 'activate' ? 'Activate' : confirmPolicyVersionAction.mode === 'archive' ? 'Archive' : 'Delete'} "${policyVersions.find((v) => v.id === confirmPolicyVersionAction.versionId)?.title ?? 'this version'}"?`
            : 'Are you sure?'
        }
        confirmLabel={
          confirmPolicyVersionAction?.mode === 'activate'
            ? 'Activate'
            : confirmPolicyVersionAction?.mode === 'archive'
              ? 'Archive'
              : 'Delete'
        }
        onConfirm={() => {
          if (!confirmPolicyVersionAction) return
          handlePolicyVersionAction(confirmPolicyVersionAction.mode, confirmPolicyVersionAction.versionId)
        }}
        loading={saving}
      />

      <PolicyDocumentImportDialog
        open={policyDocOpen}
        onOpenChange={(next) => {
          setPolicyDocOpen(next)
          if (!next) setReviewImportId(null)
        }}
        reviewImportId={reviewImportId}
        onUploadQueued={(importId, filename) => {
          setPolicyDocJob({ importId, filename, status: 'PROCESSING' })
          setReviewImportId(null)
          toast.success('Document uploaded. Extracting policy rules in the background.')
        }}
        onImported={() => {
          setPolicyDocJob(null)
          setReviewImportId(null)
          load()
        }}
        disabled={saving}
      />

      <CsvImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        title="Import policy rules"
        description="Upload a CSV file to create or update policy rules in bulk."
        onImport={importPolicyRulesCsv}
        onSuccess={load}
      />
    </DashboardLayout>
  )
}
