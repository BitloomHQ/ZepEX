export type UserRole =
  | 'PLATFORM_OWNER'
  | 'PLATFORM_ADMIN'
  | 'COMPANY_ADMIN'
  | 'MANAGER'
  | 'EMPLOYEE'
  | 'ACCOUNTS'

export interface UserPermissions {
  can_upload_receipt: boolean
  can_submit_expense: boolean
  can_approve_expense: boolean
  can_mark_paid: boolean
  can_manage_users?: boolean
  can_manage_policy?: boolean
  can_manage_workflow?: boolean
  can_view_all_reports?: boolean
  can_view_audit_logs?: boolean
}

export interface Company {
  id: string
  name: string
}

export interface Department {
  id: string
  name: string
}

export interface User {
  id: number
  email: string
  first_name: string
  last_name: string
  role: UserRole
  system_role?: UserRole
  company_role?: string | null
  company_role_id?: number | null
  permissions?: UserPermissions
  company: Company | null
  department: Department | null
  profile_picture?: string | null
}

export interface LoginResponse {
  message: string
  token: string
  user: {
    id: number
    email: string
    first_name: string
    last_name: string
    system_role: UserRole
    company_role?: string | null
    company_role_id?: number | null
    permissions?: UserPermissions
    company: Company | null
    department: Department | null
  }
  redirect_to: string
}

export interface UserProfile {
  id: number
  email: string
  first_name: string
  last_name: string
  role: UserRole
  company_role?: string | null
  company_role_id?: number | null
  company: string
  department: string
  phone_number: string | null
  address: string | null
  profile_picture: string | null
  permissions?: UserPermissions
}

export interface CompanyRole {
  id: number
  name: string
  can_upload_receipt: boolean
  can_submit_expense: boolean
  can_approve_expense: boolean
  can_mark_paid: boolean
  is_active: boolean
  created_at: string
}

export interface CompanyRegistrationRequest {
  id: number
  company_name: string
  company_domain: string
  admin_name: string
  admin_email: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  expected_employee_count?: number
  is_email_verified?: boolean
  reject_reason?: string | null
  created_at: string
}

export interface ApproveCompanyRequestResponse {
  success: boolean
  message: string
  company_id: string
  admin_email: string
  temporary_password: string
  reimbursement_email?: string
  platform_receipt_email?: string
  forwarding_instruction?: string
}

export interface RejectCompanyRequestResponse {
  success: boolean
  message: string
  company_name: string
  admin_email: string
  reject_reason: string
}

export interface CreateEmployeeResponse {
  message: string
  invite_email_sent: boolean
  invite_status: 'SENT' | 'FAILED'
  email_error?: string | null
  employee: EmployeeRecord
}

export interface PlatformPermission {
  id: number
  name: string
  code: string
  module: string
}

export interface PlatformAdminUser {
  id: number | string
  company: string | null
  user: number
  user_name: string
  user_email: string
  is_owner: boolean
  is_active: boolean
  permissions: string[]
  created_at: string
}

export interface CreatePlatformUserResponse {
  message: string
  temporary_password: string | null
  password_generated: boolean
  data: PlatformAdminUser
}

export interface DepartmentRecord {
  id: string
  name: string
  manager: string | null
  manager_name?: string | null
  is_active?: boolean
  created_at: string
}

export interface EmployeeRecord {
  id: number
  email: string
  first_name: string
  last_name: string
  company: string
  department: string | null
  department_name?: string
  role: UserRole
  company_role?: number | null
  company_role_name?: string
  phone_number?: string | null
  address?: string | null
  is_active?: boolean
  created_at: string
  profile_picture?: string | null
}

export interface PolicyRule {
  id: string
  policy?: string
  company_role: number
  company_role_name: string
  category_name: string
  max_amount: string | null
  currency?: string
  is_unlimited?: boolean
  effective_limit?: string
  category_description: string
  is_active: boolean
  updated_at?: string
}

export interface PolicyRuleMutationResponse {
  message: string
  rule: PolicyRule
}

