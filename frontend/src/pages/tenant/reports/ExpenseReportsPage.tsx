import { Building2, ChevronRight, DollarSign, PieChart, Users } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  getFinanceSettings,
  getPaymentCategorySummary,
  getPaymentDepartmentSummary,
  getPaymentEmployeeHistory,
  getPaymentEmployeeSummary,
  getPaymentMonthlyExpenses,
  getPaymentMonthlySummary,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminDataTable, AdminTableCell, AdminTableRow } from '@/components/admin/AdminDataTable'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { MetricCard } from '@/components/MetricCard'
import { StatusBadge } from '@/components/StatusBadge'
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
import { PaginationControls } from '@/components/ui/pagination-controls'
import { DashboardPageShimmer } from '@/components/ui/shimmer'
import { useAdminNav } from '@/hooks/useAdminNav'
import { financeCurrencyCode } from '@/lib/financeSettings'
import { cn, formatCurrency, formatDate } from '@/lib/utils'
import type {
  PaymentCategorySummaryRow,
  PaymentDepartmentSummaryRow,
  PaymentEmployeeHistoryItem,
  PaymentEmployeeSummary,
  PaymentMonthlyExpenseRow,
  PaymentMonthlySummary,
} from '@/types'

const PAGE_SIZE = 10

type SectionId = 'departments' | 'categories' | 'employees' | 'monthly'

function currentMonthValue() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function monthLabel(value: string | null | undefined) {
  if (!value) return '—'
  const key = String(value).slice(0, 7)
  const [year, month] = key.split('-')
  const date = new Date(Number(year), Number(month) - 1, 1)
  if (Number.isNaN(date.getTime())) return key
  return date.toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
}

function departmentName(row: PaymentDepartmentSummaryRow) {
  return row.department_name || row.department__name || 'Unassigned'
}

function paginateRows<T>(items: T[], page: number) {
  const total = items.length
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE) || 1)
  const currentPage = Math.min(Math.max(page, 1), totalPages)
  const start = (currentPage - 1) * PAGE_SIZE
  return {
    rows: items.slice(start, start + PAGE_SIZE),
    total,
    totalPages,
    currentPage,
  }
}

function AccordionSection({
  title,
  count,
  description,
  open,
  onToggle,
  children,
}: {
  title: string
  count: number
  description: string
  open: boolean
  onToggle: () => void
  children: ReactNode
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#e2e8f0] bg-white">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-gray-50 sm:px-6"
      >
        <ChevronRight
          className={cn(
            'h-5 w-5 shrink-0 text-gray-400 transition-transform',
            open && 'rotate-90',
          )}
        />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-gray-900">
            {title} ({count})
          </p>
          <p className="mt-0.5 text-sm text-gray-500">{description}</p>
        </div>
      </button>
      {open && <div className="border-t border-[#e2e8f0]">{children}</div>}
    </div>
  )
}

function PagedTable({
  columns,
  total,
  page,
  totalPages,
  onPageChange,
  empty,
  children,
}: {
  columns: string[]
  total: number
  page: number
  totalPages: number
  onPageChange: (page: number) => void
  empty: string
  children: ReactNode
}) {
  if (total === 0) {
    return <p className="px-5 py-6 text-sm text-gray-500 sm:px-6">{empty}</p>
  }

  return (
    <>
      <div className="p-4 sm:p-6">
        <AdminDataTable columns={columns}>{children}</AdminDataTable>
      </div>
      <PaginationControls
        currentPage={page}
        totalPages={totalPages}
        totalCount={total}
        onPageChange={onPageChange}
      />
    </>
  )
}

