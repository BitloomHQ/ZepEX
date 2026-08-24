import { Badge } from '@/components/ui/badge'

const statusVariant: Record<string, 'default' | 'success' | 'warning' | 'destructive' | 'muted' | 'secondary'> = {
  PENDING: 'warning',
  PENDING_APPROVAL: 'warning',
  APPROVED: 'success',
  REJECTED: 'destructive',
  SUBMITTED: 'default',
  SUBMITTED_TO_MANAGER: 'default',
  PENDING_ACCOUNTS: 'warning',
  ACCOUNTS_APPROVED: 'success',
  PAID: 'success',
  AI_PROCESSED: 'secondary',
  AI_PROCESSING: 'warning',
  AI_FAILED: 'destructive',
  AI_RETRY_REQUIRED: 'warning',
  POLICY_VIOLATION: 'destructive',
  DRAFT: 'muted',
  ACTIVE: 'success',
  INACTIVE: 'muted',
  MANAGER: 'default',
  EMPLOYEE: 'secondary',
  ACCOUNTS: 'secondary',
  COMPANY_ADMIN: 'default',
  SUCCESS: 'success',
  FAILED: 'destructive',
}

export function StatusBadge({ status }: { status: string }) {
  const label = status.replace(/_/g, ' ')
  return (
    <Badge variant={statusVariant[status] ?? 'secondary'} className="capitalize">
      {label.toLowerCase()}
    </Badge>
  )
}