export interface EffectivePolicyRule {
  id: string
  category: string
  limit: string
  description: string
  source_role: string
  inherited: boolean
}

export interface PolicyPreviewResponse {
  company_role: { id: string; name: string }
  total_rules: number
  rules: EffectivePolicyRule[]
}

export interface PolicySimulateResponse {
  company_role: string
  allowed: boolean
  entered_amount: string
  limit?: string
  category?: string
  source_role?: string
  inherited?: boolean
  violation?: boolean
  reason?: string
}

export interface PolicyCopyResponse {
  message: string
  from_role: string
  to_role: string
  copied: number
  updated: number
  skipped: number
  overwrite_existing: boolean
}

export type PolicyDocumentImportStatus =
  | 'UPLOADED'
  | 'PROCESSING'
  | 'REVIEW_REQUIRED'
  | 'IMPORTED'
  | 'FAILED'

export interface PolicyDocumentUploadResponse {
  success: boolean
  message: string
  import_id: string
  status: PolicyDocumentImportStatus
  preview: Record<string, unknown>
}

export interface PolicyDocumentImportRecord {
  id: string
  filename: string
  status: PolicyDocumentImportStatus
  uploaded_by?: string | null
  error_message?: string | null
  created_at?: string
  updated_at?: string
}

export interface PolicyDocumentPreviewResponse {
  import: PolicyDocumentImportRecord
  preview: Record<string, unknown>
  warnings: unknown[]
  conflicts: unknown[]
}

export interface PolicyDocumentUpdatePreviewResponse {
  message: string
  import_id: string
  status: PolicyDocumentImportStatus
  preview: Record<string, unknown>
}

export interface PolicyDocumentRevalidateResponse {
  message: string
  import_id: string
  status: PolicyDocumentImportStatus
  is_valid_for_import: boolean
  validation_error_count: number
  warning_count: number
  conflict_count: number
  preview: Record<string, unknown>
}

export interface PolicyDocumentConfirmImportResponse {
  success: boolean
  message: string
  import_id: string
  policy_id: string
  policy_version: {
    id: string
    version_number: number
    title: string
    status: string
    is_active: boolean
    activated_at?: string | null
  }
  previous_version: {
    id: string
    version_number: number
    status: string
    is_active: boolean
  } | null
  status: PolicyDocumentImportStatus
  summary: {
    created: number
    updated: number
    unchanged?: number
    skipped: number
    failed: number
    non_monetary_skipped?: number
    duplicates_skipped?: number
    review_required_skipped?: number
    processed?: number
    cloned_from_previous_version?: number
    total_rules_in_new_version?: number
  }
  warnings: unknown[]
  errors: unknown[]
  rules: unknown[]
}

export interface PolicyVersion {
  id: string
  version_number: number
  title: string
  description?: string
  status: string
  is_active?: boolean
  activated_at?: string | null
}

export interface PolicyVersionsListResponse {
  count: number
  active_version: PolicyVersion | null
  results: PolicyVersion[]
}

export interface WorkflowSimulateStep {
  step_order: number
  status: string
  approver_type?: string
  approver?: string
  email?: string
  reason?: string
}

export interface WorkflowSimulateResponse {
  success: boolean
  error?: string
  employee?: {
    id: string
    name: string
    email: string
    company_role: string | null
    department: string | null
    reporting_manager: string | null
  }
  simulation?: {
    workflow_name: string
    start_role: string
    total_steps: number
    steps_skipped: number
    flow: WorkflowSimulateStep[]
  }
}

export interface ApprovalWorkflowStep {
  id: string
  workflow?: string
  step_order: number
  approver_type?: string
  approver_type_name?: string
  approver_role: number | null
  approver_role_name: string
  specific_user?: string | null
  specific_user_name?: string | null
  specific_user_email?: string | null
  department: string | null
  department_name: string | null
  routing_type: 'DEPARTMENT' | 'COMPANY'
  is_active: boolean
  created_at: string
}

