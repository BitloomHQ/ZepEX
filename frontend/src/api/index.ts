import { api } from './client'
import type {
  AddWorkflowStepResponse,
  AdminReportsResponse,
  ApprovalWorkflow,
  ApproveReportResponse,
  AuditLogEntry,
  CompanyRegistrationRequest,
  CompanyRole,
  DeactivateWorkflowStepResponse,
  DepartmentRecord,
  DuplicateReceiptsResponse,
  EmployeeRecord,
  CreateEmployeeResponse,
  ExpenseReport,
  LoginResponse,
  MarkPaidReportResponse,
  MyUploadedExpensesResponse,
  PendingApprovalsResponse,
  PolicyRule,
  PolicyRuleMutationResponse,
  PolicyPreviewResponse,
  PolicySimulateResponse,
  PolicyCopyResponse,
  PolicyDocumentUploadResponse,
  PolicyDocumentPreviewResponse,
  PolicyDocumentUpdatePreviewResponse,
  PolicyDocumentRevalidateResponse,
  PolicyDocumentConfirmImportResponse,
  PolicyVersionsListResponse,
  WorkflowSimulateResponse,
  PlatformEmailServiceResponse,
  ReimbursementEmailConfigResponse,
  RejectReportResponse,
  UpdateWorkflowStepResponse,
  CompanyExchangeRate,
  Currency,
  CurrencyListResponse,
  ExchangeRateSource,
  FinanceSettings,
  UploadReceiptResponse,
  SubmitMonthlyReportResponse,
  PaymentDashboardResponse,
  User,
  UserProfile,
} from '@/types'

// Auth
export const login = (email: string, password: string) =>
  api.post<LoginResponse>('/auth/login/', { email, password })

export const changePassword = (old_password: string, new_password: string) =>
  api.post<{ message: string }>('/auth/change-password/', { old_password, new_password })

export const forgotPassword = (email: string) =>
  api.post<{ message: string }>('/auth/forgot-password/', { email })

export const resetPassword = (payload: {
  uid: string
  token: string
  new_password: string
  confirm_password: string
}) => api.post<{ message: string }>('/auth/reset-password/', payload)

export const getProfile = () => api.get<UserProfile>('/auth/profile/')