export function ExpenseReportsPage() {
  const { navItems } = useAdminNav()
  const [month, setMonth] = useState(currentMonthValue)
  const [currency, setCurrency] = useState('USD')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [summary, setSummary] = useState<PaymentMonthlySummary | null>(null)
  const [departments, setDepartments] = useState<PaymentDepartmentSummaryRow[]>([])
  const [categories, setCategories] = useState<PaymentCategorySummaryRow[]>([])
  const [employees, setEmployees] = useState<PaymentEmployeeSummary[]>([])
  const [monthlyRows, setMonthlyRows] = useState<PaymentMonthlyExpenseRow[]>([])
  const [openSections, setOpenSections] = useState<Record<SectionId, boolean>>({
    departments: true,
    categories: true,
    employees: true,
    monthly: true,
  })
  const [deptPage, setDeptPage] = useState(1)
  const [categoryPage, setCategoryPage] = useState(1)
  const [employeePage, setEmployeePage] = useState(1)
  const [monthlyPage, setMonthlyPage] = useState(1)
  const [historyPage, setHistoryPage] = useState(1)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyEmployee, setHistoryEmployee] = useState<{
    name: string
    email: string
    department: string | null
    total_reimbursed: string
  } | null>(null)
  const [history, setHistory] = useState<PaymentEmployeeHistoryItem[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { month }
      const [summaryRes, deptRes, categoryRes, employeeRes, monthlyRes, financeRes] =
        await Promise.all([
          getPaymentMonthlySummary(params),
          getPaymentDepartmentSummary(params),
          getPaymentCategorySummary(params),
          getPaymentEmployeeSummary(),
          getPaymentMonthlyExpenses(),
          getFinanceSettings().catch(() => null),
        ])

      setSummary(summaryRes.data)
      setDepartments(deptRes.data.results || [])
      setCategories(categoryRes.data.results || [])
      setEmployees(employeeRes.data.results || [])
      setMonthlyRows(
        (monthlyRes.data.results || []).filter((row) => String(row.month).slice(0, 7) === month),
      )
      setDeptPage(1)
      setCategoryPage(1)
      setEmployeePage(1)
      setMonthlyPage(1)
      if (financeRes?.data.settings) {
        setCurrency(financeCurrencyCode(financeRes.data.settings))
      }
    } catch (err) {
      setError(getApiErrorMessage(err))
      setSummary(null)
      setDepartments([])
      setCategories([])
      setEmployees([])
      setMonthlyRows([])
    } finally {
      setLoading(false)
    }
  }, [month])

  useEffect(() => {
    void load()
  }, [load])

  const deptPaged = useMemo(() => paginateRows(departments, deptPage), [departments, deptPage])
  const categoryPaged = useMemo(
    () => paginateRows(categories, categoryPage),
    [categories, categoryPage],
  )
  const employeePaged = useMemo(
    () => paginateRows(employees, employeePage),
    [employees, employeePage],
  )
  const monthlyPaged = useMemo(
    () => paginateRows(monthlyRows, monthlyPage),
    [monthlyRows, monthlyPage],
  )
  const historyPaged = useMemo(() => paginateRows(history, historyPage), [history, historyPage])

  const toggleSection = (id: SectionId) => {
    setOpenSections((current) => ({ ...current, [id]: !current[id] }))
  }

  const openHistory = async (employeeId: string | number, fallbackName: string) => {
    setHistoryOpen(true)
    setHistoryLoading(true)
    setHistoryPage(1)
    setHistory([])
    setHistoryEmployee({ name: fallbackName, email: '', department: null, total_reimbursed: '0' })
    try {
      const { data } = await getPaymentEmployeeHistory(employeeId)
      setHistoryEmployee({
        name: data.employee.name,
        email: data.employee.email,
        department: data.employee.department,
        total_reimbursed: data.total_reimbursed,
      })
      setHistory(data.history || [])
    } catch (err) {
      setError(getApiErrorMessage(err))
      setHistoryOpen(false)
    } finally {
      setHistoryLoading(false)
    }
  }

  if (loading) {
    return (
      <DashboardLayout
        title="Expense reports"
        subtitle="Company spend and employee reimbursement by month"
        breadcrumb="Expense reports"
        icon={PieChart}
        navItems={navItems}
      >
        <DashboardPageShimmer />
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout
      title="Expense reports"
      subtitle="Company spend and employee reimbursement by month"
      breadcrumb="Expense reports"
      icon={PieChart}
      navItems={navItems}
    >
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="mb-6 flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="report-month">Month</Label>
          <Input
            id="report-month"
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="w-44"
          />
        </div>
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          title="Total claimed"
          value={formatCurrency(summary?.total_claimed || 0, currency)}
          icon={DollarSign}
          description={monthLabel(summary?.month || month)}
        />
        <MetricCard
          title="Awaiting payment"
          value={formatCurrency(summary?.awaiting_payment || 0, currency)}
          icon={DollarSign}
          accent="orange"
        />
        <MetricCard
          title="Paid"
          value={formatCurrency(summary?.paid_amount || 0, currency)}
          icon={DollarSign}
          accent="green"
        />
        <MetricCard
          title="Employees"
          value={summary?.employee_count ?? 0}
          icon={Users}
          description={`${summary?.report_count ?? 0} reports`}
          accent="purple"
        />
      </div>

      <div className="space-y-3">
        <AccordionSection
          title="By department"
          count={departments.length}
          description="Claimed amount for the selected month."
          open={openSections.departments}
          onToggle={() => toggleSection('departments')}
        >
          <PagedTable
            columns={['Department', 'Reports', 'Amount']}
            total={deptPaged.total}
            page={deptPaged.currentPage}
            totalPages={deptPaged.totalPages}
            onPageChange={setDeptPage}
            empty="No department totals for this month."
          >
            {deptPaged.rows.map((row) => (
              <AdminTableRow key={String(row.department_id ?? departmentName(row))}>
                <AdminTableCell>
                  <span className="inline-flex items-center gap-2">
                    <Building2 className="h-4 w-4 text-gray-400" />
                    {departmentName(row)}
                  </span>
                </AdminTableCell>
                <AdminTableCell>{row.report_count}</AdminTableCell>
                <AdminTableCell>{formatCurrency(row.total_amount, currency)}</AdminTableCell>
              </AdminTableRow>
            ))}
          </PagedTable>
        </AccordionSection>

        <AccordionSection
          title="By category"
          count={categories.length}
          description="Line-item spend for the selected month."
          open={openSections.categories}
          onToggle={() => toggleSection('categories')}
        >
          <PagedTable
            columns={['Category', 'Reports', 'Amount']}
            total={categoryPaged.total}
            page={categoryPaged.currentPage}
            totalPages={categoryPaged.totalPages}
            onPageChange={setCategoryPage}
            empty="No category totals for this month."
          >
            {categoryPaged.rows.map((row) => (
              <AdminTableRow key={row.category || 'uncategorized'}>
                <AdminTableCell>{row.category || 'Uncategorized'}</AdminTableCell>
                <AdminTableCell>{row.report_count ?? '—'}</AdminTableCell>
                <AdminTableCell>{formatCurrency(row.total_amount, currency)}</AdminTableCell>
              </AdminTableRow>
            ))}
          </PagedTable>
        </AccordionSection>

        <AccordionSection
          title="Employees"
          count={employees.length}
          description="Lifetime reimbursed totals. Open a row for month-by-month history."
          open={openSections.employees}
          onToggle={() => toggleSection('employees')}
        >
          <PagedTable
            columns={['Employee', 'Department', 'Reports', 'Paid', 'Reimbursed', '']}
            total={employeePaged.total}
            page={employeePaged.currentPage}
            totalPages={employeePaged.totalPages}
            onPageChange={setEmployeePage}
            empty="No employee reimbursement data yet."
          >
            {employeePaged.rows.map((row) => (
              <AdminTableRow key={row.employee_id}>
                <AdminTableCell>
                  <div>
                    <p className="font-medium text-gray-900">{row.name}</p>
                    <p className="text-xs text-gray-500">{row.email}</p>
                  </div>
                </AdminTableCell>
                <AdminTableCell>{row.department || '—'}</AdminTableCell>
                <AdminTableCell>{row.total_reports}</AdminTableCell>
                <AdminTableCell>{row.paid_reports}</AdminTableCell>
                <AdminTableCell>{formatCurrency(row.total_reimbursed, currency)}</AdminTableCell>
                <AdminTableCell>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void openHistory(row.employee_id, row.name)}
                  >
                    History
                  </Button>
                </AdminTableCell>
              </AdminTableRow>
            ))}
          </PagedTable>
        </AccordionSection>

        <AccordionSection
          title={`Monthly reports · ${monthLabel(month)}`}
          count={monthlyRows.length}
          description="Submitted reimbursement reports for this month."
          open={openSections.monthly}
          onToggle={() => toggleSection('monthly')}
        >
          <PagedTable
            columns={['Employee', 'Status', 'Amount', 'Submitted', 'Paid']}
            total={monthlyPaged.total}
            page={monthlyPaged.currentPage}
            totalPages={monthlyPaged.totalPages}
            onPageChange={setMonthlyPage}
            empty="No monthly reports for this period."
          >
            {monthlyPaged.rows.map((row) => (
              <AdminTableRow key={row.report_id}>
                <AdminTableCell>
                  <div>
                    <p className="font-medium text-gray-900">{row.employee.name}</p>
                    <p className="text-xs text-gray-500">{row.employee.email}</p>
                  </div>
                </AdminTableCell>
                <AdminTableCell>
                  <StatusBadge status={row.status} />
                </AdminTableCell>
                <AdminTableCell>
                  {formatCurrency(row.total_amount, row.currency || currency)}
                </AdminTableCell>
                <AdminTableCell>{formatDate(row.submitted_at)}</AdminTableCell>
                <AdminTableCell>{formatDate(row.paid_at)}</AdminTableCell>
              </AdminTableRow>
            ))}
          </PagedTable>
        </AccordionSection>
      </div>

      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{historyEmployee?.name || 'Employee history'}</DialogTitle>
            <DialogDescription>
              {historyEmployee?.email}
              {historyEmployee?.department ? ` · ${historyEmployee.department}` : ''}
            </DialogDescription>
          </DialogHeader>
          {historyLoading ? (
            <p className="text-sm text-gray-500">Loading history…</p>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-gray-700">
                Total reimbursed:{' '}
                <span className="font-medium">
                  {formatCurrency(historyEmployee?.total_reimbursed || 0, currency)}
                </span>
              </p>
              <div className="overflow-hidden rounded-lg border border-[#e2e8f0]">
                <PagedTable
                  columns={['Month', 'Status', 'Amount', 'Paid']}
                  total={historyPaged.total}
                  page={historyPaged.currentPage}
                  totalPages={historyPaged.totalPages}
                  onPageChange={setHistoryPage}
                  empty="No reimbursement history for this employee."
                >
                  {historyPaged.rows.map((item) => (
                    <AdminTableRow key={item.report_id}>
                      <AdminTableCell>{monthLabel(String(item.month))}</AdminTableCell>
                      <AdminTableCell>
                        <StatusBadge status={item.status} />
                      </AdminTableCell>
                      <AdminTableCell>{formatCurrency(item.total_amount, currency)}</AdminTableCell>
                      <AdminTableCell>{formatDate(item.paid_at)}</AdminTableCell>
                    </AdminTableRow>
                  ))}
                </PagedTable>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  )
}
