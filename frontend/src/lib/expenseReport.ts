import type { ExpenseReport, Receipt } from '@/types'

type CurrentMonthReportResponse = Partial<ExpenseReport> & {
  report_id?: string
  no_violation_receipts?: Receipt[]
  violation_receipts?: Receipt[]
}

function reportReceipts(data: CurrentMonthReportResponse): Receipt[] {
  if (data.receipts?.length) {
    return data.receipts
  }
  return [...(data.no_violation_receipts ?? []), ...(data.violation_receipts ?? [])]
}

export function normalizeCurrentMonthReport(data: CurrentMonthReportResponse): ExpenseReport {
  return {
    ...data,
    id: String(data.id ?? data.report_id ?? ''),
    receipts: reportReceipts(data),
    workflow_timeline: data.workflow_timeline ?? [],
  } as ExpenseReport
}

function mergeReceiptsById(local: Receipt[], server: Receipt[]): Receipt[] {
  const byId = new Map(local.map((receipt) => [receipt.id, receipt]))
  for (const receipt of server) {
    byId.set(receipt.id, receipt)
  }
  return Array.from(byId.values())
}

export function mergeServerReportIntoReports(
  previous: ExpenseReport[],
  data: CurrentMonthReportResponse,
  userEmail?: string,
): ExpenseReport[] {
  const incoming = normalizeCurrentMonthReport(data)
  if (!incoming.id) {
    return previous
  }

  const normalized: ExpenseReport = {
    ...incoming,
    employee_email: incoming.employee_email || userEmail || '',
  }

  const existingIndex = previous.findIndex((report) => String(report.id) === String(normalized.id))
  if (existingIndex === -1) {
    return [normalized]
  }

  const existing = previous[existingIndex]
  const merged: ExpenseReport = {
    ...normalized,
    receipts: mergeReceiptsById(existing.receipts ?? [], normalized.receipts ?? []),
  }

  return previous.map((report, index) => (index === existingIndex ? merged : report))
}
