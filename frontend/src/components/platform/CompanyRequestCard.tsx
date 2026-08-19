import { Calendar, User } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { CompanyRegistrationRequest } from '@/types'
import { cn } from '@/lib/utils'

const requestStatusVariant = {
  PENDING: 'warning',
  APPROVED: 'success',
  REJECTED: 'destructive',
} as const

const requestStatusLabel = {
  PENDING: 'Pending',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
} as const

function formatRequestDateTime(date: string) {
  const value = new Date(date)
  const day = value.getDate()
  const month = value.toLocaleString('en-US', { month: 'short' })
  const year = value.getFullYear()
  const time = value
    .toLocaleString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    })
    .replace(/\s/g, '')
  return `${day} ${month} ${year}, ${time}`
}

interface CompanyRequestCardProps {
  request: CompanyRegistrationRequest
  actionId: number | null
  onApprove: (id: number) => void
  onReject: (id: number) => void
}

export function CompanyRequestCard({
  request,
  actionId,
  onApprove,
  onReject,
}: CompanyRequestCardProps) {
  const isPending = request.status === 'PENDING'
  const emailVerified = request.is_email_verified === true
  const canApprove = isPending && request.company_name !== 'PENDING'
  const busy = actionId === request.id
  const approveTooltip =
    isPending && !canApprove ? 'Registration details are incomplete.' : undefined

  return (
    <article className="rounded-xl border border-[#e2e8f0] bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={requestStatusVariant[request.status]}>
              {requestStatusLabel[request.status]}
            </Badge>
            <Badge variant={emailVerified ? 'success' : 'destructive'}>
              {emailVerified
                ? request.email_verified_via === 'ADMIN'
                  ? 'Email verified by admin'
                  : 'Email verified through email'
                : 'Email not verified'}
            </Badge>
          </div>
          <h3 className="mt-3 text-xl font-bold text-gray-900">{request.company_name}</h3>
          <p className="mt-1 text-sm text-gray-500">{request.admin_email}</p>
          <p className="mt-1 text-sm text-gray-500">{request.company_domain}</p>
          {request.status === 'REJECTED' && request.reject_reason && (
            <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
              <span className="font-medium">Rejection reason:</span> {request.reject_reason}
            </p>
          )}
        </div>

        <div className="flex w-full flex-col gap-4 lg:w-auto lg:min-w-[15rem] lg:items-end">
          <div className="space-y-2 text-sm text-gray-600">
            <div className="flex items-center gap-2 lg:justify-end">
              <Calendar className="h-4 w-4 shrink-0 text-[#0066FF]" aria-hidden />
              <span>{formatRequestDateTime(request.created_at)}</span>
            </div>
            <div className="flex items-center gap-2 lg:justify-end">
              <User className="h-4 w-4 shrink-0 text-[#0066FF]" aria-hidden />
              <span>
                Admin: <span className="font-medium text-gray-900">{request.admin_name}</span>
              </span>
            </div>
          </div>

          {isPending && (
            <div className="flex flex-wrap gap-3 lg:justify-end">
              {approveTooltip ? (
                <TooltipProvider delayDuration={200}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="inline-flex cursor-not-allowed">
                        <Button
                          type="button"
                          variant="secondary"
                          aria-disabled
                          className={cn(
                            'min-w-[7.5rem] rounded-lg bg-[#E8EAE9] text-gray-900 opacity-50 hover:bg-[#E8EAE9]',
                            'cursor-not-allowed',
                          )}
                          onClick={(event) => event.preventDefault()}
                        >
                          Approve
                        </Button>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-center">
                      {approveTooltip}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              ) : (
                <Button
                  type="button"
                  variant="secondary"
                  className={cn(
                    'min-w-[7.5rem] rounded-lg bg-[#E8EAE9] text-gray-900 hover:bg-gray-200',
                  )}
                  disabled={busy}
                  onClick={() => onApprove(request.id)}
                >
                  Approve
                </Button>
              )}
              <Button
                type="button"
                variant="destructive"
                className="min-w-[7.5rem] rounded-lg"
                disabled={busy}
                onClick={() => onReject(request.id)}
              >
                Reject
              </Button>
            </div>
          )}
        </div>
      </div>
    </article>
  )
}
