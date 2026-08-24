import type { NavItem } from '@/components/layout/DashboardLayout'
import {
  Building2,
  ClipboardList,
  GitBranch,
  LayoutDashboard,
  PieChart,
  ScrollText,
  Settings,
  Shield,
  Plug,
  UserCog,
  Users,
} from 'lucide-react'
import type { User, UserPermissions } from '@/types'

export const adminNavBase: NavItem[] = [
  { label: 'Dashboard', to: '/admin', icon: LayoutDashboard },
  { label: 'Departments', to: '/admin/departments', icon: Building2 },
  { label: 'Employees', to: '/admin/employees', icon: Users },
  { label: 'Roles', to: '/admin/roles', icon: UserCog },
  { label: 'Workflow', to: '/admin/workflow', icon: GitBranch },
  { label: 'Policy', to: '/admin/policy', icon: Shield },
  { label: 'Reports', to: '/admin/reports', icon: ClipboardList },
  { label: 'Expense reports', to: '/expense-reports', icon: PieChart },
  { label: 'Settings', to: '/admin/settings', icon: Settings },
  { label: 'Integrations', to: '/admin/integrations', icon: Plug },
  { label: 'Audit Logs', to: '/admin/audit-logs', icon: ScrollText },
]

function hasFlag(user: User | null, key: keyof UserPermissions) {
  return Boolean(user?.permissions?.[key])
}

function canSeeAdminNavItem(user: User | null, to: string) {
  if (!user) return false
  if (user.role === 'COMPANY_ADMIN') return true

  switch (to) {
    case '/admin':
      return false
    case '/admin/departments':
      return hasFlag(user, 'can_manage_departments')
    case '/admin/employees':
      return hasFlag(user, 'can_manage_employees') || hasFlag(user, 'can_manage_users')
    case '/admin/roles':
      return hasFlag(user, 'can_manage_roles')
    case '/admin/workflow':
      return hasFlag(user, 'can_manage_workflow')
    case '/admin/policy':
      return hasFlag(user, 'can_manage_policy')
    case '/admin/reports':
      return hasFlag(user, 'can_view_all_reports')
    case '/expense-reports':
      return (
        hasFlag(user, 'can_view_company_reports') ||
        hasFlag(user, 'can_view_all_reports') ||
        hasFlag(user, 'can_mark_paid')
      )
    case '/admin/settings':
      return hasFlag(user, 'can_manage_company') || hasFlag(user, 'can_manage_policy')
    case '/admin/integrations':
      return hasFlag(user, 'can_manage_integrations') || hasFlag(user, 'can_view_integrations')
    case '/admin/audit-logs':
      return hasFlag(user, 'can_view_audit_logs')
    default:
      return false
  }
}

export function buildAdminNav(user?: User | null): NavItem[] {
  if (!user || user.role === 'COMPANY_ADMIN') {
    return [...adminNavBase]
  }
  return adminNavBase.filter((item) => canSeeAdminNavItem(user, item.to))
}

export function mergeRoleNavWithAdminPages(items: NavItem[], user: User | null): NavItem[] {
  const extras = buildAdminNav(user).filter((item) => item.to !== '/admin')
  const existing = new Set(items.map((item) => item.to))
  return [...items, ...extras.filter((item) => !existing.has(item.to))]
}
