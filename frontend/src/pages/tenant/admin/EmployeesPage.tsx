import { Pencil, Power, PowerOff, Trash2, Users, Mail, ListFilter } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  activateCompanyUser,
  assignManager,
  assignMissingCompanyRoles,
  createEmployee,
  deactivateCompanyUser,
  deleteCompanyUser,
  downloadEmployeesTemplate,
  editCompanyUser,
  updateEmployee,
  importEmployeesCsv,
  listCompanyRoles,
  listDepartments,
  listEmployees,
  sendEmployeeInvites,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { toast } from '@/lib/toast'
import { AdminBulkActions } from '@/components/admin/AdminBulkActions'
import { CsvImportDialog } from '@/components/admin/CsvImportDialog'
import { AdminListSearchBar } from '@/components/admin/AdminListSearchBar'
import { AdminConfirmDialog } from '@/components/admin/AdminConfirmDialog'
import { AdminDataTable, AdminTableCell, AdminTableRow, RolePill } from '@/components/admin/AdminDataTable'
import { UserAvatar } from '@/components/ui/user-avatar'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { AdminModalFooter } from '@/components/admin/AdminModalFooter'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { useAdminNav } from '@/hooks/useAdminNav'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import { AdminListPanelShimmer } from '@/components/ui/shimmer'
import { PaginationControls } from '@/components/ui/pagination-controls'
import type { CompanyRole, DepartmentRecord, EmployeeRecord } from '@/types'
import { fetchAllPages } from '@/lib/pagination'
import { formatDate } from '@/lib/utils'
import UploadIcon from '@/assets/upload.png'
import AssignIcon from '@/assets/assign.png'

const COMPANY_ADMIN_ROLE_VALUE = '__COMPANY_ADMIN__'

const selectClassName =
  'flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm'

type ConfirmAction = { type: 'deactivate' | 'delete'; emp: EmployeeRecord }

function employeeRoleLabel(emp: EmployeeRecord) {
  if (emp.role === 'COMPANY_ADMIN') return 'Company Admin'
  return emp.company_role_name || emp.role
}

function isCompanyAdminRoleValue(value: string) {
  return value === COMPANY_ADMIN_ROLE_VALUE
}

function inferSystemRole(role: CompanyRole): string {
  const name = role.name.trim().toLowerCase()
  if (name === 'accounts') return 'ACCOUNTS'
  if (name === 'manager') return 'MANAGER'
  if (role.can_mark_paid && !role.can_approve_expense) return 'ACCOUNTS'
  if (role.can_approve_expense) return 'MANAGER'
  return 'EMPLOYEE'
}

function defaultCompanyRoleId(roles: CompanyRole[]) {
  const active = roles.filter((r) => r.is_active !== false)
  const employee =
    active.find((r) => r.name.toLowerCase() === 'employee') ?? active[0]
  return employee ? String(employee.id) : ''
}

