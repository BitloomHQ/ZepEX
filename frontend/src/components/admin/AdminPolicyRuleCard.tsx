import { FileText, Pencil, Power, PowerOff } from 'lucide-react'
import type { PolicyRule } from '@/types'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/utils'

interface AdminPolicyRuleCardProps {
  rule: PolicyRule
  currency?: string
  disabled?: boolean
  onEdit?: () => void
  onToggleActive?: () => void
}

export function AdminPolicyRuleCard({
  rule,
  currency = 'USD',
  disabled,
  onEdit,
  onToggleActive,
}: AdminPolicyRuleCardProps) {
  const isActive = rule.is_active !== false

  return (
    <div className="grid w-full items-center gap-3 border-b border-[#e2e8f0] px-5 py-4 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_8rem_14rem] sm:gap-4 sm:px-6">
      <div className="flex min-w-0 items-start gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gray-100">
          <FileText className="h-5 w-5 text-gray-700" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold capitalize text-gray-900">
              {rule.category_name.replace(/_/g, ' ')}
            </p>
            {rule.company_role_name && (
              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                {rule.company_role_name}
              </span>
            )}
          </div>
          <p className="mt-0.5 line-clamp-2 text-sm text-gray-500">{rule.category_description}</p>
        </div>
      </div>
      <p className="text-lg font-bold text-gray-900 sm:text-right">
        {rule.is_unlimited
          ? 'Unlimited'
          : formatCurrency(rule.max_amount ?? 0, currency)}
      </p>
      <div className="flex items-center gap-1 sm:justify-end">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={onEdit}
          aria-label="Edit policy rule"
        >
          <Pencil className="h-3.5 w-3.5" />
          Edit
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={onToggleActive}
          aria-label={isActive ? 'Deactivate policy rule' : 'Activate policy rule'}
        >
          {isActive ? (
            <>
              <PowerOff className="h-3.5 w-3.5 text-red-600" />
              Deactivate
            </>
          ) : (
            <>
              <Power className="h-3.5 w-3.5 text-green-600" />
              Activate
            </>
          )}
        </Button>
      </div>
    </div>
  )
}
