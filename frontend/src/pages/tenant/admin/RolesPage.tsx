import { Pencil, PowerOff, UserCog } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  createCompanyRole,
  deactivateCompanyRole,
  downloadRolesTemplate,
  importCompanyRolesCsv,
  listCompanyRoles,
  updateCompanyRole,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminBulkActions } from '@/components/admin/AdminBulkActions'
import { CsvImportDialog } from '@/components/admin/CsvImportDialog'
import { AdminListSearchBar } from '@/components/admin/AdminListSearchBar'
import { AdminConfirmDialog } from '@/components/admin/AdminConfirmDialog'
import { AdminDataTable, AdminTableCell, AdminTableRow } from '@/components/admin/AdminDataTable'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { AdminModalFooter } from '@/components/admin/AdminModalFooter'
import { StatusBadge } from '@/components/StatusBadge'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { useAdminNav } from '@/hooks/useAdminNav'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CardsGridShimmer } from '@/components/ui/shimmer'
import { PaginationControls } from '@/components/ui/pagination-controls'
import { toast } from '@/lib/toast'
import type { CompanyRole } from '@/types'
import UploadIcon from '@/assets/upload.png'
import AssignIcon from '@/assets/assign.png'

const defaultPermissions = {
  can_upload_receipt: false,
  can_submit_expense: false,
  can_approve_expense: false,
  can_mark_paid: false,
  can_manage_company: false,
  can_manage_roles: false,
  can_manage_employees: false,
  can_manage_departments: false,
  can_manage_policy: false,
  can_manage_workflow: false,
  can_view_company_reports: false,
  can_manage_integrations: false,
  can_view_integrations: false,
}

const permissionFields: Array<{ key: keyof typeof defaultPermissions; label: string }> = [
  { key: 'can_upload_receipt', label: 'Upload receipt' },
  { key: 'can_submit_expense', label: 'Submit expense' },
  { key: 'can_approve_expense', label: 'Approve expense' },
  { key: 'can_mark_paid', label: 'Mark paid' },
  { key: 'can_manage_company', label: 'Edit company details' },
  { key: 'can_manage_roles', label: 'Manage roles' },
  { key: 'can_manage_employees', label: 'Manage employees' },
  { key: 'can_manage_departments', label: 'Manage departments' },
  { key: 'can_manage_policy', label: 'Manage policy' },
  { key: 'can_manage_workflow', label: 'Manage workflow' },
  { key: 'can_view_company_reports', label: 'View company reports' },
  { key: 'can_view_integrations', label: 'View integrations' },
  { key: 'can_manage_integrations', label: 'Manage integrations' },
]

