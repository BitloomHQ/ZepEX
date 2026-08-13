import { useEffect, useState, type FormEvent } from 'react'
import { getCompanyPolicySettings, updateCompanyPolicySettings } from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminModalFooter } from '@/components/admin/AdminModalFooter'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/lib/toast'
import { formatDateTime } from '@/lib/utils'
import type { CompanyPolicySettings } from '@/types'

interface CompanyPolicySettingsPanelProps {
  onCancel: () => void
  onSaved?: (policy: CompanyPolicySettings) => void
}

export function CompanyPolicySettingsPanel({
  onCancel,
  onSaved,
}: CompanyPolicySettingsPanelProps) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [policy, setPolicy] = useState<CompanyPolicySettings | null>(null)
  const [oldBillLimitDays, setOldBillLimitDays] = useState('90')
  const [autoApprove, setAutoApprove] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const { data } = await getCompanyPolicySettings()
        setPolicy(data.policy)
        setOldBillLimitDays(String(data.policy.old_bill_limit_days))
        setAutoApprove(data.policy.auto_approve_if_no_violation)
        setError('')
      } catch (err) {
        setError(getApiErrorMessage(err))
      } finally {
        setLoading(false)
      }
    }

    void load()
  }, [])

  const handleSave = async (event: FormEvent) => {
    event.preventDefault()

    const parsedDays = Number.parseInt(oldBillLimitDays, 10)
    if (!Number.isFinite(parsedDays) || parsedDays < 1) {
      setError('Old bill limit must be at least 1 day.')
      return
    }

    setSaving(true)
    setError('')
    try {
      const { data } = await updateCompanyPolicySettings({
        old_bill_limit_days: parsedDays,
        auto_approve_if_no_violation: autoApprove,
      })
      setPolicy(data.policy)
      setOldBillLimitDays(String(data.policy.old_bill_limit_days))
      setAutoApprove(data.policy.auto_approve_if_no_violation)
      toast.success(data.message || 'Policy settings updated.')
      onSaved?.(data.policy)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="text-sm text-gray-500">Loading policy settings…</p>
  }

  return (
    <form onSubmit={handleSave} className="space-y-4">
      <p className="text-sm text-gray-500">
        Receipts older than the limit are flagged as policy violations when validated.
      </p>

      {policy?.updated_at && (
        <p className="text-xs text-gray-400">Updated {formatDateTime(policy.updated_at)}</p>
      )}

      <div className="space-y-2">
        <Label htmlFor="old-bill-limit-days">Old bill limit (days)</Label>
        <Input
          id="old-bill-limit-days"
          type="number"
          min={1}
          max={3650}
          value={oldBillLimitDays}
          disabled={saving}
          onChange={(event) => setOldBillLimitDays(event.target.value)}
        />
      </div>

      <label className="flex items-center gap-2 text-sm text-gray-700">
        <input
          type="checkbox"
          checked={autoApprove}
          disabled={saving}
          onChange={(event) => setAutoApprove(event.target.checked)}
        />
        Auto-approve reports with no policy violations
      </label>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <AdminModalFooter
        onCancel={onCancel}
        submitLabel="Save policy settings"
        submitting={saving}
        submitDisabled={saving}
      />
    </form>
  )
}
