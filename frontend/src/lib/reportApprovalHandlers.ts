import {
  approveReceipt,
  rejectReceipt,
  removeReportLineItem,
  restoreReportLineItem,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { toast } from '@/lib/toast'
import type { ReportApprovalContext } from '@/types'

export function createReportApprovalContext(
  reportId: string,
  options: {
    enabled: boolean
    busy: boolean
    onRefresh: () => Promise<void>
  },
): ReportApprovalContext {
  const run = async (request: () => Promise<{ data: { message: string } }>) => {
    try {
      const { data } = await request()
      toast.success(data.message)
      await options.onRefresh()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
      throw err
    }
  }

  return {
    enabled: options.enabled,
    busy: options.busy,
    onApproveReceipt: (receiptId, notes) =>
      run(() => approveReceipt(reportId, receiptId, notes)),
    onRejectReceipt: (receiptId, notes) =>
      run(() => rejectReceipt(reportId, receiptId, notes)),
    onRemoveLineItem: (lineItemId, reason) =>
      run(() => removeReportLineItem(reportId, lineItemId, reason)),
    onRestoreLineItem: (lineItemId, notes) =>
      run(() => restoreReportLineItem(reportId, lineItemId, notes)),
  }
}