export const editProfile = (data: FormData) =>
  api.patch<{ message: string }>('/auth/edit-profile/', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

// Platform
export const requestCompanyRegistrationOtp = (payload: {
  admin_email: string
  company_name: string
  company_domain: string
  admin_name: string
  expected_employee_count: number
}) =>
  api.post<{ success: boolean; message: string }>(
    '/platform/company-requests/request-otp/',
    payload,
  )

export const verifyCompanyRegistrationOtp = (admin_email: string, otp: string) =>
  api.post<{ success: boolean; message: string }>(
    '/platform/company-registration/verify-otp/',
    { admin_email, otp },
  )

export const registerCompany = (data: {
  company_name: string
  company_domain: string
  admin_name: string
  admin_email: string
  expected_employee_count: number
  otp?: string
}) => api.post<{ message: string; data: CompanyRegistrationRequest }>(
  '/platform/register-company/',
  data,
)

export const listCompanyRequests = () =>
  api.get<CompanyRegistrationRequest[]>('/platform/requests/')

export const approveCompanyRequest = (requestId: number) =>
  api.post<import('@/types').ApproveCompanyRequestResponse>(`/platform/approve/${requestId}/`)

export const rejectCompanyRequest = (requestId: number, reject_reason: string) =>
  api.post<import('@/types').RejectCompanyRequestResponse>(`/platform/reject/${requestId}/`, {
    reject_reason,
  })

export const getPlatformDashboard = () => api.get('/dashboard/platform-owner/')

// Tenants
export const createDepartment = (name: string) =>
  api.post<DepartmentRecord>('/tenants/departments/', { name })

export const listDepartments = (params?: { page?: number; search?: string }) =>
  api.get<import('@/lib/pagination').PaginatedResponse<DepartmentRecord>>(
    '/tenants/departments/list/',
    { params },
  )

export const listCompanyRoles = (params?: {
  page?: number
  search?: string
  can_approve_expense?: string
}) =>
  api.get<import('@/lib/pagination').PaginatedResponse<CompanyRole>>('/tenants/roles/', {
    params,
  })

export const createEmployee = (data: {
  first_name: string
  last_name: string
  email: string
  password?: string
  role: string
  department_id?: string
  company_role_id?: number
}) => api.post<CreateEmployeeResponse>('/tenants/employees/', data)

export const listEmployees = (params?: {
  page?: number
  search?: string
  department_id?: string
  role?: string
  company_role_id?: string
}) =>
  api.get<import('@/lib/pagination').PaginatedResponse<EmployeeRecord>>(
    '/tenants/employees/list/',
    { params },
  )

export const assignMissingCompanyRoles = () =>
  api.post<{ message: string; updated_count: number }>(
    '/tenants/employees/assign-missing-roles/',
    {},
  )

export const assignManager = (department_id: string, manager_id: number) =>
  api.post('/tenants/assign-manager/', { department_id, manager_id })

export const updateDepartment = (
  departmentId: string,
  data: { name?: string; manager_id?: number | null },
) => api.patch(`/tenants/departments/${departmentId}/update/`, data)

export const deactivateDepartment = (departmentId: string) =>
  api.patch(`/tenants/departments/${departmentId}/deactivate/`)

export const activateDepartment = (departmentId: string) =>
  api.patch(`/tenants/departments/${departmentId}/activate/`)

export const deleteDepartment = (departmentId: string) =>
  api.delete(`/tenants/departments/${departmentId}/delete/`)

export const editCompanyUser = (
  userId: number,
  data: {
    first_name?: string
    last_name?: string
    role?: string
    company_role_id?: number | null
    department_id?: string | null
    phone_number?: string
    address?: string
    email?: string
  },
) => api.patch(`/tenants/users/${userId}/edit/`, data)

export const deactivateCompanyUser = (userId: number) =>
  api.patch(`/tenants/users/${userId}/deactivate/`)

export const activateCompanyUser = (userId: number) =>
  api.patch(`/tenants/users/${userId}/activate/`)

export const deleteCompanyUser = (userId: number) =>
  api.delete(`/tenants/users/${userId}/delete/`)

export const createCompanyRole = (data: {
  name: string
  can_upload_receipt: boolean
  can_submit_expense: boolean
  can_approve_expense: boolean
  can_mark_paid: boolean
}) => api.post('/tenants/roles/create/', data)

export const updateCompanyRole = (
  roleId: number,
  data: {
    name?: string
    can_upload_receipt?: boolean
    can_submit_expense?: boolean
    can_approve_expense?: boolean
    can_mark_paid?: boolean
  },
) => api.put(`/tenants/roles/${roleId}/update/`, data)

export const deactivateCompanyRole = (roleId: number) =>
  api.post(`/tenants/roles/${roleId}/deactivate/`)

export const updatePolicyRule = (
  ruleId: string,
  data: {
    company_role?: number
    category_name?: string
    max_amount?: number | string
    is_unlimited?: boolean
    category_description?: string
    is_active?: boolean
  },
) => api.patch<PolicyRuleMutationResponse>(`/tenants/policy/rules/${ruleId}/update/`, data)

export const deactivatePolicyRule = (ruleId: string) =>
  api.patch<PolicyRuleMutationResponse>(`/tenants/policy/rules/${ruleId}/deactivate/`)

export const activatePolicyRule = (ruleId: string) =>
  api.patch<PolicyRuleMutationResponse>(`/tenants/policy/rules/${ruleId}/activate/`)

export const createCompanyPolicy = () => api.post('/tenants/policy/')

export const createPolicyRule = (data: {
  company_role: number
  category_name: string
  max_amount: number | string
  is_unlimited?: boolean
  category_description: string
  is_active?: boolean
}) => api.post<PolicyRuleMutationResponse>('/tenants/policy/rules/create/', data)

export const listPolicyRules = (params?: {
  page?: number
  search?: string
  category?: string
  company_role_id?: number | string
}) =>
  api.get<import('@/lib/pagination').PaginatedResponse<PolicyRule>>(
    '/tenants/policy/rules/',
    { params },
  )

export const previewRolePolicy = (companyRoleId: number | string) =>
  api.get<PolicyPreviewResponse>('/tenants/policy/preview/', {
    params: { company_role_id: companyRoleId },
  })

export const simulatePolicyRule = (data: {
  company_role_id: number | string
  category: string
  amount: number | string
}) => api.post<PolicySimulateResponse>('/tenants/policy/simulate/', data)

export const copyRolePolicy = (data: {
  from_role: number
  to_role: number
  overwrite_existing?: boolean
}) => api.post<PolicyCopyResponse>('/tenants/policy/copy/', data)

// Policy document import (PDF/DOCX/TXT/etc.)
// Upload returns quickly; AI extraction + validation run in a background job.
export const uploadPolicyDocument = (
  file: File,
  onUploadProgress?: (percent: number) => void,
) => {
  const formData = new FormData()
  formData.append('document', file)

  return api.post<PolicyDocumentUploadResponse>(
    '/tenants/policy/document/upload/',
    formData,
    {
      timeout: 5 * 60 * 1000,
      onUploadProgress: (event) => {
        if (!onUploadProgress || !event.total) return
        onUploadProgress(Math.round((event.loaded / event.total) * 100))
      },
    },
  )
}

export const getPolicyDocumentPreview = (importId: string) =>
  api.get<PolicyDocumentPreviewResponse>(
    `/tenants/policy/document/${importId}/preview/`,
  )

export const updatePolicyDocumentPreview = (
  importId: string,
  data: {
    policy_name?: string
    policy_version?: string
    effective_date?: string
    expiry_date?: string
    policy_currency?: string
    document_summary?: string
    document_summary_original_language?: string
    document_level_conditions?: string[]
    document_level_conditions_original_language?: string[]
    rules?: unknown[]
  },
) => api.patch<PolicyDocumentUpdatePreviewResponse>(
  `/tenants/policy/document/${importId}/preview/update/`,
  data,
)

export const revalidatePolicyDocumentPreview = (importId: string) =>
  api.post<PolicyDocumentRevalidateResponse>(
    `/tenants/policy/document/${importId}/preview/revalidate/`,
    {},
  )

export const confirmPolicyDocumentImport = (
  importId: string,
  data: {
    overwrite_existing?: boolean
    allow_review_required?: boolean
  },
) =>
  api.post<PolicyDocumentConfirmImportResponse>(
    `/tenants/policy/document/${importId}/confirm/`,
    data,
  )

// Policy versions
export const createPolicyVersion = (data: {
  title: string
  description?: string
  copy_active_rules?: boolean
}) => api.post('/tenants/policy/versions/create/', data)

export const listPolicyVersions = (params?: {
  status?: 'DRAFT' | 'ACTIVE' | 'ARCHIVED'
  is_active?: boolean
}) =>
  api.get<PolicyVersionsListResponse>('/tenants/policy/versions/', {
    params,
  })

export const activatePolicyVersion = (versionId: string) =>
  api.patch(`/tenants/policy/versions/${versionId}/activate/`)

export const archivePolicyVersion = (versionId: string) =>
  api.patch(`/tenants/policy/versions/${versionId}/archive/`)

export const deleteDraftPolicyVersion = (versionId: string) =>
  api.delete<{
    success: boolean
    message: string
  }>(`/tenants/policy/versions/${versionId}/delete/`)

export const getReimbursementEmailConfig = () =>
  api.get<ReimbursementEmailConfigResponse>('/tenants/reimbursement-email/')

export const saveReimbursementEmailConfig = (data: { reimbursement_email: string }) =>
  api.post<ReimbursementEmailConfigResponse>('/tenants/reimbursement-email/save/', data)

export const getCompanyPolicySettings = () =>
  api.get<import('@/types').CompanyPolicySettingsResponse>(
    '/expenses/company/policy/settings/',
  )

export const updateCompanyPolicySettings = (data: {
  old_bill_limit_days?: number
  auto_approve_if_no_violation?: boolean
}) =>
  api.patch<import('@/types').CompanyPolicySettingsResponse>(
    '/expenses/company/policy/settings/',
    data,
  )

export const getNotifications = () =>
  api.get<import('@/types').NotificationsListResponse>('/expenses/notifications/')

export const markNotificationRead = (notificationId: string) =>
  api.post<import('@/types').MarkNotificationReadResponse>(
    `/expenses/notifications/${notificationId}/read/`,
  )

export const markAllNotificationsRead = () =>
  api.post<import('@/types').MarkAllNotificationsReadResponse>(
    '/expenses/notifications/read-all/',
  )

export const getCompanyImapConfig = () =>
  api.get<import('@/types').CompanyImapConfigResponse>('/tenants/company/imap-config/')

export const testCompanyImapConnection = (
  data: import('@/types').TestImapConnectionPayload,
) =>
  api.post<import('@/types').CompanyImapConfigResponse>(
    '/tenants/company/imap-config/test/',
    data,
  )

export const saveCompanyImapConfig = (data: import('@/types').SaveImapConfigPayload) =>
  api.put<import('@/types').CompanyImapConfigResponse>('/tenants/company/imap-config/', data)

export const patchCompanyImapConfig = (data: import('@/types').SaveImapConfigPayload) =>
  api.patch<import('@/types').CompanyImapConfigResponse>('/tenants/company/imap-config/', data)

export const getEmailServiceStatus = () =>
  api.get<PlatformEmailServiceResponse>('/tenants/smtp-config/')

/** @deprecated Use getEmailServiceStatus — company SMTP is platform-managed via .env */
export const getSmtpConfig = getEmailServiceStatus

export const getCompanyAdminDashboard = () =>
  api.get<import('@/types').CompanyAdminDashboardData>('/dashboard/company-admin/')

export const getAuditLogs = (params?: {
  action?: string
  user_id?: number
  company_id?: string
  start_date?: string
  end_date?: string
  page?: number
}) =>
  api.get<import('@/lib/pagination').PaginatedResponse<AuditLogEntry>>('/audit-logs/', {
    params,
  })

export const getPlatformAuditLogs = (params?: {
  action?: string
  company_id?: string
  start_date?: string
  end_date?: string
  page?: number
}) =>
  api.get<import('@/lib/pagination').PaginatedResponse<AuditLogEntry>>('/audit-logs/platform/', {
    params,
  })

export const listPlatformCompanies = () =>
  api.get<{
    count: number
    results: Array<{ id: string; name: string; domain: string; is_verified: boolean }>
  }>('/platform/companies/')

export const listPlatformPermissions = () =>
  api.get<import('@/types').PlatformPermission[]>('/platform-admin/permissions/')

export const listPlatformAdmins = () =>
  api.get<import('@/types').PlatformAdminUser[]>('/platform-admin/list/')

export const createPlatformUser = (payload: {
  email: string
  first_name: string
  last_name?: string
  password?: string
  permissions: string[]
}) => api.post<import('@/types').CreatePlatformUserResponse>('/platform-admin/users/create/', payload)

export const updatePlatformAdminPermissions = (adminId: number, permissions: string[]) =>
  api.put<{ message: string; data: import('@/types').PlatformAdminUser }>(
    `/platform-admin/${adminId}/update/`,
    { permissions },
  )

function uploadCsv(
  path: string,
  file: File,
  onUploadProgress?: (percent: number) => void,
) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post<import('@/types').CsvImportResult>(path, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (!onUploadProgress || !event.total) return
      onUploadProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
}

export type CsvImportOptions = {
  onUploadProgress?: (percent: number) => void
}

export const importDepartments = (file: File, options?: CsvImportOptions) =>
  uploadCsv('/tenants/departments/import/', file, options?.onUploadProgress)

export const importCompanyRolesCsv = (file: File, options?: CsvImportOptions) =>
  uploadCsv('/tenants/roles/import/', file, options?.onUploadProgress)

export const importEmployeesCsv = (file: File, options?: CsvImportOptions) =>
  uploadCsv('/tenants/employees/import/', file, options?.onUploadProgress)

export const importPolicyRulesCsv = (file: File, options?: CsvImportOptions) =>
  uploadCsv('/tenants/policy-rules/import/', file, options?.onUploadProgress)

export const getDepartmentTemplateInfo = () =>
  api.get<import('@/types').CsvTemplateInfo>('/tenants/departments/template/')

export const getRolesTemplateInfo = () =>
  api.get<import('@/types').CsvTemplateInfo>('/tenants/roles/template/')

export const getEmployeesTemplateInfo = () =>
  api.get<import('@/types').CsvTemplateInfo>('/tenants/employees/template/')

export const getPolicyRulesTemplateInfo = () =>
  api.get<import('@/types').CsvTemplateInfo>('/tenants/policy-rules/template/')

async function downloadCsvTemplate(path: string, fallbackName: string) {
  const response = await api.get<Blob>(path, { responseType: 'blob' })
  const { downloadBlob, filenameFromContentDisposition } = await import('@/lib/csvDownload')
  const filename = filenameFromContentDisposition(
    response.headers['content-disposition'],
    fallbackName,
  )
  downloadBlob(response.data, filename)
}

export const downloadDepartmentTemplate = () =>
  downloadCsvTemplate('/tenants/departments/template/download/', 'department_template.csv')

export const downloadRolesTemplate = () =>
  downloadCsvTemplate('/tenants/roles/template/download/', 'roles_template.csv')

export const downloadEmployeesTemplate = () =>
  downloadCsvTemplate('/tenants/employees/template/download/', 'employees_template.csv')

export const downloadPolicyRulesTemplate = () =>
  downloadCsvTemplate('/tenants/policy-rules/template/download/', 'policy_rules_template.csv')

export const sendEmployeeInvites = (data: { employee_ids?: string[]; send_to_all?: boolean }) =>
  api.post<import('@/types').EmployeeInviteResult>('/tenants/employees/send-invites/', data)

export const getPlatformCompanyDetails = (
  companyId: string,
  params?: {
    section?: 'all' | 'departments' | 'employees' | 'roles' | 'policy_rules' | 'workflow'
    page?: number
    page_size?: number
    search?: string
    department_id?: string
    role?: string
    company_role_id?: string
    category?: string
  },
) =>
  api.get<import('@/types').PlatformCompanyDetailsResponse>(
    `/platform/companies/${companyId}/details/`,
    { params },
  )

export const deactivatePlatformCompany = (companyId: string) =>
  api.patch(`/platform/companies/${companyId}/deactivate/`)

export const activatePlatformCompany = (companyId: string) =>
  api.patch(`/platform/companies/${companyId}/activate/`)

export const deletePlatformCompany = (companyId: string) =>
  api.delete(`/platform/companies/${companyId}/delete/`)

export const listCurrencies = (params?: {
  page?: number
  page_size?: number
  search?: string
  is_active?: string
}) => api.get<CurrencyListResponse>('/tenants/currencies/', { params })

export const getCurrency = (currencyCode: string) =>
  api.get<{ success: boolean; currency: Currency }>(`/tenants/currencies/${currencyCode}/`)

export const getFinanceSettings = () =>
  api.get<{ success: boolean; settings: FinanceSettings }>('/tenants/company/finance-settings/')

export const updateFinanceSettings = (data: {
  base_currency: number
  auto_currency_conversion: boolean
  exchange_rate_source: ExchangeRateSource
  exchange_rate_provider: string
  allow_manual_exchange_rate: boolean
  decimal_places: number
  rounding_enabled: boolean
  timezone: string
  date_format: string
}) =>
  api.put<{
    success: boolean
    message: string
    settings: FinanceSettings
    draft_receipts_resynced?: number
  }>('/tenants/company/finance-settings/', data)

export const getCompanyExchangeRates = () =>
  api.get<{ success: boolean; exchange_rates: CompanyExchangeRate[] }>(
    '/tenants/company/exchange-rates/',
  )

export const createCompanyExchangeRate = (data: {
  from_currency: string
  to_currency: string
  exchange_rate: number | string
}) =>
  api.post<{
    success: boolean
    message: string
    exchange_rate: CompanyExchangeRate
    draft_receipts_resynced?: number
  }>('/tenants/company/exchange-rates/', data)

export const updateCompanyExchangeRate = (
  rateId: number,
  data: {
    from_currency?: string
    to_currency?: string
    exchange_rate?: number | string
  },
) =>
  api.put<{
    success: boolean
    message: string
    exchange_rate: CompanyExchangeRate
    draft_receipts_resynced?: number
  }>(`/tenants/company/exchange-rates/${rateId}/`, data)

export const deleteCompanyExchangeRate = (rateId: number) =>
  api.delete<{
    success: boolean
    message: string
    draft_receipts_resynced?: number
  }>(`/tenants/company/exchange-rates/${rateId}/delete/`)

export const getAuditLogDashboard = () => api.get('/audit-logs/dashboard/')

// Expenses
export const uploadReceipt = (files: File[], reportId?: string) => {
  const formData = new FormData()
  if (reportId) {
    formData.append('report_id', reportId)
  }
  for (const file of files) {
    formData.append('files', file)
  }
  return api.post<UploadReceiptResponse>('/expenses/upload-receipt/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const submitMonthlyReport = () =>
  api.post<SubmitMonthlyReportResponse>('/expenses/reports/submit/')

export const getCurrentMonthReport = () =>
  api.get<ExpenseReport>('/expenses/reports/current/')

export const getMyUploadedExpenses = (params?: {
  status?: string
  start_date?: string
  end_date?: string
  min_amount?: string
  max_amount?: string
}) => api.get<MyUploadedExpensesResponse>('/expenses/my-uploaded-expenses/', { params })

export const getDuplicateReceipts = (params?: { type?: string }) =>
  api.get<DuplicateReceiptsResponse>('/expenses/duplicates/', { params })

export const deleteLineItem = (lineItemId: string) =>
  api.delete(`/expenses/line-items/${lineItemId}/delete/`)

export const deleteReceipt = (receiptId: string) =>
  api.delete<{ success?: boolean; message: string }>(
    `/expenses/receipt/${receiptId}/delete/`,
  )

export const retryReceiptAi = (receiptId: string) =>
  api.post<import('@/types').RetryAiResponse>(
    `/expenses/receipts/${receiptId}/retry-ai/`,
    {},
  )

export const getMyPendingApprovals = (params?: {
  employee_id?: number
  employee_email?: string
  department_id?: string
  start_date?: string
  end_date?: string
  min_amount?: string
  max_amount?: string
  page?: number
}) => api.get<PendingApprovalsResponse>('/expenses/approvals/my-pending/', { params })

export const getMyApprovedApprovals = (params?: {
  employee_id?: number
  employee_email?: string
  department_id?: string
  start_date?: string
  end_date?: string
  min_amount?: string
  max_amount?: string
  page?: number
}) => api.get<PendingApprovalsResponse>('/expenses/approvals/my-approved/', { params })

export const getAdminReports = (params?: {
  status?: string
  employee_id?: number
  employee_email?: string
  department_id?: string
  start_date?: string
  end_date?: string
  page?: number
}) => api.get<AdminReportsResponse>('/expenses/admin/reports/', { params })

export const approveReport = (reportId: string, notes?: string) =>
  api.post<ApproveReportResponse>(`/expenses/reports/${reportId}/approve/`, { notes })

export const rejectReport = (reportId: string, notes: string) =>
  api.post<RejectReportResponse>(`/expenses/reports/${reportId}/reject/`, { notes })

export const approveReceipt = (reportId: string, receiptId: string, notes?: string) =>
  api.post<import('@/types').ApproveReceiptResponse>(
    `/expenses/reports/${reportId}/receipts/${receiptId}/approve/`,
    { notes },
  )

export const rejectReceipt = (reportId: string, receiptId: string, notes: string) =>
  api.post<import('@/types').RejectReceiptResponse>(
    `/expenses/reports/${reportId}/receipts/${receiptId}/reject/`,
    { notes },
  )

export const removeReportLineItem = (reportId: string, lineItemId: string, reason: string) =>
  api.post<import('@/types').RemoveLineItemResponse>(
    `/expenses/reports/${reportId}/line-items/${lineItemId}/remove/`,
    { reason },
  )

export const restoreReportLineItem = (reportId: string, lineItemId: string, notes?: string) =>
  api.post<import('@/types').RestoreLineItemResponse>(
    `/expenses/reports/${reportId}/line-items/${lineItemId}/restore/`,
    { notes },
  )

export const accountsMarkPaid = (reportId: string, notes = '') =>
  api.post<MarkPaidReportResponse>(`/expenses/accounts/reports/${reportId}/paid/`, { notes })

/** Alias matching updated API docs */
export const markReportPaid = accountsMarkPaid

// Approval workflow
export const listApprovalWorkflows = () =>
  api.get<import('@/types').ApprovalWorkflowListResponse>('/expenses/workflow/')

export const getApprovalWorkflow = (workflowId: string) =>
  api.get<ApprovalWorkflow>(`/expenses/workflow/?workflow_id=${workflowId}`)

export const saveApprovalWorkflow = (data: {
  name: string
  start_role: number
  workflow_id?: string | number
}) =>
  api.post<{ message: string; workflow: ApprovalWorkflow }>('/expenses/workflow/save/', data)

export const addWorkflowStep = (data: {
  workflow_id: string
  step_order: number
  approver_role?: number
  approver_type?: string
  routing_type: 'DEPARTMENT' | 'COMPANY'
  department?: string | null
  specific_user?: string | null
}) => api.post<AddWorkflowStepResponse>('/expenses/workflow/steps/add/', data)

export const deactivateWorkflowStep = (stepId: string) =>
  api.patch<DeactivateWorkflowStepResponse>(`/expenses/workflow/steps/${stepId}/deactivate/`)

export const updateWorkflowStep = (
  stepId: string,
  data: {
    step_order?: number
    approver_type?: string
    approver_role?: number
    routing_type?: 'DEPARTMENT' | 'COMPANY'
    department?: string | null
    specific_user?: string | null
  },
) => api.patch<UpdateWorkflowStepResponse>(`/expenses/workflow/steps/${stepId}/update/`, data)

export const deleteApprovalWorkflow = (workflowId: string) =>
  api.delete<import('@/types').DeleteWorkflowResponse>(`/expenses/workflow/${workflowId}/`)

export const simulateWorkflow = (employeeId: string | number) =>
  api.post<WorkflowSimulateResponse>('/expenses/workflow/simulate/', {
    employee_id: employeeId,
  })

// Dashboards
export const getDashboard = () => api.get('/dashboard/')

export const getEmployeeDashboard = () =>
  api.get<import('@/types').EmployeeDashboardResponse>('/dashboard/employee/')

export const getApproverDashboard = () => api.get('/dashboard/approver/')

export const getPaymentDashboard = () =>
  api.get<PaymentDashboardResponse>('/dashboard/payments/')

// Backward-compatible aliases
export const getCompanyAuditLogs = getAuditLogs
export const getManagerPendingReports = getMyPendingApprovals
export const managerApproveReport = approveReport
export const managerRejectReport = rejectReport
export const getManagerDashboard = getApproverDashboard
export const getAccountsDashboard = getPaymentDashboard

export type { User }
