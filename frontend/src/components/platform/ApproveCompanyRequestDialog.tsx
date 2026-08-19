import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { AdminModalFooter } from '@/components/admin/AdminModalFooter'
import type { CompanyRegistrationRequest } from '@/types'

interface ApproveCompanyRequestDialogProps {
  request: CompanyRegistrationRequest | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (requestId: number) => void
  loading?: boolean
}

export function ApproveCompanyRequestDialog({
  request,
  open,
  onOpenChange,
  onConfirm,
  loading,
}: ApproveCompanyRequestDialogProps) {
  const unverified = request?.is_email_verified !== true

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Approve registration</DialogTitle>
          <DialogDescription>
            {request
              ? `Approve ${request.company_name} (${request.admin_email}).`
              : 'Approve this company registration.'}
          </DialogDescription>
        </DialogHeader>

        {unverified && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
            This admin email is not verified. Approving will mark it as verified and approve the
            company by admin.
          </div>
        )}

        <p className="text-sm text-gray-600">
          The company admin will receive a welcome email with login credentials.
        </p>

        <AdminModalFooter
          onCancel={() => onOpenChange(false)}
          cancelLabel="Cancel"
          submitLabel={unverified ? 'Mark verified and approve' : 'Approve request'}
          submitType="button"
          submitting={loading}
          onSubmit={() => {
            if (!request) return
            onConfirm(request.id)
          }}
        />
      </DialogContent>
    </Dialog>
  )
}
