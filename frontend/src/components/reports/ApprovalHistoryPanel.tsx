import type { ApprovalHistoryEntry } from '@/types'
import { formatDateTime } from '@/lib/utils'

const ACTION_LABELS: Record<string, string> = {
  REPORT_SUBMITTED: 'Report submitted',
  STEP_APPROVED: 'Step approved',
  STEP_REJECTED: 'Step rejected',
  RECEIPT_APPROVED: 'Receipt approved',
  RECEIPT_REJECTED: 'Receipt rejected',
  LINE_ITEM_UPDATED: 'Line item updated',
  LINE_ITEM_REMOVED: 'Line item removed',
  LINE_ITEM_RESTORED: 'Line item restored',
  PAID: 'Marked as paid',
}

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action.replace(/_/g, ' ').toLowerCase()
}

function actorLabel(entry: ApprovalHistoryEntry): string {
  return entry.action_by_email || entry.action_by_role || entry.action_by || 'System'
}

interface ApprovalHistoryPanelProps {
  history: ApprovalHistoryEntry[]
}

export function ApprovalHistoryPanel({ history }: ApprovalHistoryPanelProps) {
  if (!history.length) return null

  const sorted = [...history].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-2.5">
        <p className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
          Approval history
        </p>
      </div>
      <ul className="divide-y divide-slate-100">
        {sorted.map((entry, index) => (
          <li key={entry.id ?? `${entry.action}-${entry.created_at}-${index}`} className="px-4 py-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-sm font-medium text-slate-900">{actionLabel(entry.action)}</p>
              <p className="text-xs text-slate-500">{formatDateTime(entry.created_at)}</p>
            </div>
            <p className="mt-0.5 text-xs text-slate-500">{actorLabel(entry)}</p>
            {entry.comments?.trim() && (
              <p className="mt-1.5 text-sm text-slate-700">{entry.comments}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
