import { Check, Circle, Clock, X } from 'lucide-react'
import type { WorkflowTimelineEntry } from '@/types'
import { formatDateTime } from '@/lib/utils'
import { cn } from '@/lib/utils'

const statusStyles: Record<string, string> = {
  COMPLETED: 'text-emerald-600',
  APPROVED: 'text-emerald-600',
  AUTO_APPROVED: 'text-emerald-600',
  PAID: 'text-emerald-600',
  PENDING: 'text-blue-600',
  PENDING_PAYMENT: 'text-blue-600',
  VIEW_ONLY: 'text-gray-500',
  WAITING: 'text-gray-400',
  REJECTED: 'text-red-600',
  CANCELLED: 'text-gray-400',
  DRAFT: 'text-gray-500',
}

function isCompletedStatus(status: string) {
  return status === 'COMPLETED' || status === 'APPROVED' || status === 'PAID' || status === 'AUTO_APPROVED'
}

function isActiveStatus(status: string) {
  return status === 'PENDING' || status === 'PENDING_PAYMENT'
}

function StepNode({ status, size = 'md' }: { status: string; size?: 'sm' | 'md' }) {
  const dim = size === 'sm' ? 'h-5 w-5' : 'h-7 w-7'
  const iconDim = size === 'sm' ? 'h-3 w-3' : 'h-4 w-4'

  if (status === 'REJECTED') {
    return (
      <div
        className={cn(
          dim,
          'flex shrink-0 items-center justify-center rounded-full bg-red-500 text-white',
        )}
      >
        <X className={iconDim} strokeWidth={3} />
      </div>
    )
  }

  if (status === 'VIEW_ONLY') {
    return (
      <div
        className={cn(
          dim,
          'flex shrink-0 items-center justify-center rounded-full border-2 border-gray-300 bg-gray-50 text-gray-500',
        )}
      >
        <Circle className={iconDim} />
      </div>
    )
  }

  if (isActiveStatus(status)) {
    return (
      <div
        className={cn(
          dim,
          'flex shrink-0 items-center justify-center rounded-full border-2 border-blue-500 bg-blue-50 text-blue-600',
        )}
      >
        <Clock className={iconDim} />
      </div>
    )
  }

  if (isCompletedStatus(status)) {
    return (
      <div
        className={cn(
          dim,
          'flex shrink-0 items-center justify-center rounded-full bg-emerald-500 text-white',
        )}
      >
        <Check className={iconDim} strokeWidth={3} />
      </div>
    )
  }

  return (
    <div
      className={cn(
        dim,
        'flex shrink-0 items-center justify-center rounded-full border-2 border-gray-300 bg-white',
      )}
    >
      <Circle className={cn(iconDim, 'text-gray-300')} />
    </div>
  )
}

interface WorkflowProgressProps {
  timeline: WorkflowTimelineEntry[]
  variant?: 'compact' | 'detailed'
}

const auditTimelineStatuses = new Set([
  'LINE_ITEM_REMOVED',
  'LINE_ITEM_RESTORED',
  'LINE_ITEM_UPDATED',
])

function workflowStepsOnly(timeline: WorkflowTimelineEntry[]) {
  return timeline.filter((entry) => !auditTimelineStatuses.has(entry.status))
}

export function WorkflowProgress({ timeline, variant = 'detailed' }: WorkflowProgressProps) {
  const displayTimeline = variant === 'compact' ? workflowStepsOnly(timeline) : timeline

  if (!displayTimeline.length) {
    return variant === 'compact' ? (
      <span className="text-xs text-muted-foreground">—</span>
    ) : null
  }

  if (variant === 'compact') {
    return (
      <div className="flex items-center" aria-label="Workflow progress">
        {displayTimeline.map((entry, index) => {
          const completed = isCompletedStatus(entry.status)
          const isLast = index === displayTimeline.length - 1

          return (
            <div key={`${entry.step_order}-${entry.step_name}-${index}`} className="flex items-center">
              <StepNode status={entry.status} size="sm" />
              {!isLast && (
                <div
                  className={cn('h-0.5 w-5', completed ? 'bg-emerald-500' : 'bg-gray-200')}
                />
              )}
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div className="rounded-lg border bg-muted/20 p-4">
      <p className="mb-4 text-sm font-semibold text-foreground">Workflow progress</p>
      <div className="flex w-full items-start">
        {displayTimeline.map((entry, index) => {
          const completed = isCompletedStatus(entry.status)
          const isLast = index === displayTimeline.length - 1
          const nextCompleted = isCompletedStatus(displayTimeline[index + 1]?.status ?? '')

          return (
            <div
              key={`${entry.step_order}-${entry.step_name}-${index}`}
              className="flex min-w-0 flex-1 flex-col items-center"
            >
              <div className="flex w-full items-center">
                {index > 0 && (
                  <div
                    className={cn(
                      'h-0.5 flex-1',
                      completed || isActiveStatus(entry.status) ? 'bg-emerald-500' : 'bg-gray-200',
                    )}
                  />
                )}
                <StepNode status={entry.status} />
                {!isLast && (
                  <div
                    className={cn(
                      'h-0.5 flex-1',
                      completed && nextCompleted ? 'bg-emerald-500' : completed ? 'bg-emerald-500' : 'bg-gray-200',
                    )}
                  />
                )}
              </div>
              <div className="mt-3 w-full px-1 text-center">
                <p className="text-xs font-medium text-foreground sm:text-sm">{entry.step_name}</p>
                <p className={cn('mt-0.5 text-[10px] font-medium uppercase sm:text-xs', statusStyles[entry.status] ?? 'text-gray-400')}>
                  {entry.status}
                </p>
                {entry.action_by && (
                  <p className="mt-1 text-[10px] text-muted-foreground sm:text-xs">
                    {entry.action_by} · {entry.action_role}
                  </p>
                )}
                {!entry.action_by && entry.action_role && (
                  <p className="mt-1 text-[10px] text-muted-foreground sm:text-xs">
                    {entry.action_role}
                  </p>
                )}
                {entry.comments && (
                  <p className="mt-1 text-[10px] text-muted-foreground sm:text-xs">
                    “{entry.comments}”
                  </p>
                )}
                {entry.action_at && (
                  <p className="mt-1 text-[10px] text-muted-foreground sm:text-xs">
                    {formatDateTime(entry.action_at)}
                  </p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** @deprecated Use WorkflowProgress */
export function WorkflowTimeline({ timeline }: { timeline: WorkflowTimelineEntry[] }) {
  return <WorkflowProgress timeline={timeline} variant="detailed" />
}
