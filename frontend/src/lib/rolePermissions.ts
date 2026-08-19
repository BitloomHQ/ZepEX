import { CheckCircle2, ClipboardList, LayoutDashboard, Wallet } from 'lucide-react'
import type { NavItem } from '@/components/layout/DashboardLayout'
import type { User, UserPermissions } from '@/types'
import { mergeRoleNavWithAdminPages } from '@/lib/adminNav'
import { approvedReportsPath, pendingReportsPath } from '@/lib/reportQueuePaths'

export function hasPermission(user: User | null, permission: keyof UserPermissions) {
  return Boolean(user?.permissions?.[permission])
}

export function canUploadReceipt(user: User | null) {
  return hasPermission(user, 'can_upload_receipt')
}

export function canSubmitExpense(user: User | null) {
  return hasPermission(user, 'can_submit_expense')
}

export function canManageOwnExpenses(user: User | null) {
  return canUploadReceipt(user) || canSubmitExpense(user)
}

export function canApproveExpense(user: User | null) {
  return hasPermission(user, 'can_approve_expense')
}

export function canMarkPaid(user: User | null) {
  return hasPermission(user, 'can_mark_paid')
}

function appendReportQueueNav(items: NavItem[], user: User | null, baseRole: User['role']) {
  if (!canApproveExpense(user) && !canMarkPaid(user)) return

  items.push({
    label: 'Pending Reports',
    to: pendingReportsPath(baseRole),
    icon: ClipboardList,
  })
  items.push({
    label: 'Approved Reports',
    to: approvedReportsPath(baseRole),
    icon: CheckCircle2,
  })
}

export function expensePathForUser(user: User | null) {
  switch (user?.role) {
    case 'MANAGER':
      return '/manager/expenses'
    case 'ACCOUNTS':
      return '/accounts/expenses'
    case 'EMPLOYEE':
    default:
      return '/employee/expenses'
  }
}

export function buildEmployeeNav(user: User | null): NavItem[] {
  const items: NavItem[] = [
    { label: 'Dashboard', to: '/employee', icon: LayoutDashboard },
  ]
  if (canManageOwnExpenses(user)) {
    items.push({ label: 'Expenses', to: '/employee/expenses', icon: Wallet })
  }
  return mergeRoleNavWithAdminPages(items, user)
}

export function buildManagerNav(user: User | null): NavItem[] {
  const items: NavItem[] = [
    { label: 'Dashboard', to: '/manager', icon: LayoutDashboard },
  ]
  if (canManageOwnExpenses(user)) {
    items.push({ label: 'My Expenses', to: '/manager/expenses', icon: Wallet })
  }
  appendReportQueueNav(items, user, 'MANAGER')
  return mergeRoleNavWithAdminPages(items, user)
}

export function buildAccountsNav(user: User | null): NavItem[] {
  const items: NavItem[] = [
    { label: 'Dashboard', to: '/accounts', icon: LayoutDashboard },
  ]
  if (canManageOwnExpenses(user)) {
    items.push({ label: 'My Expenses', to: '/accounts/expenses', icon: Wallet })
  }
  appendReportQueueNav(items, user, 'ACCOUNTS')
  return mergeRoleNavWithAdminPages(items, user)
}

export function navItemsForUser(user: User | null): NavItem[] {
  if (!user) return buildEmployeeNav(null)

  switch (user.role) {
    case 'MANAGER':
      return buildManagerNav(user)
    case 'ACCOUNTS':
      return buildAccountsNav(user)
    case 'EMPLOYEE':
    default:
      return buildEmployeeNav(user)
  }
}