export interface ApprovalWorkflow {
  id: string
  company: string
  name: string
  start_role: number
  start_role_name?: string
  is_active: boolean
  steps: ApprovalWorkflowStep[]
  created_at: string
  updated_at: string
}

export interface ApprovalWorkflowListResponse {
  count: number
  workflows: ApprovalWorkflow[]
}

export interface LineItem {
  id: string
  receipt?: string
  description: string
  category: string
  subcategory?: string
  vendor: string
  amount: string
  bill_date: string
  is_violating: boolean
  violation_reason: string | null
  is_removed?: boolean
  removed_by?: string | null
  removed_at?: string | null
  removal_reason?: string | null
  is_deleted?: boolean
  deleted_at?: string | null
  deleted_by?: string | null
  created_at: string
}

export interface Receipt {
  id: string
  report: string
  submission: string
  company: string
  employee: number
  employee_email: string
  department: string
  department_name: string
  receipt_file: string
  vendor_name: string | null
  invoice_date: string | null
  total_amount: string
  currency: string
  original_amount?: string | null
  original_currency?: string | null
  company_amount?: string | null
  company_currency?: string | null
  exchange_rate?: string | null
  exchange_rate_date?: string | null
  exchange_rate_provider?: string | null
  ai_status?: string | null
  ai_error_message?: string | null
  ai_retry_count?: number
  status: string
  policy_violation_reason: string | null
  has_duplicate_violation: boolean
  has_old_bill_violation: boolean
  has_amount_violation: boolean
  has_any_violation: boolean
  line_items: LineItem[]
  /** Frontend-friendly alias of line_items from the API. */
  claim_lines?: LineItem[]
  created_at: string
  updated_at: string
}

export interface WorkflowTimelineEntry {
  step_order: number
  step_name: string
  status: string
  action_by: string | null
  action_role: string
  comments: string | null
  action_at?: string | null
}

export interface ReportCurrentStep {
  id?: string
  step_order: number
  approver_type?: string
  approver_role: string
  routing_type: 'DEPARTMENT' | 'COMPANY' | 'ANY'
  department: string | null
  specific_user?: string | null
}

export type ApprovalHistoryAction =
  | 'REPORT_SUBMITTED'
  | 'STEP_APPROVED'
  | 'STEP_REJECTED'
  | 'RECEIPT_APPROVED'
  | 'RECEIPT_REJECTED'
  | 'LINE_ITEM_UPDATED'
  | 'LINE_ITEM_REMOVED'
  | 'LINE_ITEM_RESTORED'
  | 'PAID'

export interface ApprovalHistoryEntry {
  id?: string
  report?: string
  receipt?: string | null
  action: ApprovalHistoryAction | string
  action_by?: string | null
  action_by_email?: string | null
  action_by_role?: string | null
  comments?: string | null
  created_at: string
}

export interface ReportApprovalContext {
  enabled: boolean
  busy?: boolean
  onApproveReceipt: (receiptId: string, notes?: string) => Promise<void>
  onRejectReceipt: (receiptId: string, notes: string) => Promise<void>
  onRemoveLineItem: (lineItemId: string, reason: string) => Promise<void>
  onRestoreLineItem: (lineItemId: string, notes?: string) => Promise<void>
}

export interface LatestRejectionReason {
  rejected_by: string
  role: string
  reason: string
  rejected_at: string
}

export interface ExpenseReport {
  id: string
  company: string
  employee: number
  employee_email: string
  employee_name?: string
  employee_profile_picture?: string | null
  department: string
  department_name: string
  month: string
  status: string
  total_amount: string
  /** Company reimbursement currency from finance settings. */
  company_currency?: string
  is_auto_approved?: boolean
  auto_approved_at?: string | null
  approval_type?: string | null
  approval_required?: boolean
  view_only_for_workflow?: boolean
  submitted_at: string | null
  paid_at: string | null
  paid_notes?: string | null
  current_workflow_step?: string | null
  current_step?: ReportCurrentStep | null
  workflow_timeline?: WorkflowTimelineEntry[]
  approval_history?: ApprovalHistoryEntry[]
  latest_rejection_reason?: LatestRejectionReason | null
  workflow_completed?: boolean
  receipts: Receipt[]
  created_at: string
  updated_at: string
}

