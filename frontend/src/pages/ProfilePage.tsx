import { Key, Pencil, Save, Trash2, Upload, User } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { changePassword, editProfile, getProfile } from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import { FormPageShimmer } from '@/components/ui/shimmer'
import { Textarea } from '@/components/ui/textarea'
import { UserAvatar } from '@/components/ui/user-avatar'
import { useAuth } from '@/context/AuthContext'
import { useAdminNav } from '@/hooks/useAdminNav'
import { getNavForUser, userRoleLabel } from '@/lib/dashboardNav'
import { toast } from '@/lib/toast'
import type { UserProfile } from '@/types'

function getFullName(first = '', last = '') {
  return `${first} ${last}`.trim()
}

function splitFullName(fullName: string) {
  const trimmed = fullName.trim()
  if (!trimmed) return { first_name: '', last_name: '' }
  const parts = trimmed.split(/\s+/)
  if (parts.length === 1) return { first_name: parts[0], last_name: '' }
  return { first_name: parts[0], last_name: parts.slice(1).join(' ') }
}

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function ProfileField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-sm font-medium text-gray-500">{label}</p>
      <p className="mt-1.5 text-sm leading-relaxed text-gray-900">{value || '—'}</p>
    </div>
  )
}

export function ProfilePage() {
  const { user, logout, refreshPermissions } = useAuth()
  const navigate = useNavigate()
  const { navItems: adminNavItems, ready: adminNavReady } = useAdminNav()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [editOpen, setEditOpen] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [profileForm, setProfileForm] = useState({
    full_name: '',
    phone_number: '',
    address: '',
  })
  const [passwordForm, setPasswordForm] = useState({
    old_password: '',
    new_password: '',
  })
  const [pictureFile, setPictureFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const navItems =
    user?.role === 'COMPANY_ADMIN' && adminNavReady
      ? adminNavItems
      : getNavForUser(user)

  const loadProfile = () =>
    getProfile()
      .then((res) => {
        setProfile(res.data)
        setProfileForm({
          full_name: getFullName(res.data.first_name, res.data.last_name),
          phone_number: res.data.phone_number || '',
          address: res.data.address || '',
        })
      })
      .catch(() => {
        setProfile(null)
        setProfileForm({
          full_name: getFullName(user?.first_name, user?.last_name),
          phone_number: '',
          address: '',
        })
      })

  useEffect(() => {
    loadProfile().finally(() => setLoading(false))
  }, [user?.first_name, user?.last_name])

  const resetEditForm = () => {
    setPictureFile(null)
    setDragOver(false)
    if (fileRef.current) fileRef.current.value = ''
    if (profile) {
      setProfileForm({
        full_name: getFullName(profile.first_name, profile.last_name),
        phone_number: profile.phone_number || '',
        address: profile.address || '',
      })
    }
  }

  const handleProfileSave = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const { first_name, last_name } = splitFullName(profileForm.full_name)
      const data = new FormData()
      if (first_name) data.append('first_name', first_name)
      if (last_name) data.append('last_name', last_name)
      if (profileForm.phone_number) data.append('phone_number', profileForm.phone_number)
      if (profileForm.address) data.append('address', profileForm.address)
      if (pictureFile) data.append('profile_picture', pictureFile)
      await editProfile(data)
      toast.success('Profile updated successfully.')
      setEditOpen(false)
      resetEditForm()
      const { data: updated } = await getProfile()
      setProfile(updated)
      setProfileForm({
        full_name: getFullName(updated.first_name, updated.last_name),
        phone_number: updated.phone_number || '',
        address: updated.address || '',
      })
      await refreshPermissions()
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handlePasswordChange = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const { data } = await changePassword(
        passwordForm.old_password,
        passwordForm.new_password,
      )
      setPasswordForm({ old_password: '', new_password: '' })
      setPasswordOpen(false)
      logout()
      navigate('/login', {
        state: {
          message: data.message || 'Password changed successfully. Please login again.',
        },
      })
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handlePictureSelect = (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    setPictureFile(file)
  }

  const picturePreviewUrl = useMemo(
    () => (pictureFile ? URL.createObjectURL(pictureFile) : null),
    [pictureFile],
  )

  useEffect(() => {
    return () => {
      if (picturePreviewUrl) URL.revokeObjectURL(picturePreviewUrl)
    }
  }, [picturePreviewUrl])

  if (loading || (user?.role === 'COMPANY_ADMIN' && !adminNavReady)) {
    return (
      <DashboardLayout
        title="Profile"
        breadcrumb="Profile"
        icon={User}
        navItems={getNavForUser(user)}
      >
        <FormPageShimmer fields={6} />
      </DashboardLayout>
    )
  }

  const email = profile?.email ?? user?.email ?? ''
  const role = userRoleLabel(user)
  const fullName = getFullName(
    profile?.first_name ?? user?.first_name,
    profile?.last_name ?? user?.last_name,
  )

  return (
    <DashboardLayout
      title={fullName || 'Profile'}
      breadcrumb="Profile"
      headerLeading={
        <UserAvatar
          src={profile?.profile_picture ?? user?.profile_picture}
          firstName={profile?.first_name ?? user?.first_name}
          lastName={profile?.last_name ?? user?.last_name}
          email={email}
          size="lg"
          className="shadow-sm"
        />
      }
      subtitle={`${email} · ${role}`}
      navItems={navItems}
    >
      {error && !editOpen && !passwordOpen && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="overflow-hidden rounded-xl border border-[#e2e8f0] bg-white shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e2e8f0] px-5 py-5 sm:px-6">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Profile Details</h2>
            <p className="mt-1 text-sm text-gray-500">
              You can view all of the profile settings here.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                resetEditForm()
                setError('')
                setEditOpen(true)
              }}
            >
              <Pencil className="h-4 w-4" />
              Edit Profile
            </Button>
            <Button
              type="button"
              onClick={() => {
                setPasswordForm({ old_password: '', new_password: '' })
                setError('')
                setPasswordOpen(true)
              }}
            >
              <Key className="h-4 w-4" />
              Change Password
            </Button>
          </div>
        </div>

        <div className="grid gap-6 px-5 py-6 sm:grid-cols-2 sm:px-6">
          <ProfileField label="Email Address" value={email} />
          <ProfileField label="Role" value={role} />
          <ProfileField label="Name" value={fullName} />
          <ProfileField label="Phone No" value={profileForm.phone_number} />
          <div className="sm:col-span-2">
            <ProfileField label="Address" value={profileForm.address} />
          </div>
        </div>
      </div>

      <Dialog
        open={editOpen}
        onOpenChange={(open) => {
          setEditOpen(open)
          if (!open) {
            resetEditForm()
            setError('')
          }
        }}
      >
        <DialogContent className="flex max-h-[min(90vh,720px)] w-[calc(100vw-2rem)] max-w-lg flex-col overflow-hidden p-6 sm:max-w-xl">
          <DialogHeader className="shrink-0">
            <DialogTitle>Edit Profile Details</DialogTitle>
            <DialogDescription>
              Update your personal information and manage your profile details easily.
            </DialogDescription>
          </DialogHeader>

          <form
            onSubmit={handleProfileSave}
            className="flex min-h-0 flex-1 flex-col overflow-hidden"
          >
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-1">
              {error && (
                <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Email Address</Label>
                  <Input value={email} disabled className="bg-gray-50" />
                </div>
                <div className="space-y-2">
                  <Label>Role</Label>
                  <Input value={role} disabled className="bg-gray-50" />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="full_name">Full Name*</Label>
                <Input
                  id="full_name"
                  value={profileForm.full_name}
                  onChange={(e) =>
                    setProfileForm({ ...profileForm, full_name: e.target.value })
                  }
                  placeholder="Enter your full name"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="phone_number">Phone*</Label>
                <Input
                  id="phone_number"
                  value={profileForm.phone_number}
                  onChange={(e) =>
                    setProfileForm({ ...profileForm, phone_number: e.target.value })
                  }
                  placeholder="+91 855241436"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="address">Address</Label>
                <Textarea
                  id="address"
                  value={profileForm.address}
                  onChange={(e) =>
                    setProfileForm({ ...profileForm, address: e.target.value })
                  }
                  placeholder="Enter your address"
                  rows={3}
                />
              </div>

              <div className="space-y-2">
                <Label>Profile picture</Label>
                <div className="flex items-center gap-4">
                  <UserAvatar
                    src={picturePreviewUrl ?? profile?.profile_picture}
                    firstName={profile?.first_name ?? user?.first_name}
                    lastName={profile?.last_name ?? user?.last_name}
                    email={email}
                    size="lg"
                  />
                  <p className="text-sm text-gray-500">
                    Upload a new photo or keep your current picture.
                  </p>
                </div>
                <div
                  className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center transition ${
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
                    handlePictureSelect(e.dataTransfer.files)
                  }}
                  onKeyDown={(e) => e.key === 'Enter' && fileRef.current?.click()}
                  role="button"
                  tabIndex={0}
                >
                  <Upload className="h-7 w-7 text-gray-400" />
                  <p className="mt-2 text-sm text-gray-600">
                    Choose a file or drag &amp; drop it here.
                  </p>
                  <p className="mt-1 text-xs text-gray-400">
                    PNG, JPG formats up to 10 MB
                  </p>
                  <span
                    className="mt-3 cursor-pointer text-sm font-medium text-primary hover:underline"
                    onClick={(e) => {
                      e.stopPropagation()
                      fileRef.current?.click()
                    }}
                  >
                    Browse File
                  </span>
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/png,image/jpeg,image/jpg"
                  className="hidden"
                  onChange={(e) => handlePictureSelect(e.target.files)}
                />
                {pictureFile && (
                  <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-gray-900">
                        {pictureFile.name}
                      </p>
                      <p className="text-xs text-gray-500">
                        Completed · {formatFileSize(pictureFile.size)} of 10 MB
                      </p>
                    </div>
                    <button
                      type="button"
                      className="rounded p-1 text-red-500 hover:bg-red-50"
                      onClick={() => {
                        setPictureFile(null)
                        if (fileRef.current) fileRef.current.value = ''
                      }}
                      aria-label="Remove file"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </div>
            </div>

            <DialogFooter className="mt-4 shrink-0 gap-2 border-t border-gray-100 pt-4 sm:justify-end">
              <Button type="submit" disabled={saving}>
                <Save className="h-4 w-4" />
                {saving ? 'Saving...' : 'Save Changes'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={passwordOpen}
        onOpenChange={(open) => {
          setPasswordOpen(open)
          if (!open) {
            setPasswordForm({ old_password: '', new_password: '' })
            setError('')
          }
        }}
      >
        <DialogContent className="max-w-md p-6">
          <DialogHeader>
            <DialogTitle>Change Password</DialogTitle>
            <DialogDescription>
              You will be logged out after changing your password.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handlePasswordChange} className="space-y-4">
            {error && (
              <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
            )}

            <div className="space-y-2">
              <Label htmlFor="old_password">Current Password*</Label>
              <PasswordInput
                id="old_password"
                value={passwordForm.old_password}
                onChange={(e) =>
                  setPasswordForm({ ...passwordForm, old_password: e.target.value })
                }
                placeholder="Enter your current password"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="new_password">New Password*</Label>
              <PasswordInput
                id="new_password"
                value={passwordForm.new_password}
                onChange={(e) =>
                  setPasswordForm({ ...passwordForm, new_password: e.target.value })
                }
                placeholder="Enter your new password"
                required
              />
            </div>

            <DialogFooter className="gap-2 sm:justify-end">
              <Button type="submit" disabled={saving}>
                <Key className="h-4 w-4" />
                {saving ? 'Updating...' : 'Update Password'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  )
}
