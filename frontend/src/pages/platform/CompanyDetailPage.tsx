import { Building2, GitBranch, ListFilter, Pencil } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getPlatformCompanyDetails, updatePlatformCompany } from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminDataTable, AdminTableCell, AdminTableRow } from '@/components/admin/AdminDataTable'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { AdminListSearchBar } from '@/components/admin/AdminListSearchBar'
import { AdminModalFooter } from '@/components/admin/AdminModalFooter'
import { StatusBadge } from '@/components/StatusBadge'
import { DashboardLayout, platformNavWithAudit } from '@/components/layout/DashboardLayout'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { TabbedTablePageShimmer } from '@/components/ui/shimmer'
import { PaginationControls } from '@/components/ui/pagination-controls'
import { formatReportTotal } from '@/lib/receiptDisplay'
import { toast } from '@/lib/toast'
import { formatDate } from '@/lib/utils'
import type {
  ApprovalWorkflow,
  CompanyRole,
  DepartmentRecord,
  EmployeeRecord,
  ExpenseReport,
  PlatformCompanyDetailsResponse,
  PolicyRule,
} from '@/types'

type Section = 'departments' | 'employees' | 'roles' | 'policy_rules' | 'workflow' | 'reports'

const SECTION_TABS: { label: string; value: Section }[] = [
  { label: 'Departments', value: 'departments' },
  { label: 'Employees', value: 'employees' },
  { label: 'Roles', value: 'roles' },
  { label: 'Policy', value: 'policy_rules' },
  { label: 'Workflow', value: 'workflow' },
  { label: 'Reports', value: 'reports' },
]

const ROLE_OPTIONS = ['EMPLOYEE', 'MANAGER', 'ACCOUNTS', 'COMPANY_ADMIN'] as const

const selectClassName =
  'flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm'

