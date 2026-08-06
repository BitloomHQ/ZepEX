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
import { formatDate } from '@/lib/utils'
import {
  formatLineItemAmount,
  formatReceiptAmountDisplay,
  receiptExchangeRateHint,
  receiptDisplayCurrency,
} from '@/lib/receiptDisplay'
import { formatCurrency } from '@/lib/utils'
import {
  canRetryReceiptAi,
  isAiExtractionFailed,
  isAiExtractionPending,
  receiptDisplayTitle,
} from '@/lib/receiptAi'
import { resolveMediaUrl } from '@/lib/userDisplay'

function violationTags(receipt: Receipt) {
  const tags: string[] = []
  if (receipt.has_duplicate_violation) tags.push('Duplicate receipt')
  if (receipt.has_old_bill_violation) tags.push('Old bill')
  if (receipt.has_amount_violation) tags.push('Over policy limit')
  return tags
}

function violationLines(receipt: Receipt): string[] {
  if (!receipt.policy_violation_reason) return []
  return receipt.policy_violation_reason
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

/** Split dense AI descriptions into readable lines when numbered. */
function descriptionLines(description: string | null | undefined): string[] {
  const trimmed = description?.trim()
  if (!trimmed) return []

  if (trimmed.includes('\n')) {
    return trimmed
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
  }

  const numbered = trimmed
    .split(/(?=\d+[.)]\s+)/)
    .map((part) => part.trim())
    .filter(Boolean)

  if (numbered.length > 1) {
    return numbered.map((part) => part.replace(/^\d+[.)]\s*/, '').trim()).filter(Boolean)
  }

  return [trimmed]
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
  const label = itemLabel(item)
  return /tax|gst|cgst|sgst|igst|vat|hst|pst|sales t/.test(label)
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
  // Old AI bug: whole receipt summary dumped into one row including "Total —".
  return (
    (/total\s*[—-]/.test(label) &&
      /(parking fee|sales tax|gst|vat)/.test(label)) ||
    false
  )
}

function itemAmountValue(item: LineItem): number {
  const value = Number(item.amount)
  return Number.isFinite(value) ? value : 0
}

/** Display sequence matching a printed receipt: charges → taxes. Drop totals/zeros. */
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

  // Drop a leftover "total" row whose amount equals charges + taxes (old for/else bug).
  const componentSum = [...charges, ...taxes].reduce((sum, item) => sum + itemAmountValue(item), 0)
  const filteredCharges = charges.filter((item) => {
    const amount = itemAmountValue(item)
    if (componentSum <= 0) return true
    // If this charge alone equals the sum of remaining components, it's a duplicate total.
    const others = [...charges, ...taxes]
      .filter((candidate) => candidate.id !== item.id)
      .reduce((sum, candidate) => sum + itemAmountValue(candidate), 0)
    return !(others > 0 && Math.abs(amount - others) < 0.01)
  })

  return { charges: filteredCharges, taxes }
}

