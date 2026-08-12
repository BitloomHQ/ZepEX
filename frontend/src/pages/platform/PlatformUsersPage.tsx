import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Pencil, Users } from 'lucide-react'
import {
  createPlatformUser,
  listPlatformAdmins,
  listPlatformPermissions,
  updatePlatformAdminPermissions,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminDataTable, AdminTableCell, AdminTableRow } from '@/components/admin/AdminDataTable'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { DashboardLayout, platformNavWithAudit } from '@/components/layout/DashboardLayout'
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
import { PasswordInput } from '@/components/ui/password-input'
import { AdminListPanelShimmer } from '@/components/ui/shimmer'
import { toast } from '@/lib/toast'
import { formatDate } from '@/lib/utils'
import type { PlatformAdminUser, PlatformPermission } from '@/types'

const emptyForm = {
  email: '',
  first_name: '',
  last_name: '',
  password: '',
}

function canEditAdmin(admin: PlatformAdminUser): admin is PlatformAdminUser & { id: number } {
  return !admin.is_owner && typeof admin.id === 'number'
}

function PermissionPicker({
  grouped,
  selectedCodes,
  onToggle,
}: {
  grouped: Array<[string, PlatformPermission[]]>
  selectedCodes: string[]
  onToggle: (code: string) => void
}) {
  return (
    <div className="space-y-3">
      {grouped.map(([module, items]) => (
        <div key={module}>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {module}
          </p>
          <div className="space-y-1">
            {items.map((permission) => (
              <label key={permission.code} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={selectedCodes.includes(permission.code)}
                  onChange={() => onToggle(permission.code)}
                />
                {permission.name}
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function PlatformUsersPage() {
  const [admins, setAdmins] = useState<PlatformAdminUser[]>([])
  const [permissions, setPermissions] = useState<PlatformPermission[]>([])
  const [selectedCodes, setSelectedCodes] = useState<string[]>([])
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<PlatformAdminUser | null>(null)
  const [error, setError] = useState('')
  const [createdPassword, setCreatedPassword] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const [adminsRes, permissionsRes] = await Promise.all([
        listPlatformAdmins(),
        listPlatformPermissions(),
      ])
      setAdmins(adminsRes.data)
      setPermissions(permissionsRes.data)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const groupedPermissions = useMemo(() => {
    const groups = new Map<string, PlatformPermission[]>()
    for (const permission of permissions) {
      const current = groups.get(permission.module) ?? []
      current.push(permission)
      groups.set(permission.module, current)
    }
    return Array.from(groups.entries())
  }, [permissions])

  const togglePermission = (code: string) => {
    setSelectedCodes((current) =>
      current.includes(code) ? current.filter((item) => item !== code) : [...current, code],
    )
  }

  const openEdit = (admin: PlatformAdminUser) => {
    setEditing(admin)
    setSelectedCodes(admin.permissions.filter((code) => code !== '*'))
  }

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    try {
      const { data } = await createPlatformUser({
        email: form.email,
        first_name: form.first_name,
        last_name: form.last_name,
        password: form.password || undefined,
        permissions: selectedCodes,
      })
      toast.success(data.message)
      setCreatedPassword(data.temporary_password)
      setForm(emptyForm)
      setSelectedCodes([])
      await load()
      if (!data.temporary_password) {
        setCreateOpen(false)
      }
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleUpdatePermissions = async (event: FormEvent) => {
    event.preventDefault()
    if (!editing || !canEditAdmin(editing)) return
    setSaving(true)
    try {
      const { data } = await updatePlatformAdminPermissions(editing.id, selectedCodes)
      toast.success(data.message)
      setEditing(null)
      setSelectedCodes([])
      await load()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <DashboardLayout
        portal="platform"
        title="Platform Users"
        subtitle="Create staff who can sign in at /platform/login"
        breadcrumb="Platform Users"
        icon={Users}
        navItems={platformNavWithAudit}
      >
        <AdminListPanelShimmer />
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout
      portal="platform"
      title="Platform Users"
      subtitle="Create staff who can sign in at /platform/login"
      breadcrumb="Platform Users"
      icon={Users}
      navItems={platformNavWithAudit}
    >
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <AdminListPanel
        title="Platform staff"
        count={admins.length}
        description="Assign permissions when creating a user, or edit them later from this list. Owners always have full access."
        toolbar={
          <Button
            onClick={() => {
              setSelectedCodes([])
              setCreateOpen(true)
            }}
          >
            Create platform user
          </Button>
        }
      >
        <AdminDataTable columns={['Name', 'Email', 'Role', 'Permissions', 'Created', '']}>
          {admins.length === 0 ? (
            <AdminTableRow>
              <AdminTableCell className="text-slate-500">No platform users yet.</AdminTableCell>
              <AdminTableCell>—</AdminTableCell>
              <AdminTableCell>—</AdminTableCell>
              <AdminTableCell>—</AdminTableCell>
              <AdminTableCell>—</AdminTableCell>
              <AdminTableCell>—</AdminTableCell>
            </AdminTableRow>
          ) : (
            admins.map((admin) => (
              <AdminTableRow key={String(admin.id)}>
                <AdminTableCell className="font-medium text-gray-900">
                  {admin.user_name || '—'}
                </AdminTableCell>
                <AdminTableCell>{admin.user_email}</AdminTableCell>
                <AdminTableCell>{admin.is_owner ? 'Owner' : 'Admin'}</AdminTableCell>
                <AdminTableCell>
                  {admin.is_owner ? 'All' : admin.permissions.length || 'None'}
                </AdminTableCell>
                <AdminTableCell>{formatDate(admin.created_at)}</AdminTableCell>
                <AdminTableCell>
                  {canEditAdmin(admin) ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => openEdit(admin)}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      Edit permissions
                    </Button>
                  ) : (
                    <span className="text-xs text-slate-400">Full access</span>
                  )}
                </AdminTableCell>
              </AdminTableRow>
            ))
          )}
        </AdminDataTable>
      </AdminListPanel>

      <Dialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open)
          if (!open) {
            setCreatedPassword(null)
            setForm(emptyForm)
            setSelectedCodes([])
          }
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Create platform user</DialogTitle>
            <DialogDescription>
              Permissions are optional. You can leave them empty and edit them later from the list.
            </DialogDescription>
          </DialogHeader>

          {createdPassword ? (
            <div className="space-y-4">
              <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
                Temporary password: <span className="font-mono font-semibold">{createdPassword}</span>
              </p>
              <Button className="w-full" onClick={() => setCreateOpen(false)}>
                Done
              </Button>
            </div>
          ) : (
            <form className="space-y-4" onSubmit={handleCreate}>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="first_name">First name</Label>
                  <Input
                    id="first_name"
                    required
                    value={form.first_name}
                    onChange={(event) => setForm((current) => ({ ...current, first_name: event.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="last_name">Last name</Label>
                  <Input
                    id="last_name"
                    value={form.last_name}
                    onChange={(event) => setForm((current) => ({ ...current, last_name: event.target.value }))}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  required
                  value={form.email}
                  onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password (optional)</Label>
                <PasswordInput
                  id="password"
                  value={form.password}
                  onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                  placeholder="Leave blank to auto-generate"
                />
              </div>
              <div className="space-y-2">
                <Label>Permissions (optional)</Label>
                <p className="text-xs text-slate-500">Skip this now if you want to assign access later.</p>
                <PermissionPicker
                  grouped={groupedPermissions}
                  selectedCodes={selectedCodes}
                  onToggle={togglePermission}
                />
              </div>
              <Button type="submit" className="w-full" disabled={saving}>
                {saving ? 'Creating…' : 'Create user'}
              </Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditing(null)
            setSelectedCodes([])
          }
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit permissions</DialogTitle>
            <DialogDescription>
              {editing?.user_email
                ? `Choose what ${editing.user_email} can do in the platform console.`
                : 'Update this user’s platform access.'}
            </DialogDescription>
          </DialogHeader>
          <form className="space-y-4" onSubmit={handleUpdatePermissions}>
            <PermissionPicker
              grouped={groupedPermissions}
              selectedCodes={selectedCodes}
              onToggle={togglePermission}
            />
            <Button type="submit" className="w-full" disabled={saving}>
              {saving ? 'Saving…' : 'Save permissions'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  )
}
