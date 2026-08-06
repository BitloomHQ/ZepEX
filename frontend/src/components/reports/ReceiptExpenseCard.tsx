import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  ChevronDown,
  ExternalLink,
  Eye,
  FileText,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { LineItem, Receipt } from '@/types'
import { cn, formatCurrency, formatDate } from '@/lib/utils'
import {
  formatLineItemAmount,
  formatReceiptAmountDisplay,
  lineItemDisplayAmount,
  receiptDisplayCurrency,
  receiptExchangeRateHint,
} from '@/lib/receiptDisplay'
import {
  canRetryReceiptAi,
  canDeleteReceipt,
  isAiExtractionFailed,
  isAiExtractionPending,
  receiptDisplayTitle,
} from '@/lib/receiptAi'
import { resolveMediaUrl } from '@/lib/userDisplay'

function violationTags(receipt: Receipt) {
  const tags: string[] = []
  if (receipt.has_duplicate_violation) tags.push('Duplicate')
  if (receipt.has_old_bill_violation) tags.push('Old bill')
  if (receipt.has_amount_violation) tags.push('Over limit')
  return tags
}

function violationLines(receipt: Receipt): string[] {
  if (!receipt.policy_violation_reason) return []
  const unique = new Set<string>()
  for (const line of receipt.policy_violation_reason.split('\n')) {
    const trimmed = line.trim()
    if (trimmed) unique.add(trimmed)
  }
  return Array.from(unique)
}

function descriptionPreview(description: string | null | undefined): string {
  const trimmed = description?.trim()
  if (!trimmed) return '—'
  const firstLine = trimmed.split('\n')[0]?.trim() || trimmed
  return firstLine.length > 90 ? `${firstLine.slice(0, 87)}…` : firstLine
}

function fileNameFromUrl(url: string): string {
  try {
    const path = url.split('?')[0]
    const name = path.split('/').pop()
    return name ? decodeURIComponent(name) : 'Receipt file'
  } catch {
    return 'Receipt file'
  }
}

function isImageFile(url: string): boolean {
  return /\.(jpe?g|png|gif|webp|bmp)(\?|$)/i.test(url)
}

function isPdfFile(url: string): boolean {
  return /\.pdf(\?|$)/i.test(url)
}

function itemLabel(item: LineItem): string {
  return `${item.description || ''} ${item.subcategory || ''}`.trim().toLowerCase()
}

function isTaxLineItem(item: LineItem): boolean {
  return /tax|gst|cgst|sgst|igst|vat|hst|pst|sales t/.test(itemLabel(item))
}

function isTotalLineItem(item: LineItem): boolean {
  const label = itemLabel(item)
  if (label.includes('subtotal')) return false
  if (
    label === 'total' ||
    label === 'totals' ||
    /grand total|amount due|balance due|amount payable|total due|total amount|net payable/.test(
      label,
    )
  ) {
    return true
  }
  return /total\s*[—-]/.test(label) && /(parking fee|sales tax|gst|vat)/.test(label)
}

function itemAmountValue(item: LineItem): number {
  const value = Number(item.amount)
  return Number.isFinite(value) ? value : 0
}

function organizeLineItems(items: LineItem[]): { charges: LineItem[]; taxes: LineItem[] } {
  const charges: LineItem[] = []
  const taxes: LineItem[] = []

  const chronological = [...items].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )

  for (const item of chronological) {
    if (itemAmountValue(item) === 0) continue
    if (isTotalLineItem(item)) continue
    if (isTaxLineItem(item)) taxes.push(item)
    else charges.push(item)
  }

  const filteredCharges = charges.filter((item) => {
    const amount = itemAmountValue(item)
    const others = [...charges, ...taxes]
      .filter((candidate) => candidate.id !== item.id)
      .reduce((sum, candidate) => sum + itemAmountValue(candidate), 0)
    return !(others > 0 && Math.abs(amount - others) < 0.01)
  })

  return { charges: filteredCharges, taxes }
}

function sumDisplayAmounts(items: LineItem[], receipt: Receipt): number {
  return items.reduce((sum, item) => {
    const value = Number(lineItemDisplayAmount(item, receipt))
    return sum + (Number.isFinite(value) ? value : 0)
  }, 0)
}

interface ReceiptExpenseCardProps {
  receipt: Receipt
  canEdit?: boolean
  onDeleteLineItem?: (lineItemId: string) => void
  onDeleteReceipt?: (receiptId: string) => void
  onRetryReceipt?: (receiptId: string) => void
  retrying?: boolean
  deleting?: boolean
  defaultOpen?: boolean
}