function LineItemRow({
  item,
  index,
  receipt,
  canEdit,
  onDeleteLineItem,
}: {
  item: LineItem
  index: number
  receipt: Receipt
  canEdit: boolean
  onDeleteLineItem?: (lineItemId: string) => void
}) {
  const lines = descriptionLines(item.description)
  return (
    <li className="rounded-lg border border-[#e2e8f0] bg-[#fafbfc] px-3.5 py-3 sm:px-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">#{index}</span>
            <Badge variant="secondary" className="capitalize">
              {(item.subcategory || item.category).replace(/_/g, ' ')}
            </Badge>
            {item.bill_date && (
              <span className="text-xs text-muted-foreground">{formatDate(item.bill_date)}</span>
            )}
          </div>

          {lines.length > 1 ? (
            <ul className="space-y-1.5 text-sm leading-relaxed text-gray-800">
              {lines.map((line) => (
                <li key={line} className="flex gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-gray-400" />
                  <span className="break-words">{line}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-gray-800">
              {lines[0] || '—'}
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-start gap-2">
          <span className="pt-0.5 text-sm font-semibold text-gray-900">
            {formatLineItemAmount(item, receipt)}
          </span>
          {canEdit && onDeleteLineItem && (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-8 w-8 text-red-500 hover:bg-red-50 hover:text-red-600"
              onClick={() => onDeleteLineItem(item.id)}
              aria-label="Remove line item"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </li>
  )
}

interface ReceiptExpenseCardProps {
  receipt: Receipt
  canEdit?: boolean
  onDeleteLineItem?: (lineItemId: string) => void
  onRetryReceipt?: (receiptId: string) => void
  retrying?: boolean
  defaultOpen?: boolean
}

export function ReceiptExpenseCard({
  receipt,
  canEdit = false,
  onDeleteLineItem,
  onRetryReceipt,
  retrying = false,
  defaultOpen = true,
}: ReceiptExpenseCardProps) {
  const [viewerOpen, setViewerOpen] = useState(false)
  const [open, setOpen] = useState(defaultOpen)
  const hasLineItems = receipt.line_items.length > 0
  const tags = violationTags(receipt)
  const violations = violationLines(receipt)
  const rateHint = receiptExchangeRateHint(receipt)
  const showOriginalAmount =
    hasLineItems &&
    receipt.original_currency &&
    receipt.company_currency &&
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
  const displayItems = [...charges, ...taxes]
  const lineItemCount = displayItems.length
  const panelId = `receipt-panel-${receipt.id}`
  const receiptTotalLabel = formatCurrency(
    receipt.company_amount ?? receipt.total_amount,
    receiptDisplayCurrency(receipt),
  )

  return (
    <article className="overflow-hidden rounded-xl border border-[#e2e8f0] bg-white shadow-sm">
      <header
        className={`flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-5 ${
          open ? 'border-b border-[#e2e8f0]' : ''
        }`}
      >
        <button
          type="button"
          className="min-w-0 flex-1 rounded-md text-left outline-none transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 -m-1 p-1 sm:-m-1.5 sm:p-1.5"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
        >
          <div className="flex items-start gap-2">
            <ChevronDown
              className={`mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform ${
                open ? 'rotate-0' : '-rotate-90'
              }`}
              aria-hidden
            />
            <FileText className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
            <div className="min-w-0">
              <h3 className="font-semibold text-gray-900">{receiptDisplayTitle(receipt)}</h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {receipt.invoice_date ? `Invoice date · ${formatDate(receipt.invoice_date)}` : 'Receipt'}
                {lineItemCount > 0 ? ` · ${lineItemCount} line item${lineItemCount === 1 ? '' : 's'}` : ''}
                {!open && showViolations ? ' · Policy issue' : ''}
              </p>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 pl-6">
            {!hasLineItems ? (
              <span className="text-sm text-muted-foreground">All line items removed</span>
            ) : isAiExtractionFailed(receipt) ? (
              <span className="text-sm text-muted-foreground">Amount pending extraction</span>
            ) : (
              <>
                <span className="text-lg font-semibold text-gray-900">
                  {formatReceiptAmountDisplay(receipt)}
                </span>
                {showOriginalAmount && rateHint && (
                  <span className="text-xs text-muted-foreground">{rateHint}</span>
                )}
              </>
            )}
          </div>
        </button>

        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          {receiptUrl && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={(event) => {
                event.stopPropagation()
                setViewerOpen(true)
              }}
            >
              <Eye className="h-3.5 w-3.5" />
              View receipt
            </Button>
          )}
          {showViolations && (
            <Badge variant="destructive" className="gap-1">
              <AlertTriangle className="h-3 w-3" />
              Policy issue
            </Badge>
          )}
          <StatusBadge status={receipt.status} />
          {canEdit && canRetryReceiptAi(receipt) && onRetryReceipt && (
            <Button
              size="sm"
              variant="outline"
              disabled={retrying}
              onClick={(event) => {
                event.stopPropagation()
                onRetryReceipt(receipt.id)
              }}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${retrying ? 'animate-spin' : ''}`} />
              Retry AI
            </Button>
          )}
        </div>
      </header>

      {open && (
        <div id={panelId}>
          {isAiExtractionPending(receipt) ? (
            <div className="border-b border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-900 sm:px-5">
              <div className="flex items-center gap-2 font-medium">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-500" />
                </span>
                Extracting vendor, amounts, and line items…
              </div>
            </div>
          ) : isAiExtractionFailed(receipt) ? (
            <div className="border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 sm:px-5">
              <div className="flex items-center gap-2 font-medium">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                {receipt.ai_error_message ||
                  'AI extraction failed. Retry or upload a clearer receipt.'}
              </div>
            </div>
          ) : null}

          {showViolations && (violations.length > 0 || tags.length > 0) && (
            <div className="border-b border-amber-200 bg-amber-50/80 px-4 py-3 sm:px-5">
              {violations.length > 0 && (
                <ul className="space-y-1 text-sm text-amber-900">
                  {violations.map((line) => (
                    <li key={line} className="flex gap-2">
                      <span className="text-amber-600">•</span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              )}
              {tags.length > 0 && (
                <div className={`flex flex-wrap gap-1.5 ${violations.length > 0 ? 'mt-2' : ''}`}>
                  {tags.map((tag) => (
                    <Badge
                      key={tag}
                      variant="outline"
                      className="border-amber-300 bg-white text-amber-900"
                    >
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="px-4 py-4 sm:px-5">
            {displayItems.length > 0 ? (
              <div className="space-y-4">
                {charges.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        1. Line items
                      </p>
                      <p className="text-xs text-muted-foreground">{charges.length}</p>
                    </div>
                    <ul className="space-y-3">
                      {charges.map((item, index) => (
                        <LineItemRow
                          key={item.id}
                          item={item}
                          index={index + 1}
                          receipt={receipt}
                          canEdit={canEdit}
                          onDeleteLineItem={onDeleteLineItem}
                        />
                      ))}
                    </ul>
                  </div>
                )}

                {taxes.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        2. Taxes
                      </p>
                      <p className="text-xs text-muted-foreground">{taxes.length}</p>
                    </div>
                    <ul className="space-y-3">
                      {taxes.map((item, index) => (
                        <LineItemRow
                          key={item.id}
                          item={item}
                          index={charges.length + index + 1}
                          receipt={receipt}
                          canEdit={canEdit}
                          onDeleteLineItem={onDeleteLineItem}
                        />
                      ))}
                    </ul>
                  </div>
                )}

                <div className="flex items-center justify-between rounded-lg border border-[#e2e8f0] bg-white px-3.5 py-3 sm:px-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    3. Total
                  </p>
                  <p className="text-base font-semibold text-gray-900">{receiptTotalLabel}</p>
                </div>
              </div>
            ) : isAiExtractionPending(receipt) ? (
              <div className="space-y-2 rounded-lg border border-dashed border-blue-200 bg-blue-50/50 px-4 py-6 text-center">
                <p className="text-sm font-medium text-blue-900">Reading your receipt</p>
                <p className="text-xs text-blue-700">
                  Line items will appear here automatically when extraction finishes.
                </p>
              </div>
            ) : isAiExtractionFailed(receipt) ? (
              <p className="text-sm text-amber-700">
                {receipt.ai_error_message ||
                  'Could not extract expense details. Retry AI or upload a clearer receipt.'}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                No expenses on this receipt. Upload a new receipt or retry AI to extract again.
              </p>
            )}
          </div>
        </div>
      )}

      {receiptUrl && (
        <Dialog open={viewerOpen} onOpenChange={setViewerOpen}>
          <DialogContent className="max-h-[90vh] max-w-4xl overflow-hidden p-0 sm:max-w-4xl">
            <DialogHeader className="border-b border-[#e2e8f0] px-5 py-4">
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

            <div className="max-h-[min(70vh,40rem)] overflow-auto bg-muted/30 p-4">
              {isImageFile(receiptUrl) ? (
                <img
                  src={receiptUrl}
                  alt={`Receipt from ${receiptDisplayTitle(receipt)}`}
                  className="mx-auto max-h-[min(65vh,36rem)] w-auto max-w-full rounded-md object-contain shadow-sm"
                />
              ) : isPdfFile(receiptUrl) ? (
                <iframe
                  title="Receipt PDF"
                  src={receiptUrl}
                  className="h-[min(65vh,36rem)] w-full rounded-md border border-[#e2e8f0] bg-white"
                />
              ) : (
                <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-[#e2e8f0] bg-white px-6 py-16 text-center">
                  <FileText className="h-10 w-10 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
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