export function EmployeesPage() {
  const { navItems } = useAdminNav()
  const [employees, setEmployees] = useState<EmployeeRecord[]>([])
  const [allEmployees, setAllEmployees] = useState<EmployeeRecord[]>([])
  const [departments, setDepartments] = useState<DepartmentRecord[]>([])
  const [companyRoles, setCompanyRoles] = useState<CompanyRole[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [assignOpen, setAssignOpen] = useState(false)
  const [confirm, setConfirm] = useState<ConfirmAction | null>(null)
  const [searchDraft, setSearchDraft] = useState('')
  const [search, setSearch] = useState('')
  const [filterDepartmentId, setFilterDepartmentId] = useState('')
  const [filterRole, setFilterRole] = useState('')
  const [importOpen, setImportOpen] = useState(false)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [editing, setEditing] = useState<EmployeeRecord | null>(null)
  const [assignDept, setAssignDept] = useState('')
  const [assignManagerId, setAssignManagerId] = useState('')
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    password: '',
    department_id: '',
    company_role_id: '',
  })
  const [editForm, setEditForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    department_id: '',
    company_role_id: '',
    phone_number: '',
    address: '',
  })

  const activeCompanyRoles = companyRoles.filter((r) => r.is_active !== false)
  const activeCompanyAdminCount = allEmployees.filter(
    (e) => e.role === 'COMPANY_ADMIN' && e.is_active !== false,
  ).length

  const isSoleCompanyAdmin = (emp: EmployeeRecord) =>
    emp.role === 'COMPANY_ADMIN' && activeCompanyAdminCount <= 1

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [empRes, allDepts, allEmps, allRoles] = await Promise.all([
        listEmployees({
          page,
          search: search || undefined,
          department_id: filterDepartmentId || undefined,
          role: isCompanyAdminRoleValue(filterRole) ? 'COMPANY_ADMIN' : undefined,
          company_role_id:
            filterRole && !isCompanyAdminRoleValue(filterRole) ? filterRole : undefined,
        }),
        fetchAllPages((page) => listDepartments({ page })),
        fetchAllPages((page) => listEmployees({ page })),
        fetchAllPages((page) => listCompanyRoles({ page })),
      ])
      setEmployees(empRes.data.results)
      setTotalPages(empRes.data.total_pages)
      setTotalCount(empRes.data.count)
      setAllEmployees(allEmps)
      setDepartments(allDepts.filter((d) => d.is_active !== false))
      setCompanyRoles(allRoles)
    } finally {
      setLoading(false)
    }
  }, [page, search, filterDepartmentId, filterRole])

  useEffect(() => {
    setPage(1)
  }, [search, filterDepartmentId, filterRole])

  useEffect(() => {
    load()
  }, [load])

  const resetForm = () => {
    setForm({
      first_name: '',
      last_name: '',
      email: '',
      password: '',
      department_id: '',
      company_role_id: defaultCompanyRoleId(companyRoles),
    })
  }

  const handleFixMissingRoles = async () => {
    setSaving(true)
    setError('')
    try {
      const { data } = await assignMissingCompanyRoles()
      toast.success(data.message)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.company_role_id) {
      setError('Select a role.')
      return
    }
    const selectedRole = activeCompanyRoles.find(
      (r) => String(r.id) === form.company_role_id,
    )
    const isCompanyAdmin = isCompanyAdminRoleValue(form.company_role_id)
    if (!isCompanyAdmin && !selectedRole) {
      setError('Selected role is no longer available.')
      return
    }
    const systemRole = isCompanyAdmin ? 'COMPANY_ADMIN' : inferSystemRole(selectedRole!)
    if (['EMPLOYEE', 'MANAGER'].includes(systemRole) && !form.department_id) {
      setError('Department is required for this role.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const { data } = await createEmployee({
        first_name: form.first_name,
        last_name: form.last_name,
        email: form.email,
        password: form.password.trim() || undefined,
        role: systemRole,
        department_id: isCompanyAdmin ? undefined : form.department_id || undefined,
        company_role_id: isCompanyAdmin ? undefined : parseInt(form.company_role_id, 10),
      })
      resetForm()
      setCreateOpen(false)
      if (data.invite_email_sent) {
        toast.success(data.message || 'Employee created and invite email sent.')
      } else {
        toast.error(
          data.email_error ||
            data.message ||
            'Employee created, but the invite email could not be sent.',
        )
      }
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const openEdit = (emp: EmployeeRecord) => {
    setEditing(emp)
    setEditForm({
      first_name: emp.first_name,
      last_name: emp.last_name,
      email: emp.email,
      department_id: emp.department || '',
      company_role_id:
        emp.role === 'COMPANY_ADMIN'
          ? COMPANY_ADMIN_ROLE_VALUE
          : emp.company_role
            ? String(emp.company_role)
            : defaultCompanyRoleId(companyRoles),
      phone_number: emp.phone_number || '',
      address: emp.address || '',
    })
    setError('')
    setEditOpen(true)
  }

  const handleEdit = async (e: FormEvent) => {
    e.preventDefault()
    if (!editing) return
    if (!editForm.company_role_id) {
      setError('Select a role.')
      return
    }
    const isCompanyAdmin = isCompanyAdminRoleValue(editForm.company_role_id)
    const selectedRole = activeCompanyRoles.find(
      (r) => String(r.id) === editForm.company_role_id,
    )
    if (!isCompanyAdmin && !selectedRole) {
      setError('Selected role is no longer available.')
      return
    }
    if (
      editing.role === 'COMPANY_ADMIN' &&
      activeCompanyAdminCount <= 1 &&
      !isCompanyAdmin
    ) {
      setError('Cannot change role of the only company admin.')
      return
    }
    const systemRole = isCompanyAdmin ? 'COMPANY_ADMIN' : inferSystemRole(selectedRole!)
    if (['EMPLOYEE', 'MANAGER'].includes(systemRole) && !editForm.department_id) {
      setError('Department is required for this role.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await updateEmployee(editing.id, {
        first_name: editForm.first_name,
        last_name: editForm.last_name,
        email: editForm.email,
        department: isCompanyAdmin ? null : editForm.department_id || null,
        company_role: isCompanyAdmin ? null : parseInt(editForm.company_role_id, 10),
      })
      await editCompanyUser(editing.id, {
        first_name: editForm.first_name,
        last_name: editForm.last_name,
        email: editForm.email,
        role: systemRole,
        department_id: isCompanyAdmin ? null : editForm.department_id || null,
        company_role_id: isCompanyAdmin ? null : parseInt(editForm.company_role_id, 10),
        phone_number: editForm.phone_number || undefined,
        address: editForm.address || undefined,
      })
      setEditOpen(false)
      setEditing(null)
      toast.success('Employee updated successfully.')
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleConfirmAction = async () => {
    if (!confirm) return
    if (isSoleCompanyAdmin(confirm.emp)) {
      setError('Cannot deactivate or delete the only company admin.')
      setConfirm(null)
      return
    }
    setSaving(true)
    setError('')
    try {
      if (confirm.type === 'deactivate') {
        await deactivateCompanyUser(confirm.emp.id)
      } else {
        await deleteCompanyUser(confirm.emp.id)
      }
      setConfirm(null)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleActivate = async (emp: EmployeeRecord) => {
    setSaving(true)
    setError('')
    try {
      await activateCompanyUser(emp.id)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleAssign = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await assignManager(assignDept, parseInt(assignManagerId, 10))
      setAssignDept('')
      setAssignManagerId('')
      setAssignOpen(false)
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleSendInvites = async () => {
    setSaving(true)
    setError('')
    try {
      const { data } = await sendEmployeeInvites({ send_to_all: true })
      setInviteOpen(false)
      if (data.sent > 0) {
        toast.success(
          data.message ||
            `Invites sent: ${data.sent}${data.failed ? `, ${data.failed} failed` : ''}.`,
        )
      } else if (data.failed > 0) {
        const firstError = data.errors?.[0]?.error
        toast.error(firstError || `Failed to send ${data.failed} invite(s).`)
      } else {
        toast(
          data.message ||
            `No invites sent${data.skipped_already_sent ? ` (${data.skipped_already_sent} already invited)` : ''}.`,
        )
      }
      await load()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const managers = allEmployees.filter((e) => e.role === 'MANAGER' && e.is_active !== false)
  const missingCompanyRoleCount = allEmployees.filter(
    (e) => !e.company_role && e.role !== 'COMPANY_ADMIN',
  ).length

  if (loading) {
    return (
      <DashboardLayout
        title="Employees"
        subtitle="Manage users and assign managers"
        breadcrumb="Employees"
        icon={Users}
        navItems={navItems}
      >
        <AdminListPanelShimmer />
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout
      title="Employees"
      subtitle="Manage users and assign managers"
      breadcrumb="Employees"
      icon={Users}
      navItems={navItems}
      headerAction={
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={saving} onClick={() => { setError(''); setInviteOpen(true) }}>
            <Mail className="h-4 w-4" />
            Send invites
          </Button>
          <Button variant="secondary" onClick={() => { setError(''); setAssignOpen(true) }}>
            Assign Manager
            <img src={AssignIcon} alt="Assign" className="w-6 h-6" />
          </Button>
          <AdminBulkActions
            onImport={() => setImportOpen(true)}
            onDownloadTemplate={downloadEmployeesTemplate}
            disabled={saving}
          />
          <Button onClick={() => { setError(''); resetForm(); setCreateOpen(true) }}>
            Create Employee
            <img src={UploadIcon} alt="Upload" className="w-6 h-6" />
          </Button>
        </div>
      }
    >
      {missingCompanyRoleCount > 0 && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 text-sm text-orange-900">
          <p>
            {missingCompanyRoleCount} user(s) have no company role assigned.
          </p>
          <Button size="sm" variant="outline" disabled={saving} onClick={handleFixMissingRoles}>
            Assign default roles
          </Button>
        </div>
      )}
      {error && !createOpen && !editOpen && !assignOpen && !confirm && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <AdminListPanel
        title="All Users"
        count={totalCount}
        description="View employee details, roles, and department assignments."
        toolbar={
          <>
            <div className="flex flex-wrap items-center gap-2">
              <div className="min-w-0 flex-1">
                <AdminListSearchBar
                  value={searchDraft}
                  onChange={setSearchDraft}
                  onApply={() => setSearch(searchDraft.trim())}
                  onClear={() => {
                    setSearchDraft('')
                    setSearch('')
                  }}
                  placeholder="Search employees…"
                  disabled={saving}
                />
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setFiltersOpen((value) => !value)}
                aria-expanded={filtersOpen}
                disabled={saving}
              >
                <ListFilter className="h-4 w-4" />
                Filter
              </Button>
            </div>
            {filtersOpen && (
              <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-[#e2e8f0] bg-gray-50 p-3">
                <select
                  className={selectClassName + ' w-full min-w-[10rem] sm:w-auto sm:flex-1'}
                  value={filterDepartmentId}
                  onChange={(e) => setFilterDepartmentId(e.target.value)}
                  disabled={saving}
                >
                  <option value="">All departments</option>
                  {departments.map((d) => (
                    <option key={d.id} value={String(d.id)}>
                      {d.name}
                    </option>
                  ))}
                </select>
                <select
                  className={selectClassName + ' w-full min-w-[8rem] sm:w-auto sm:flex-1'}
                  value={filterRole}
                  onChange={(e) => setFilterRole(e.target.value)}
                  disabled={saving}
                >
                  <option value="">All roles</option>
                  <option value={COMPANY_ADMIN_ROLE_VALUE}>Company Admin</option>
                  {activeCompanyRoles.map((role) => (
                    <option key={role.id} value={String(role.id)}>
                      {role.name}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={saving || (!filterDepartmentId && !filterRole)}
                  onClick={() => {
                    setFilterDepartmentId('')
                    setFilterRole('')
                  }}
                >
                  Clear filters
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={saving}
                  onClick={() => setFiltersOpen(false)}
                >
                  Cancel
                </Button>
              </div>
            )}
          </>
        }
      >
        <AdminDataTable columns={['Name', 'Email Address', 'Role', 'Department', 'Created', '']}>
          {employees.map((emp) => (
            <AdminTableRow key={emp.id}>
              <AdminTableCell className="font-medium text-gray-900">
                <div className="flex items-center gap-3">
                  <UserAvatar
                    src={emp.profile_picture}
                    firstName={emp.first_name}
                    lastName={emp.last_name}
                    email={emp.email}
                  />
                  <span>
                    {emp.first_name} {emp.last_name}
                  </span>
                </div>
              </AdminTableCell>
              <AdminTableCell>{emp.email}</AdminTableCell>
              <AdminTableCell>
                <RolePill>{employeeRoleLabel(emp)}</RolePill>
              </AdminTableCell>
              <AdminTableCell>{emp.department_name || '—'}</AdminTableCell>
              <AdminTableCell className="text-gray-500">
                {formatDate(emp.created_at)}
              </AdminTableCell>
              <AdminTableCell className="text-right">
                <div className="flex justify-end gap-1">
                  <Button size="sm" variant="ghost" disabled={saving} onClick={() => openEdit(emp)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  {emp.is_active === false ? (
                    <Button size="sm" variant="ghost" disabled={saving} onClick={() => handleActivate(emp)}>
                      <Power className="h-3.5 w-3.5 text-green-600" />
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={saving || isSoleCompanyAdmin(emp)}
                      onClick={() => setConfirm({ type: 'deactivate', emp })}
                    >
                      <PowerOff className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={saving || isSoleCompanyAdmin(emp)}
                    onClick={() => setConfirm({ type: 'delete', emp })}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-red-500" />
                  </Button>
                </div>
              </AdminTableCell>
            </AdminTableRow>
          ))}
        </AdminDataTable>
        <PaginationControls
          currentPage={page}
          totalPages={totalPages}
          totalCount={totalCount}
          onPageChange={setPage}
          disabled={saving}
        />
      </AdminListPanel>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create Employee</DialogTitle>
            <DialogDescription>
              An invite email with login credentials is sent automatically when the employee is
              created.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-3">
            <div className="space-y-2">
              <Label>Name</Label>
              <div className="grid gap-2 sm:grid-cols-2">
                <Input
                  placeholder="First name"
                  value={form.first_name}
                  onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                  required
                />
                <Input
                  placeholder="Last name"
                  value={form.last_name}
                  onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Email</Label>
              <Input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Password</Label>
              <PasswordInput
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                Leave blank to auto-generate a password and send it in the invite email.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <select
                className={selectClassName}
                value={form.company_role_id}
                onChange={(e) => setForm({ ...form, company_role_id: e.target.value })}
                required
              >
                <option value="">Select role</option>
                <option value={COMPANY_ADMIN_ROLE_VALUE}>Company Admin</option>
                {activeCompanyRoles.map((r) => (
                  <option key={r.id} value={String(r.id)}>
                    {r.name}
                  </option>
                ))}
              </select>
            </div>
            {!isCompanyAdminRoleValue(form.company_role_id) && (
              <div className="space-y-2">
                <Label>Department</Label>
                <select
                  className={selectClassName}
                  value={form.department_id}
                  onChange={(e) => setForm({ ...form, department_id: e.target.value })}
                >
                  <option value="">Select department</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
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
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Employee</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleEdit} className="space-y-3">
            <div className="space-y-2">
              <Label>Name</Label>
              <div className="grid gap-2 sm:grid-cols-2">
                <Input
                  value={editForm.first_name}
                  onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
                  required
                />
                <Input
                  value={editForm.last_name}
                  onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Email</Label>
              <Input
                type="email"
                value={editForm.email}
                onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <select
                className={selectClassName}
                value={editForm.company_role_id}
                onChange={(e) => setEditForm({ ...editForm, company_role_id: e.target.value })}
                required
                disabled={
                  editing?.role === 'COMPANY_ADMIN' && activeCompanyAdminCount <= 1
                }
              >
                <option value="">Select role</option>
                <option value={COMPANY_ADMIN_ROLE_VALUE}>Company Admin</option>
                {activeCompanyRoles.map((r) => (
                  <option key={r.id} value={String(r.id)}>
                    {r.name}
                  </option>
                ))}
              </select>
              {editing?.role === 'COMPANY_ADMIN' && activeCompanyAdminCount <= 1 && (
                <p className="text-xs text-gray-500">
                  Role cannot be changed while this is the only company admin.
                </p>
              )}
            </div>
            {!isCompanyAdminRoleValue(editForm.company_role_id) && (
              <div className="space-y-2">
                <Label>Department</Label>
                <select
                  className={selectClassName}
                  value={editForm.department_id}
                  onChange={(e) => setEditForm({ ...editForm, department_id: e.target.value })}
                >
                  <option value="">None</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {error && editOpen && <p className="text-sm text-red-600">{error}</p>}
            <AdminModalFooter
              onCancel={() => setEditOpen(false)}
              submitLabel="Save"
              submitting={saving}
            />
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Assign Role To Department</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAssign} className="space-y-3">
            <div className="space-y-2">
              <Label>Department</Label>
              <select
                className={selectClassName}
                value={assignDept}
                onChange={(e) => setAssignDept(e.target.value)}
                required
              >
                <option value="">Select department</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Manager</Label>
              <select
                className={selectClassName}
                value={assignManagerId}
                onChange={(e) => setAssignManagerId(e.target.value)}
                required
              >
                <option value="">Select manager</option>
                {managers.map((m) => (
                  <option key={m.id} value={String(m.id)}>
                    {m.first_name} {m.last_name}
                  </option>
                ))}
              </select>
            </div>
            {error && assignOpen && <p className="text-sm text-red-600">{error}</p>}
            <AdminModalFooter
              onCancel={() => setAssignOpen(false)}
              submitLabel="Assign"
              submitting={saving}
            />
          </form>
        </DialogContent>
      </Dialog>

      <AdminConfirmDialog
        open={confirm?.type === 'deactivate'}
        onOpenChange={(v) => !v && setConfirm(null)}
        title="Deactivate Employee"
        description={`Deactivate ${confirm?.emp.email}? They will not be able to log in.`}
        confirmLabel="Deactivate"
        onConfirm={handleConfirmAction}
        loading={saving}
      />

      <AdminConfirmDialog
        open={confirm?.type === 'delete'}
        onOpenChange={(v) => !v && setConfirm(null)}
        title="Delete Employee"
        description={`Permanently delete ${confirm?.emp.email}? This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleConfirmAction}
        loading={saving}
      />

      <AdminConfirmDialog
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        title="Send employee invites"
        description="Send login invite emails to active employees who have not received one yet?"
        confirmLabel="Send invites"
        onConfirm={handleSendInvites}
        loading={saving}
      />

      <CsvImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        title="Import employees"
        description="Upload a CSV file to create or update employees in bulk."
        onImport={importEmployeesCsv}
        onSuccess={load}
      />
    </DashboardLayout>
  )
}