export interface ApproveReportResponse {
  message: string
  approved_by: string
  workflow_completed?: boolean
  steps_skipped?: number
  is_company_admin_override?: boolean
  next_step?: {
    id?: string
    step_order: number
    approver_type?: string
    approver_type_name?: string
    approver_role?: string | null
    role?: string
    routing_type: string
    department: string | null
    specific_user?: string | null
    next_approver?: {
      id: string
      name: string
      email: string
    }
  }
  status?: string
  report: ExpenseReport
}

export interface RejectReportResponse {
  message: string
  rejected_by: string
  workflow_completed?: boolean
  is_company_admin_override?: boolean
  status: string
  report: ExpenseReport
}

export interface MarkPaidReportResponse {
  message: string
  previous_status?: string
  paid_by: string
  is_company_admin_override?: boolean
  report: ExpenseReport
}

export interface ApproveReceiptResponse {
  message: string
  approved?: boolean
  receipt_id?: string
  status: string
  notes?: string
  receipt?: {
    id: string
    status: string
  }
}

export interface RejectReceiptResponse {
  message: string
  rejected?: boolean
  receipt_id?: string
  status: string
  reason: string
  receipt?: {
    id: string
    status: string
  }
}

export interface RemoveLineItemResponse {
  message: string
  removed?: boolean
  line_item_id?: string
  receipt_id?: string
  category?: string
  subcategory?: string
  reason?: string
  status?: {
    is_removed: boolean
    is_deleted: boolean
  }
  line_item?: LineItem
  receipt?: Pick<Receipt, 'id' | 'original_amount' | 'company_amount' | 'total_amount'>
}

export interface RestoreLineItemResponse {
  message: string
  restored?: boolean
  line_item_id?: string
  receipt_id?: string
  removed?: boolean
  line_item?: LineItem
  receipt?: Pick<Receipt, 'id' | 'original_amount' | 'company_amount' | 'total_amount'>
}

export interface AddWorkflowStepResponse {
  message: string
  step: ApprovalWorkflowStep
}

export interface DeactivateWorkflowStepResponse {
  message: string
  workflow_steps_reordered: boolean
}

export interface DeleteWorkflowResponse {
  message: string
}

export interface UpdateWorkflowStepResponse {
  message: string
  step: {
    id: string
    step_order: number
    approver_role: { id: string; name: string } | number
    routing_type: 'DEPARTMENT' | 'COMPANY'
    department: string | null
    is_active: boolean
    created_at: string
  }
}

export interface PendingApprovalsResponse {
  count: number
  filters: Record<string, string | null>
  results: ExpenseReport[]
}

export interface AdminReportsResponse {
  count: number
  total_pages: number
  current_page: number
  filters: Record<string, string | null>
  results: ExpenseReport[]
}

export interface AuditLogEntry {
  id: string
  company: string
  company_name?: string
  action: string
  message: string
  metadata: Record<string, unknown>
  action_by?: number | null
  action_by_email: string
  created_at: string
}

export interface MyUploadedExpensesResponse {
  count: number
  filters: Record<string, string | null>
  results: ExpenseReport[]
}

export interface DuplicateReceiptLog {
  id: string
  original_receipt: string
  duplicate_receipt: string
  duplicate_type: 'SAME_EMPLOYEE' | 'CROSS_EMPLOYEE'
  original_employee_email: string
  duplicate_employee_email: string
  original_vendor: string
  duplicate_vendor: string
  created_at: string
}

export interface DuplicateReceiptsResponse {
  count: number
  filters?: { type?: string | null }
  results: DuplicateReceiptLog[]
}

export interface ReimbursementEmailConfigData {
  company_name: string
  reimbursement_email: string | null
  platform_receipt_email: string
  forwarding_instruction: string
  imap_required?: boolean
  imap_removed?: boolean
}