export function ReceiptExpenseCard({
  receipt,
  canEdit = false,
  onDeleteLineItem,
  onDeleteReceipt,
  onRetryReceipt,
  retrying = false,
  deleting = false,
  defaultOpen = true,
}: ReceiptExpenseCardProps) {
  const [viewerOpen, setViewerOpen] = useState(false)
  const [open, setOpen] = useState(defaultOpen)

  const hasLineItems = receipt.line_items.length > 0
  const tags = violationTags(receipt)
  const violations = violationLines(receipt)
  const rateHint = receiptExchangeRateHint(receipt)
  const currency = receiptDisplayCurrency(receipt)
  const showOriginalAmount =
    hasLineItems &&
    Boolean(receipt.original_currency) &&
    Boolean(receipt.company_currency) &&
    receipt.original_currency !== receipt.company_currency
  const showViolations = hasLineItems && receipt.has_any_violation

  const receiptUrl = useMemo(
    () => resolveMediaUrl(receipt.receipt_file),
    [receipt.receipt_file],
  )

  const { charges, taxes } = useMemo(
    () => organizeLineItems(receipt.line_items),
    [receipt.line_items],
  )
  const ledgerRows = useMemo(
    () => [
      ...charges.map((item) => ({ item, kind: 'charge' as const })),
      ...taxes.map((item) => ({ item, kind: 'tax' as const })),
    ],
    [charges, taxes],
  )

  const subtotal = useMemo(() => sumDisplayAmounts(charges, receipt), [charges, receipt])
  const taxTotal = useMemo(() => sumDisplayAmounts(taxes, receipt), [taxes, receipt])
  const linesTotal = subtotal + taxTotal
  const claimAmount = Number(receipt.company_amount ?? receipt.total_amount ?? 0)
  // Prefer ledger math when lines exist so UI never shows inflated stored amounts.
  const displayClaimAmount = ledgerRows.length > 0 ? linesTotal : claimAmount
  const linesMatchClaim =
    Number.isFinite(claimAmount) && claimAmount > 0 && ledgerRows.length > 0
      ? Math.abs(linesTotal - claimAmount) < 0.02
      : true

  const panelId = `receipt-panel-${receipt.id}`

  return (
    <article
      className={cn(
        'overflow-hidden rounded-2xl border bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow',
        showViolations ? 'border-amber-200/90' : 'border-slate-200',
        open && 'shadow-[0_8px_24px_rgba(15,23,42,0.06)]',
      )}
    >
      <header className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <button
          type="button"
          className="-m-1 min-w-0 flex-1 rounded-xl p-1 text-left outline-none transition-colors hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-primary/30 sm:-m-1.5 sm:p-1.5"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
        >
          <div className="flex items-start gap-3">
            <span
              className={cn(
                'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-500 transition-transform',
                open && 'rotate-0 bg-blue-50 text-primary',
              )}
            >
              <ChevronDown
                className={cn('h-4 w-4 transition-transform', !open && '-rotate-90')}
                aria-hidden
              />
            </span>

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="truncate text-[15px] font-semibold tracking-tight text-slate-900">
                  {receiptDisplayTitle(receipt)}
                </h3>
                {!open && showViolations && (
                  <Badge variant="warning" className="font-medium">
                    Needs review
                  </Badge>
                )}
              </div>
              <p className="mt-0.5 text-sm text-slate-500">
                {receipt.invoice_date ? formatDate(receipt.invoice_date) : 'No invoice date'}
                {ledgerRows.length > 0
                  ? ` · ${ledgerRows.length} line${ledgerRows.length === 1 ? '' : 's'}`
                  : ''}
                {currency ? ` · ${currency}` : ''}
              </p>

              <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                {!hasLineItems ? (
                  <span className="text-sm text-slate-500">No claim lines yet</span>
                ) : isAiExtractionFailed(receipt) ? (
                  <span className="text-sm text-amber-700">Extraction incomplete</span>
                ) : (
                  <>
                    <span className="text-xl font-semibold tracking-tight text-slate-900">
                      {formatCurrency(
                        Number.isFinite(displayClaimAmount) ? displayClaimAmount : 0,
                        currency,
                      )}
                    </span>
                    {showOriginalAmount && (
                      <span className="text-xs text-slate-500">
                        from {formatReceiptAmountDisplay(receipt).split('→')[0]?.trim()}
                      </span>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </button>

        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          {receiptUrl && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="border-slate-200 bg-white"
              onClick={(event) => {
                event.stopPropagation()
                setViewerOpen(true)
              }}
            >
              <Eye className="h-3.5 w-3.5" />
              Receipt
            </Button>
          )}
          <StatusBadge status={receipt.status} />
          {canEdit && canRetryReceiptAi(receipt) && onRetryReceipt && (
            <Button
              size="sm"
              variant="outline"
              className="border-slate-200"
              disabled={retrying || deleting}
              onClick={(event) => {
                event.stopPropagation()
                onRetryReceipt(receipt.id)
              }}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${retrying ? 'animate-spin' : ''}`} />
              Retry
            </Button>
          )}
          {canEdit && canDeleteReceipt(receipt) && onDeleteReceipt && (
            <Button
              size="sm"
              variant="outline"
              className="border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
              disabled={deleting || retrying}
              onClick={(event) => {
                event.stopPropagation()
                onDeleteReceipt(receipt.id)
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              {deleting ? 'Deleting…' : 'Delete'}
            </Button>
          )}
        </div>
      </header>

      {open && (
        <div id={panelId} className="border-t border-slate-100">
          {isAiExtractionPending(receipt) ? (
            <div className="mx-4 my-4 rounded-xl border border-blue-100 bg-blue-50/80 px-4 py-3 text-sm text-blue-900 sm:mx-5">
              <div className="flex items-center gap-2 font-medium">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-500" />
                </span>
                Reading receipt — line items will appear shortly
              </div>
            </div>
          ) : null}

          {isAiExtractionFailed(receipt) ? (
            <div className="mx-4 my-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 sm:mx-5">
              <div className="flex gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <p>
                  {receipt.ai_error_message ||
                    'AI extraction failed. Retry or upload a clearer receipt.'}
                </p>
              </div>
            </div>
          ) : null}

          {showViolations && (violations.length > 0 || tags.length > 0) && (
            <div className="mx-4 mt-4 rounded-xl border border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50/40 px-4 py-3 sm:mx-5">
              <div className="flex flex-wrap items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-700" />
                <p className="text-sm font-semibold text-amber-950">Policy review required</p>
                {tags.map((tag) => (
                  <Badge
                    key={tag}
                    variant="outline"
                    className="border-amber-300/80 bg-white/80 text-amber-900"
                  >
                    {tag}
                  </Badge>
                ))}
              </div>
              {violations.length > 0 && (
                <ul className="mt-2 space-y-1 text-sm text-amber-900/90">
                  {violations.slice(0, 3).map((line) => (
                    <li key={line} className="flex gap-2">
                      <span className="text-amber-500">•</span>
                      <span>{line}</span>
                    </li>
                  ))}
                  {violations.length > 3 && (
                    <li className="text-xs text-amber-700">
                      +{violations.length - 3} more policy note
                      {violations.length - 3 === 1 ? '' : 's'}
                    </li>
                  )}
                </ul>
              )}
            </div>
          )}

          <div className="p-4 sm:p-5">
            {ledgerRows.length > 0 ? (
              <div className="overflow-hidden rounded-xl border border-slate-200">
                <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-slate-50/90 px-4 py-2.5">
                  <p className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                    Expense ledger
                  </p>
                  {rateHint && (
                    <p className="max-w-[18rem] truncate text-right text-[11px] text-slate-500">
                      {rateHint}
                    </p>
                  )}
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[36rem] text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-[0.06em] text-slate-400">
                        <th className="px-4 py-2.5 font-medium">Description</th>
                        <th className="px-3 py-2.5 font-medium">Category</th>
                        <th className="px-3 py-2.5 font-medium">Type</th>
                        <th className="px-3 py-2.5 font-medium">Date</th>
                        <th className="px-4 py-2.5 text-right font-medium">Amount</th>
                        {canEdit && <th className="w-12 px-2 py-2.5" aria-label="Actions" />}
                      </tr>
                    </thead>
                    <tbody>
                      {ledgerRows.map(({ item, kind }, index) => (
                        <tr
                          key={item.id}
                          className={cn(
                            'border-b border-slate-100 last:border-b-0',
                            kind === 'tax' ? 'bg-slate-50/40' : 'bg-white',
                          )}
                        >
                          <td className="px-4 py-3 align-top">
                            <div className="flex items-start gap-2">
                              <span className="mt-0.5 text-[11px] font-medium text-slate-400">
                                {String(index + 1).padStart(2, '0')}
                              </span>
                              <div className="min-w-0">
                                <p className="font-medium text-slate-900">
                                  {descriptionPreview(
                                    item.subcategory || item.description || item.category,
                                  )}
                                </p>
                                {item.subcategory &&
                                  item.description &&
                                  item.description.trim().toLowerCase() !==
                                    item.subcategory.trim().toLowerCase() && (
                                    <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
                                      {descriptionPreview(item.description)}
                                    </p>
                                  )}
                                {item.is_violating && (
                                  <p className="mt-1 text-xs font-medium text-amber-700">
                                    {item.violation_reason || 'Flagged for policy review'}
                                  </p>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="px-3 py-3 align-top capitalize text-slate-600">
                            {item.category.replace(/_/g, ' ')}
                          </td>
                          <td className="px-3 py-3 align-top">
                            <div className="flex flex-col items-start gap-1">
                              <span
                                className={cn(
                                  'inline-flex rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide',
                                  kind === 'tax'
                                    ? 'bg-violet-50 text-violet-700'
                                    : 'bg-emerald-50 text-emerald-700',
                                )}
                              >
                                {kind === 'tax' ? 'Tax' : 'Charge'}
                              </span>
                              {item.is_violating && (
                                <span className="inline-flex rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-800">
                                  Review
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="whitespace-nowrap px-3 py-3 align-top text-slate-500">
                            {item.bill_date ? formatDate(item.bill_date) : '—'}
                          </td>
                          <td className="px-4 py-3 text-right align-top font-semibold tabular-nums text-slate-900">
                            {formatLineItemAmount(item, receipt)}
                          </td>
                          {canEdit && (
                            <td className="px-2 py-3 align-top">
                              {onDeleteLineItem && (
                                <Button
                                  type="button"
                                  size="icon"
                                  variant="ghost"
                                  className="h-8 w-8 text-slate-400 hover:bg-red-50 hover:text-red-600"
                                  onClick={() => onDeleteLineItem(item.id)}
                                  aria-label="Remove line item"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              )}
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="border-t border-slate-200 bg-slate-50/70 px-4 py-3">
                  <dl className="ml-auto w-full max-w-xs space-y-1.5 text-sm">
                    <div className="flex items-center justify-between gap-6 text-slate-600">
                      <dt>Subtotal</dt>
                      <dd className="tabular-nums font-medium text-slate-800">
                        {formatCurrency(subtotal, currency)}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-6 text-slate-600">
                      <dt>Tax</dt>
                      <dd className="tabular-nums font-medium text-slate-800">
                        {formatCurrency(taxTotal, currency)}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-6 border-t border-slate-200 pt-2 text-slate-900">
                      <dt className="font-semibold">Total</dt>
                      <dd className="text-base font-semibold tabular-nums">
                        {formatCurrency(linesTotal, currency)}
                      </dd>
                    </div>
                  </dl>
                  {!linesMatchClaim && (
                    <p className="mt-2 text-right text-[11px] text-amber-700">
                      Refreshing claim total to match line items…
                    </p>
                  )}
                </div>
              </div>
            ) : isAiExtractionPending(receipt) ? (
              <div className="rounded-xl border border-dashed border-blue-200 bg-blue-50/40 px-4 py-8 text-center">
                <p className="text-sm font-medium text-blue-900">Building expense ledger…</p>
              </div>
            ) : isAiExtractionFailed(receipt) ? (
              <p className="text-sm text-amber-700">
                {receipt.ai_error_message ||
                  'Could not extract expense details. Retry AI or upload a clearer receipt.'}
              </p>
            ) : (
              <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-4 py-8 text-center text-sm text-slate-500">
                No reimbursable lines on this receipt yet.
              </div>
            )}
          </div>
        </div>
      )}

      {receiptUrl && (
        <Dialog open={viewerOpen} onOpenChange={setViewerOpen}>
          <DialogContent className="max-h-[90vh] max-w-4xl overflow-hidden p-0 sm:max-w-4xl">
            <DialogHeader className="border-b border-slate-200 px-5 py-4">
              <DialogTitle>Uploaded receipt</DialogTitle>
              <DialogDescription className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span>{fileNameFromUrl(receiptUrl)}</span>
                <a
                  href={receiptUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
                >
                  Open in new tab
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </DialogDescription>
            </DialogHeader>

            <div className="max-h-[min(70vh,40rem)] overflow-auto bg-slate-50 p-4">
              {isImageFile(receiptUrl) ? (
                <img
                  src={receiptUrl}
                  alt={`Receipt from ${receiptDisplayTitle(receipt)}`}
                  className="mx-auto max-h-[min(65vh,36rem)] w-auto max-w-full rounded-lg object-contain shadow-sm"
                />
              ) : isPdfFile(receiptUrl) ? (
                <iframe
                  title="Receipt PDF"
                  src={receiptUrl}
                  className="h-[min(65vh,36rem)] w-full rounded-lg border border-slate-200 bg-white"
                />
              ) : (
                <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-slate-200 bg-white px-6 py-16 text-center">
                  <FileText className="h-10 w-10 text-slate-400" />
                  <p className="text-sm text-slate-500">
                    Preview is not available for this file type. Open it in a new tab instead.
                  </p>
                  <Button asChild variant="outline">
                    <a href={receiptUrl} target="_blank" rel="noreferrer">
                      Open file
                    </a>
                  </Button>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </article>
  )
}
