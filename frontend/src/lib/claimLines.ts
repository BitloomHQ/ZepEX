import type { LineItem, Receipt } from '@/types'

/** Prefer API `claim_lines`, then `line_items`. */
export function getReceiptLineItems(receipt: Receipt): LineItem[] {
  return receipt.claim_lines ?? receipt.line_items ?? []
}

export function isActiveLineItem(item: LineItem): boolean {
  return !item.is_removed && !item.is_deleted
}

export function getActiveLineItems(receipt: Receipt): LineItem[] {
  return getReceiptLineItems(receipt).filter(isActiveLineItem)
}

export function getRemovedLineItems(receipt: Receipt): LineItem[] {
  return getReceiptLineItems(receipt).filter((item) => item.is_removed && !item.is_deleted)
}