function PermissionCheck({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-gray-700">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

const defaultRoleTemplates = [
  {
    name: 'Employee',
    can_upload_receipt: true,
    can_submit_expense: true,
    can_approve_expense: false,
    can_mark_paid: false,
  },
  {
    name: 'Manager',
    can_upload_receipt: false,
    can_submit_expense: false,
    can_approve_expense: true,
    can_mark_paid: false,
  },
  {
    name: 'Accounts',
    can_upload_receipt: false,
    can_submit_expense: false,
    can_approve_expense: false,
    can_mark_paid: true,
  },
] as const

export function RolesPage() {
  const { navItems } = useAdminNav()
  const [roles, setRoles] = useState<CompanyRole[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [deactivateRole, setDeactivateRole] = useState<CompanyRole | null>(null)
  const [searchDraft, setSearchDraft] = useState('')
  const [search, setSearch] = useState('')
  const [importOpen, setImportOpen] = useState(false)
  const [editing, setEditing] = useState<CompanyRole | null>(null)
  const [form, setForm] = useState({ name: '', ...defaultPermissions })
  const [editForm, setEditForm] = useState({ name: '', ...defaultPermissions })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await listCompanyRoles({ page, search: search || undefined })
      setRoles(data.results)
      setTotalPages(data.total_pages)
      setTotalCount(data.count)
    } finally {
      setLoading(false)
    }
  }, [page, search])

  useEffect(() => {
    setPage(1)
  }, [search])

  useEffect(() => {
    load()
  }, [load])

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await createCompanyRole(form)
      setForm({ name: '', ...defaultPermissions })
      setCreateOpen(false)
      toast.success('Role created successfully.')
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const openEdit = (role: CompanyRole) => {
    setEditing(role)
    setEditForm({
      name: role.name,
      can_upload_receipt: role.can_upload_receipt,
      can_submit_expense: role.can_submit_expense,
      can_approve_expense: role.can_approve_expense,
      can_mark_paid: role.can_mark_paid,
      can_manage_company: Boolean(role.can_manage_company),
      can_manage_roles: Boolean(role.can_manage_roles),
      can_manage_employees: Boolean(role.can_manage_employees),
      can_manage_departments: Boolean(role.can_manage_departments),
      can_manage_policy: Boolean(role.can_manage_policy),
      can_manage_workflow: Boolean(role.can_manage_workflow),
      can_view_company_reports: Boolean(role.can_view_company_reports),
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
      await updateCompanyRole(editing.id, editForm)
      setEditOpen(false)
      setEditing(null)
      toast.success('Role updated successfully.')
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleDeactivate = async () => {
    if (!deactivateRole) return
    setSaving(true)
    setError('')
    try {
      await deactivateCompanyRole(deactivateRole.id)
      setDeactivateRole(null)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleCreateDefaults = async () => {
    setSaving(true)
    setError('')
    try {
      for (const template of defaultRoleTemplates) {
        await createCompanyRole(template)
      }
      toast.success('Default roles created successfully.')
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const permissionSummary = (role: CompanyRole) => {
    const parts: string[] = []
    if (role.can_upload_receipt) parts.push('Upload')
    if (role.can_submit_expense) parts.push('Submit')
    if (role.can_approve_expense) parts.push('Approve')
    if (role.can_mark_paid) parts.push('Pay')
    if (role.can_manage_company) parts.push('Company')
    if (role.can_manage_roles) parts.push('Roles')
    if (role.can_manage_employees) parts.push('Employees')
    if (role.can_manage_departments) parts.push('Departments')
    if (role.can_manage_policy) parts.push('Policy')
    if (role.can_manage_workflow) parts.push('Workflow')
    if (role.can_view_company_reports) parts.push('Reports')
    if (role.can_view_integrations) parts.push('View integrations')
    if (role.can_manage_integrations) parts.push('Integrations')
    return parts.join(', ') || '—'
  }

  if (loading) {
    return (
      <DashboardLayout
        title="Roles"
        subtitle="Manage company permission profiles"
        breadcrumb="Roles"
        icon={UserCog}
        navItems={navItems}
      >
        <CardsGridShimmer />
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout
      title="Roles"
      subtitle="Manage company permission profiles"
      breadcrumb="Roles"
      icon={UserCog}
      navItems={navItems}
      headerAction={
        <div className="flex flex-wrap gap-2">
          {roles.length === 0 && (
            <Button variant="secondary" disabled={saving} onClick={handleCreateDefaults}>
              Create default roles
              <img src={AssignIcon} alt="Assign" className="w-6 h-6" />
            </Button>
          )}
          <AdminBulkActions
            onImport={() => setImportOpen(true)}
            onDownloadTemplate={downloadRolesTemplate}
            disabled={saving}
          />
          <Button onClick={() => { setError(''); setCreateOpen(true) }}>
            Create Role
            <img src={UploadIcon} alt="Upload" className="w-6 h-6" />
          </Button>
        </div>
      }
    >
      {error && !createOpen && !editOpen && !deactivateRole && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <AdminListPanel
        title="Company Roles"
        count={totalCount}
        description="Custom permission profiles for upload, approve, and payment workflows."
        toolbar={
          <AdminListSearchBar
            value={searchDraft}
            onChange={setSearchDraft}
            onApply={() => setSearch(searchDraft.trim())}
            onClear={() => {
              setSearchDraft('')
              setSearch('')
            }}
            placeholder="Search roles…"
            disabled={saving}
          />
        }
      >
        {roles.length === 0 ? (
          <p className="px-5 py-8 text-sm text-gray-400 sm:px-6">
            No roles yet. Create default roles or add your own.
          </p>
        ) : (
          <AdminDataTable columns={['Role', 'Permissions', 'Status', '']}>
            {roles.map((role) => (
              <AdminTableRow key={role.id}>
                <AdminTableCell className="font-medium text-gray-900">{role.name}</AdminTableCell>
                <AdminTableCell className="text-gray-500">{permissionSummary(role)}</AdminTableCell>
                <AdminTableCell>
                  <StatusBadge status={role.is_active ? 'ACTIVE' : 'INACTIVE'} />
                </AdminTableCell>
                <AdminTableCell>
                  <div className="flex justify-end gap-1">
                    <Button size="sm" variant="ghost" disabled={saving} onClick={() => openEdit(role)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    {role.is_active && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={saving}
                        onClick={() => setDeactivateRole(role)}
                      >
                        <PowerOff className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </AdminDataTable>
        )}
        <PaginationControls
          currentPage={page}
          totalPages={totalPages}
          totalCount={totalCount}
          onPageChange={setPage}
          disabled={saving}
        />
      </AdminListPanel>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create Role</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-3">
            <div className="space-y-2">
              <Label>Role name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Finance Head"
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Permissions</Label>
              <div className="max-h-64 space-y-2 overflow-y-auto rounded-md border border-gray-200 p-3">
                {permissionFields.map((field) => (
                  <PermissionCheck
                    key={field.key}
                    label={field.label}
                    checked={form[field.key]}
                    onChange={(v) => setForm({ ...form, [field.key]: v })}
                  />
                ))}
              </div>
            </div>
            {error && createOpen && <p className="text-sm text-red-600">{error}</p>}
            <AdminModalFooter
              onCancel={() => setCreateOpen(false)}
              submitLabel="Create"
              submitting={saving}
            />
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Role</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleUpdate} className="space-y-3">
            <div className="space-y-2">
              <Label>Role name</Label>
              <Input
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Permissions</Label>
              <div className="max-h-64 space-y-2 overflow-y-auto rounded-md border border-gray-200 p-3">
                {permissionFields.map((field) => (
                  <PermissionCheck
                    key={field.key}
                    label={field.label}
                    checked={editForm[field.key]}
                    onChange={(v) => setEditForm({ ...editForm, [field.key]: v })}
                  />
                ))}
              </div>
            </div>
            {error && editOpen && <p className="text-sm text-red-600">{error}</p>}
            <AdminModalFooter
              onCancel={() => setEditOpen(false)}
              submitLabel="Save"
              submitting={saving}
            />
          </form>
        </DialogContent>
      </Dialog>

      <AdminConfirmDialog
        open={!!deactivateRole}
        onOpenChange={(v) => !v && setDeactivateRole(null)}
        title="Deactivate Role"
        description={`Deactivate role "${deactivateRole?.name}"?`}
        confirmLabel="Deactivate"
        onConfirm={handleDeactivate}
        loading={saving}
      />

      <CsvImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        title="Import roles"
        description="Upload a CSV file to create or update company roles in bulk."
        onImport={importCompanyRolesCsv}
        onSuccess={load}
      />
    </DashboardLayout>
  )
}