export interface ReimbursementEmailConfigResponse {
  success: boolean
  message?: string
  data: ReimbursementEmailConfigData
}

export interface PlatformEmailServiceStatus {
  smtp_source?: string
  company_smtp_required?: boolean
  company_smtp_removed?: boolean
  from_email?: string
  provider?: string
  outgoing_email?: string
  smtp_configured?: boolean
  email_forwarding_required?: boolean
  platform_receipt_email?: string
}

export interface PlatformEmailServiceResponse {
  success: boolean
  message?: string
  data?: PlatformEmailServiceStatus
  email_service?: PlatformEmailServiceStatus
}

export interface CsvImportError {
  row: number
  message: string
}

export interface CsvImportResult {
  success?: boolean
  created?: number
  updated?: number
  skipped?: number
  errors?: CsvImportError[]
}

export interface CsvTemplateInfo {
  success: boolean
  template_name: string
  description: string
  required_columns: string[]
  sample_data?: Record<string, string>[]
  allowed_roles?: string[]
  supported_categories?: string[]
}

export interface PlatformCompanySummary {
  id: string
  name: string
  domain: string
  reimbursement_email_prefix?: string
  is_verified: boolean
  is_active?: boolean
  created_at: string
}

export interface PlatformCompanyDetailsResponse {
  company: PlatformCompanySummary
  filters: Record<string, string | number | null>
  departments?: import('@/lib/pagination').PaginatedResponse<DepartmentRecord>
  employees?: import('@/lib/pagination').PaginatedResponse<EmployeeRecord>
  roles?: import('@/lib/pagination').PaginatedResponse<CompanyRole>
  policy_rules?: import('@/lib/pagination').PaginatedResponse<PolicyRule>
  workflow?: ApprovalWorkflow | null
}

export interface EmployeeInviteResult {
  success: boolean
  message?: string
  sent: number
  failed: number
  skipped_already_sent?: number
  errors?: Array<{ employee: string; error: string }>
}

export interface UploadPolicyResult {
  success: boolean
  has_violations?: boolean
  violations?: string[]
  next_status?: string
  policy_currency?: string
}

export interface CurrencyConversionResult {
  success: boolean
  company_amount?: number | string
  company_currency?: string
  exchange_rate?: number | string
  exchange_rate_provider?: string
  error?: string
}

export interface UploadAiResult {
  success?: boolean | null
  pending?: boolean
  retry_allowed?: boolean
  ai_status?: string
  error?: string
  receipt_id?: string
  line_items_created?: string[]
  total_amount?: number | string
  original_amount?: number | string
  original_currency?: string
  company_amount?: number | string
  company_currency?: string
  exchange_rate?: number | string
  exchange_rate_date?: string
  exchange_rate_provider?: string
  has_any_violation?: boolean
  violation_reason?: string | null
  currency_conversion?: CurrencyConversionResult | null
  policy?: UploadPolicyResult
}

export interface RetryAiResponse {
  message: string
  receipt: Receipt
  ai_result: UploadAiResult
}

export interface UploadReceiptResponse {
  message: string
  receipt_ids: string[]
  /** Present on current backend for draft refresh; optional per API docs. */
  report_id?: string
}

export interface SubmitApprovalStep {
  step_order: number
  approver_role: string
  routing_type: 'DEPARTMENT' | 'COMPANY'
  department: string | null
}

export interface SubmitMonthlyReportResponse {
  message: string
  auto_approved?: boolean
  approval_required?: boolean
  view_only_for_workflow?: boolean
  next_action?: string
  current_approval_step?: SubmitApprovalStep
  report?: ExpenseReport
}

export interface PaymentDashboardMetrics {
  payment_queue_reports: number
  approved_reports_waiting_payment: number
  rejected_reports_waiting_accounts_action?: number
  auto_approved_reports_waiting_payment?: number
  manual_approved_reports_waiting_payment?: number
  paid_reports: number
  rejected_reports?: number
  total_rejected_reports?: number
  approved_amount: string
  auto_approved_amount?: string
  manual_approved_amount?: string
  paid_amount: string
  rejected_amount?: string
  rejected_queue_amount?: string
  total_rejected_amount?: string
  payment_completion_rate: number
}