export function CompanyDetailPage() {
  const { companyId = '' } = useParams()
  const [section, setSection] = useState<Section>('departments')
  const [page, setPage] = useState(1)
  const [searchDraft, setSearchDraft] = useState('')
  const [search, setSearch] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [filterDepartmentId, setFilterDepartmentId] = useState('')
  const [filterRole, setFilterRole] = useState('')
  const [filterCompanyRoleId, setFilterCompanyRoleId] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [data, setData] = useState<PlatformCompanyDetailsResponse | null>(null)
  const [filterOptions, setFilterOptions] = useState<{
    departments: DepartmentRecord[]
    roles: CompanyRole[]
  }>({ departments: [], roles: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editOpen, setEditOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editForm, setEditForm] = useState({
    name: '',
    domain: '',
    reimbursement_email: '',
    is_verified: false,
  })

  useEffect(() => {
    if (!companyId) return
    Promise.all([
      getPlatformCompanyDetails(companyId, { section: 'departments', page_size: 100 }),
      getPlatformCompanyDetails(companyId, { section: 'roles', page_size: 100 }),
    ])
      .then(([deptRes, rolesRes]) => {
        setFilterOptions({
          departments: deptRes.data.departments?.results ?? [],
          roles: rolesRes.data.roles?.results ?? [],
        })
      })
      .catch(() => setFilterOptions({ departments: [], roles: [] }))
  }, [companyId])

  const load = useCallback(async () => {
    if (!companyId) return
    setLoading(true)
    setError('')
    try {
      const { data: response } = await getPlatformCompanyDetails(companyId, {
        section,
        page,
        page_size: 10,
        search: search || undefined,
        department_id: section === 'employees' && filterDepartmentId ? filterDepartmentId : undefined,
        role: section === 'employees' && filterRole ? filterRole : undefined,
        company_role_id:
          section === 'employees' && filterCompanyRoleId ? filterCompanyRoleId : undefined,
        category: section === 'policy_rules' && filterCategory ? filterCategory : undefined,
        status: section === 'reports' && filterStatus ? filterStatus : undefined,
      })
      setData(response)
      if (response.company) {
        setEditForm({
          name: response.company.name ?? '',
          domain: response.company.domain ?? '',
          reimbursement_email: response.company.reimbursement_email ?? '',
          is_verified: Boolean(response.company.is_verified),
        })
      }
    } catch (err) {
      setError(getApiErrorMessage(err))
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [
    companyId,
    section,
    page,
    search,
    filterDepartmentId,
    filterRole,
    filterCompanyRoleId,
    filterCategory,
    filterStatus,
  ])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    setPage(1)
  }, [section, search, filterDepartmentId, filterRole, filterCompanyRoleId, filterCategory, filterStatus])

  useEffect(() => {
    setFiltersOpen(false)
    setFilterDepartmentId('')
    setFilterRole('')
    setFilterCompanyRoleId('')
    setFilterCategory('')
    setFilterStatus('')
    setSearchDraft('')
    setSearch('')
  }, [section])

  const company = data?.company
  const showSearch = section !== 'workflow'
  const showFilters = section === 'employees' || section === 'policy_rules' || section === 'reports'

  const saveCompanyDetails = async (e: FormEvent) => {
    e.preventDefault()
    if (!companyId) return
    if (!editForm.name.trim() || !editForm.domain.trim()) {
      setError('Company name and domain are required.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const { data: response } = await updatePlatformCompany(companyId, {
        name: editForm.name.trim(),
        domain: editForm.domain.trim(),
        reimbursement_email: editForm.reimbursement_email.trim() || null,
        is_verified: editForm.is_verified,
      })
      setData((current) =>
        current ? { ...current, company: { ...current.company, ...response.company } } : current,
      )
      setEditForm({
        name: response.company.name ?? '',
        domain: response.company.domain ?? '',
        reimbursement_email: response.company.reimbursement_email ?? '',
        is_verified: Boolean(response.company.is_verified),
      })
      toast.success(response.message || 'Company details updated.')
      setEditOpen(false)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading && !data) {
    return (
      <DashboardLayout
        portal="platform"
        title="Company"
        breadcrumb="Company"
        icon={Building2}
        navItems={platformNavWithAudit}
      >
        <TabbedTablePageShimmer />
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout
      portal="platform"
      title={company?.name ?? 'Company'}
      subtitle={company?.domain}
      breadcrumb="Company details"
      icon={Building2}
      navItems={platformNavWithAudit}
      headerAction={
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" onClick={() => setEditOpen(true)} disabled={!company}>
            <Pencil className="h-4 w-4" />
            Edit details
          </Button>
          <Button asChild variant="outline">
            <Link to="/platform/companies">Back to companies</Link>
          </Button>
        </div>
      }
    >
      {error && !editOpen && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {company && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-gray-600">
          <StatusBadge status={company.is_verified ? 'APPROVED' : 'PENDING'} />
          {company.is_active === false && <StatusBadge status="INACTIVE" />}
          {company.reimbursement_email && (
            <span className="text-gray-500">{company.reimbursement_email}</span>
          )}
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        {SECTION_TABS.map((tab) => (
          <Button
            key={tab.value}
            type="button"
            size="sm"
            variant={section === tab.value ? 'default' : 'outline'}
            onClick={() => setSection(tab.value)}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {showSearch && (
        <AdminListPanel title={`Search ${section.replace('_', ' ')}`}>
          <div className="px-5 py-4 sm:px-6">
            <div className="flex flex-wrap items-center gap-2">
              <div className="min-w-0 flex-1">
                <AdminListSearchBar
                  value={searchDraft}
                  onChange={setSearchDraft}
                  onApply={() => setSearch(searchDraft.trim())}
                  onClear={() => {
                    setSearchDraft('')
                    setSearch('')
                  }}
                  placeholder={`Search ${section.replace('_', ' ')}…`}
                />
              </div>
              {showFilters && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setFiltersOpen((value) => !value)}
                  aria-expanded={filtersOpen}
                >
                  <ListFilter className="h-4 w-4" />
                  Filter
                </Button>
              )}
            </div>
            {filtersOpen && section === 'employees' && (
              <div className="mt-3 flex flex-wrap gap-2 rounded-lg border border-[#e2e8f0] bg-gray-50 p-3">
                <select
                  className={selectClassName + ' min-w-[10rem] sm:flex-1'}
                  value={filterDepartmentId}
                  onChange={(e) => setFilterDepartmentId(e.target.value)}
                >
                  <option value="">All departments</option>
                  {filterOptions.departments.map((dept) => (
                    <option key={dept.id} value={dept.id}>
                      {dept.name}
                    </option>
                  ))}
                </select>
                <select
                  className={selectClassName + ' min-w-[8rem] sm:flex-1'}
                  value={filterRole}
                  onChange={(e) => setFilterRole(e.target.value)}
                >
                  <option value="">All system roles</option>
                  {ROLE_OPTIONS.map((role) => (
                    <option key={role} value={role}>
                      {role.charAt(0) + role.slice(1).toLowerCase()}
                    </option>
                  ))}
                </select>
                <select
                  className={selectClassName + ' min-w-[8rem] sm:flex-1'}
                  value={filterCompanyRoleId}
                  onChange={(e) => setFilterCompanyRoleId(e.target.value)}
                >
                  <option value="">All company roles</option>
                  {filterOptions.roles.map((role) => (
                    <option key={role.id} value={String(role.id)}>
                      {role.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {filtersOpen && section === 'policy_rules' && (
              <div className="mt-3 rounded-lg border border-[#e2e8f0] bg-gray-50 p-3">
                <input
                  className={selectClassName}
                  value={filterCategory}
                  onChange={(e) => setFilterCategory(e.target.value)}
                  placeholder="Category e.g. food, hotel, fuel"
                />
              </div>
            )}
            {filtersOpen && section === 'reports' && (
              <div className="mt-3 rounded-lg border border-[#e2e8f0] bg-gray-50 p-3">
                <select
                  className={selectClassName}
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value)}
                >
                  <option value="">All statuses</option>
                  <option value="DRAFT">Draft</option>
                  <option value="SUBMITTED">Submitted</option>
                  <option value="APPROVED">Approved</option>
                  <option value="REJECTED">Rejected</option>
                  <option value="PAID">Paid</option>
                </select>
              </div>
            )}
          </div>
        </AdminListPanel>
      )}

      <div className={showSearch ? 'mt-4' : undefined}>
        {section === 'departments' && (
          <SectionTable
            title="Departments"
            count={data?.departments?.count}
            columns={['Name', 'Manager', 'Status', 'Created']}
            page={page}
            totalPages={data?.departments?.total_pages ?? 1}
            onPageChange={setPage}
            loading={loading}
          >
            {(data?.departments?.results ?? []).map((dept: DepartmentRecord) => (
              <AdminTableRow key={dept.id}>
                <AdminTableCell className="font-medium">{dept.name}</AdminTableCell>
                <AdminTableCell>{dept.manager_name ?? '—'}</AdminTableCell>
                <AdminTableCell>
                  <StatusBadge status={dept.is_active === false ? 'INACTIVE' : 'ACTIVE'} />
                </AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {formatDate(dept.created_at)}
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </SectionTable>
        )}

        {section === 'employees' && (
          <SectionTable
            title="Employees"
            count={data?.employees?.count}
            columns={['Name', 'Email', 'System role', 'Company role', 'Department']}
            page={page}
            totalPages={data?.employees?.total_pages ?? 1}
            onPageChange={setPage}
            loading={loading}
          >
            {(data?.employees?.results ?? []).map((emp: EmployeeRecord) => (
              <AdminTableRow key={emp.id}>
                <AdminTableCell className="font-medium">
                  {emp.first_name} {emp.last_name}
                </AdminTableCell>
                <AdminTableCell>{emp.email}</AdminTableCell>
                <AdminTableCell>{emp.role}</AdminTableCell>
                <AdminTableCell>{emp.company_role_name || '—'}</AdminTableCell>
                <AdminTableCell>{emp.department_name || '—'}</AdminTableCell>
              </AdminTableRow>
            ))}
          </SectionTable>
        )}

        {section === 'roles' && (
          <SectionTable
            title="Roles"
            count={data?.roles?.count}
            columns={['Role', 'Permissions', 'Status']}
            page={page}
            totalPages={data?.roles?.total_pages ?? 1}
            onPageChange={setPage}
            loading={loading}
          >
            {(data?.roles?.results ?? []).map((role: CompanyRole) => (
              <AdminTableRow key={role.id}>
                <AdminTableCell className="font-medium">{role.name}</AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {[
                    role.can_upload_receipt && 'Upload',
                    role.can_submit_expense && 'Submit',
                    role.can_approve_expense && 'Approve',
                    role.can_mark_paid && 'Pay',
                    role.can_view_company_reports && 'Reports',
                  ]
                    .filter(Boolean)
                    .join(', ') || '—'}
                </AdminTableCell>
                <AdminTableCell>
                  <StatusBadge status={role.is_active ? 'APPROVED' : 'REJECTED'} />
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </SectionTable>
        )}

        {section === 'policy_rules' && (
          <SectionTable
            title="Policy rules"
            count={data?.policy_rules?.count}
            columns={['Category', 'Max amount', 'Description', 'Status']}
            page={page}
            totalPages={data?.policy_rules?.total_pages ?? 1}
            onPageChange={setPage}
            loading={loading}
          >
            {(data?.policy_rules?.results ?? []).map((rule: PolicyRule) => (
              <AdminTableRow key={rule.id}>
                <AdminTableCell className="font-medium capitalize">
                  {rule.category_name.replace(/_/g, ' ')}
                </AdminTableCell>
                <AdminTableCell>{rule.max_amount}</AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {rule.category_description || '—'}
                </AdminTableCell>
                <AdminTableCell>
                  <StatusBadge status={rule.is_active === false ? 'INACTIVE' : 'ACTIVE'} />
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </SectionTable>
        )}

        {section === 'workflow' && (
          <AdminListPanel
            title="Approval workflow"
            description="Read-only view of the company's active approval flow."
          >
            <div className="p-5 sm:p-6">
              <WorkflowSummary workflow={data?.workflow ?? null} />
            </div>
          </AdminListPanel>
        )}

        {section === 'reports' && (
          <SectionTable
            title="Expense reports"
            count={data?.reports?.count}
            columns={['Employee', 'Month', 'Status', 'Amount', 'Submitted']}
            page={page}
            totalPages={data?.reports?.total_pages ?? 1}
            onPageChange={setPage}
            loading={loading}
          >
            {(data?.reports?.results ?? []).map((report: ExpenseReport) => (
              <AdminTableRow key={report.id}>
                <AdminTableCell>
                  <div>
                    <p className="font-medium text-gray-900">
                      {report.employee_name || report.employee_email}
                    </p>
                    <p className="text-xs text-gray-500">{report.employee_email}</p>
                  </div>
                </AdminTableCell>
                <AdminTableCell>{String(report.month).slice(0, 7)}</AdminTableCell>
                <AdminTableCell>
                  <StatusBadge status={report.status} />
                </AdminTableCell>
                <AdminTableCell>{formatReportTotal(report)}</AdminTableCell>
                <AdminTableCell className="text-gray-500">
                  {formatDate(report.submitted_at)}
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </SectionTable>
        )}
      </div>

      <Dialog
        open={editOpen}
        onOpenChange={(open) => {
          if (!open) {
            setEditOpen(false)
            setError('')
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit company details</DialogTitle>
            <DialogDescription>
              Update this company&apos;s name, domain, reimbursement email, and verification status.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={saveCompanyDetails} className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="platform-company-name">Company name</Label>
              <Input
                id="platform-company-name"
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                disabled={saving}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="platform-company-domain">Domain</Label>
              <Input
                id="platform-company-domain"
                value={editForm.domain}
                onChange={(e) => setEditForm({ ...editForm, domain: e.target.value })}
                disabled={saving}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="platform-company-email">Reimbursement email</Label>
              <Input
                id="platform-company-email"
                type="email"
                value={editForm.reimbursement_email}
                onChange={(e) => setEditForm({ ...editForm, reimbursement_email: e.target.value })}
                disabled={saving}
              />
            </div>
            <label className="flex items-start gap-2 rounded-lg border border-[#e2e8f0] bg-gray-50 px-3 py-2 text-sm text-gray-800">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={editForm.is_verified}
                onChange={(e) => setEditForm({ ...editForm, is_verified: e.target.checked })}
                disabled={saving}
              />
              <span>
                Mark company email as verified
                <span className="mt-0.5 block text-xs text-gray-500">
                  Verified companies appear in the main companies list.
                </span>
              </span>
            </label>
            {error && editOpen && <p className="text-sm text-red-600">{error}</p>}
            <AdminModalFooter
              onCancel={() => {
                setEditOpen(false)
                setError('')
              }}
              submitLabel="Save details"
              submitting={saving}
            />
          </form>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  )
}

function SectionTable({
  title,
  count,
  columns,
  page,
  totalPages,
  onPageChange,
  loading,
  children,
}: {
  title: string
  count?: number
  columns: string[]
  page: number
  totalPages: number
  onPageChange: (page: number) => void
  loading?: boolean
  children: ReactNode
}) {
  return (
    <AdminListPanel title={title} count={count}>
      {loading ? (
        <p className="px-5 py-8 text-sm text-gray-400">Loading…</p>
      ) : (
        <>
          <div className="p-4 sm:p-6">
            <AdminDataTable columns={columns}>{children}</AdminDataTable>
          </div>
          <PaginationControls
            currentPage={page}
            totalPages={totalPages}
            totalCount={count ?? 0}
            onPageChange={onPageChange}
          />
        </>
      )}
    </AdminListPanel>
  )
}

function WorkflowSummary({ workflow }: { workflow: ApprovalWorkflow | null }) {
  if (!workflow) {
    return <p className="text-sm text-gray-500">No active workflow configured for this company.</p>
  }

  const steps = (workflow.steps ?? []).filter((s) => s.is_active).sort((a, b) => a.step_order - b.step_order)

  return (
    <div className="space-y-4">
      <p className="text-sm font-medium text-gray-900">{workflow.name}</p>
      <ol className="space-y-3">
        {steps.map((step) => (
          <li
            key={step.id}
            className="flex items-start gap-3 rounded-lg border border-[#e2e8f0] bg-white px-4 py-3 text-sm"
          >
            <GitBranch className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <div>
              <p className="font-medium text-gray-900">
                Step {step.step_order}: {step.approver_role_name}
              </p>
              <p className="text-gray-500">
                {step.routing_type === 'COMPANY'
                  ? 'Company wide'
                  : step.department_name
                    ? `Pinned to ${step.department_name}`
                    : "Submitter's department"}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
