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
  READY: 'default',
  EXPORTED: 'secondary',
  CONFIRMED: 'success',
  CANCELLED: 'muted',
  RUNNING: 'warning',
  PROCESSING: 'warning',
  VERIFIED: 'success',
  MISMATCH: 'destructive',
  MISSING: 'destructive',
  ERROR: 'destructive',
  NOT_CHECKED: 'muted',
  HEALTHY: 'success',
  WARNING: 'warning',
  UNHEALTHY: 'destructive',
  QUEUED_AFTER_COMMIT: 'warning',
  CONNECTED: 'success',
  NOT_CONNECTED: 'muted',
  CREATED: 'success',
  UPDATED: 'default',
  ACTIVATED: 'success',
  DEACTIVATED: 'muted',
  MANAGER_CHANGED: 'default',
  DEPARTMENT_CHANGED: 'default',
  Active: 'success',
  Inactive: 'muted',
  UNKNOWN: 'muted',
}

export function StatusBadge({ status }: { status: string }) {
  const label = status.replace(/_/g, ' ')
  return (
    <Badge variant={statusVariant[status] ?? 'secondary'} className="capitalize">
      {label.toLowerCase()}
    </Badge>
  )
}