export interface PaymentDashboardResponse {
  payment_user: {
    name: string
    email: string
    company: string
    company_role: string
    permissions?: {
      can_mark_paid: boolean
      can_approve_expense: boolean
    }
  }
  metrics: PaymentDashboardMetrics
  department_payment_summary?: Array<{
    department: string
    total_paid: string
  }>
  recent_approved_reports?: ExpenseReport[]
  recent_auto_approved_reports?: ExpenseReport[]
  recent_manual_approved_reports?: ExpenseReport[]
  recent_paid_reports?: ExpenseReport[]
  approved_reports: ExpenseReport[]
  auto_approved_reports?: ExpenseReport[]
  manual_approved_reports?: ExpenseReport[]
  paid_reports?: ExpenseReport[]
  rejected_reports?: ExpenseReport[]
  rejected_reports_for_accounts?: ExpenseReport[]
  payment_queue_reports?: ExpenseReport[]
  recent_payment_queue_reports?: ExpenseReport[]
  recent_rejected_reports_for_accounts?: ExpenseReport[]
}

export interface CompanyAdminDashboardData {
  company_admin: { name: string; email: string; company: string; company_id?: string }
  setup_status: Record<string, boolean>
  email_forwarding?: {
    company_reimbursement_email: string | null
    platform_receipt_email: string
    forwarding_instruction: string
  }
  metrics: Record<string, number | string>
  department_wise_spend?: Array<{ department: string; total: string }>
  category_wise_spend?: Array<{ category: string; total: string }>
  recent_reports?: ExpenseReport[]
  workflows?: unknown[]
}

export interface EmployeeDashboardCurrentMonthReport {
  report: ExpenseReport
  summary?: {
    total_receipts: number
    no_violation_receipts: number
    violation_receipts: number
    total_amount: string
  }
  workflow_status?: {
    workflow_completed: boolean
    current_approver: { id: string; name: string; email: string } | null
    current_step: Record<string, unknown> | null
  }
  no_violation_receipts?: Receipt[]
  violation_receipts?: Receipt[]
}

export interface EmployeeDashboardResponse {
  user: {
    name: string
    email: string
    system_role: string
    company_role: string
    company: string
    department: string | null
    permissions: UserPermissions
  }
  metrics: {
    total_reports: number
    draft_reports: number
    pending_reports: number
    approved_reports: number
    rejected_reports: number
    paid_reports: number
  }
  current_month_report: EmployeeDashboardCurrentMonthReport | null
  submitted_reports: ExpenseReport[]
}

export interface Currency {
  id: number
  code: string
  name: string
  symbol: string
  country: string
  flag: string
  is_active: boolean
  created_at: string
}

export interface CurrencyListResponse {
  count: number
  total_pages: number
  current_page: number
  page_size: number
  filters: {
    search: string | null
    is_active: string | null
  }
  results: Currency[]
}

export type ExchangeRateSource = 'GLOBAL' | 'CUSTOM'

export interface CompanyExchangeRate {
  id: number
  from_currency: string
  to_currency: string
  exchange_rate: string | number
  updated_at: string
}

export interface FinanceSettings {
  id: number
  company: string
  base_currency: number
  base_currency_details?: Pick<
    Currency,
    'id' | 'code' | 'name' | 'symbol' | 'country' | 'flag' | 'is_active'
  >
  base_currency_code?: string
  base_currency_name?: string
  base_currency_symbol?: string
  base_currency_flag?: string
  auto_currency_conversion: boolean
  exchange_rate_source: ExchangeRateSource
  exchange_rate_provider: string
  allow_manual_exchange_rate: boolean
  decimal_places: number
  rounding_enabled: boolean
  timezone: string
  date_format: string
  last_exchange_sync: string | null
  created_at: string
  updated_at: string
}
