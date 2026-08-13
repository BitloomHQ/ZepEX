import { useState } from 'react'
import { copyRolePolicy } from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminModalFooter } from '@/components/admin/AdminModalFooter'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { toast } from '@/lib/toast'
import type { CompanyRole } from '@/types'

const selectClassName =
  'flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm'

interface PolicyToolsPanelProps {
  roles: CompanyRole[]
  disabled?: boolean
  onCopied?: () => void
}

export function PolicyToolsPanel({
  roles,
  disabled,
  onCopied,
}: PolicyToolsPanelProps) {
  const [copyOpen, setCopyOpen] = useState(false)
  const [copyFromRoleId, setCopyFromRoleId] = useState<number | ''>('')
  const [copyToRoleId, setCopyToRoleId] = useState<number | ''>('')
  const [overwriteExisting, setOverwriteExisting] = useState(false)
  const [copyLoading, setCopyLoading] = useState(false)

  const activeRoles = roles.filter((role) => role.is_active !== false)

  const handleCopy = async () => {
    if (!copyFromRoleId || !copyToRoleId) {
      toast.error('Select both source and destination roles.')
      return
    }

    if (copyFromRoleId === copyToRoleId) {
      toast.error('Source and destination roles must be different.')
      return
    }

    setCopyLoading(true)
    try {
      const { data } = await copyRolePolicy({
        from_role: copyFromRoleId,
        to_role: copyToRoleId,
        overwrite_existing: overwriteExisting,
      })
      toast.success(
        `${data.message} Copied ${data.copied}, updated ${data.updated}, skipped ${data.skipped}.`,
      )
      setCopyOpen(false)
      onCopied?.()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setCopyLoading(false)
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        disabled={disabled}
        onClick={() => setCopyOpen(true)}
      >
        Copy policy
      </Button>

      <Dialog open={copyOpen} onOpenChange={setCopyOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Copy policy</DialogTitle>
            <DialogDescription>
              Copy all rules from one role to another.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="copy-from">From role</Label>
              <select
                id="copy-from"
                className={selectClassName}
                value={copyFromRoleId}
                onChange={(e) => setCopyFromRoleId(e.target.value ? Number(e.target.value) : '')}
                disabled={disabled || copyLoading}
              >
                <option value="">Select role</option>
                {activeRoles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="copy-to">To role</Label>
              <select
                id="copy-to"
                className={selectClassName}
                value={copyToRoleId}
                onChange={(e) => setCopyToRoleId(e.target.value ? Number(e.target.value) : '')}
                disabled={disabled || copyLoading}
              >
                <option value="">Select role</option>
                {activeRoles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={overwriteExisting}
                onChange={(e) => setOverwriteExisting(e.target.checked)}
                disabled={disabled || copyLoading}
              />
              Overwrite existing rules
            </label>
            <AdminModalFooter
              onCancel={() => setCopyOpen(false)}
              submitLabel={copyLoading ? 'Copying…' : 'Copy policy'}
              submitting={copyLoading}
              submitDisabled={disabled}
              submitType="button"
              onSubmit={handleCopy}
            />
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
