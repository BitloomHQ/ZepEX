import type { NavItem } from '@/components/layout/DashboardLayout'
import { platformNavWithAudit } from '@/components/layout/DashboardLayout'
import { buildAdminNav } from '@/lib/adminNav'
import {
  buildAccountsNav,
  buildEmployeeNav,
  buildManagerNav,
} from '@/lib/rolePermissions'
import type { User, UserRole } from '@/types'

export function getNavForUser(user: User | null, adminNavItems?: NavItem[]): NavItem[] {
  if (!user) return buildEmployeeNav(null)

  switch (user.role as UserRole) {
    case 'COMPANY_ADMIN':
      return adminNavItems ?? buildAdminNav(user)
    case 'MANAGER':
      return buildManagerNav(user)
    case 'EMPLOYEE':
      return buildEmployeeNav(user)
    case 'ACCOUNTS':
      return buildAccountsNav(user)
    case 'PLATFORM_OWNER':
    case 'PLATFORM_ADMIN':
      return platformNavWithAudit
    default:
      return buildEmployeeNav(user)
  }
}

export function userRoleLabel(user: User | null): string {
  if (!user) return ''
  if (user.company_role) return user.company_role
  const labels: Record<string, string> = {
    PLATFORM_OWNER: 'Platform Owner',
    PLATFORM_ADMIN: 'Platform Admin',
    COMPANY_ADMIN: 'Company Admin',
    MANAGER: 'Manager',
    EMPLOYEE: 'Employee',
    ACCOUNTS: 'Accounts',
  }
  return labels[user.role] ?? user.role
}
