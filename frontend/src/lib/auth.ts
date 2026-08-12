import type { User, UserPermissions, UserRole } from '@/types'
import { resolveUserPermissions } from '@/lib/permissions'

export const roleHome: Record<UserRole, string> = {
  PLATFORM_OWNER: '/platform',
  PLATFORM_ADMIN: '/platform',
  COMPANY_ADMIN: '/admin',
  MANAGER: '/manager',
  EMPLOYEE: '/employee',
  ACCOUNTS: '/accounts',
}

const redirectPathMap: Record<string, string> = {
  '/platform-dashboard': '/platform',
  '/company-admin-dashboard': '/admin',
  '/employee-dashboard': '/employee',
  '/approver-dashboard': '/manager',
  '/payment-dashboard': '/accounts',
}

export interface LoginUserPayload {
  id: number
  email: string
  first_name: string
  last_name: string
  system_role: UserRole
  company_role?: string | null
  company_role_id?: number | null
  permissions?: UserPermissions
  company: User['company']
  department: User['department']
}

export function normalizeLoginUser(user: LoginUserPayload): User {
  return {
    id: user.id,
    email: user.email,
    first_name: user.first_name,
    last_name: user.last_name,
    role: user.system_role,
    system_role: user.system_role,
    company_role: user.company_role ?? null,
    company_role_id: user.company_role_id ?? null,
    permissions: resolveUserPermissions(user.system_role, user.permissions),
    company: user.company,
    department: user.department,
  }
}

export function resolvePostLoginPath(user: User, redirectTo?: string | null): string {
  if (redirectTo && redirectPathMap[redirectTo]) return redirectPathMap[redirectTo]
  return roleHome[user.role] ?? '/employee'
}

export function canAccessRoute(
  user: User,
  allowedRoles: UserRole[] = [],
  permission?: keyof UserPermissions,
  anyPermissions?: (keyof UserPermissions)[],
): boolean {
  if (anyPermissions?.some((key) => user.permissions?.[key])) return true

  if (allowedRoles.length > 0 && allowedRoles.includes(user.role)) {
    if (permission) return Boolean(user.permissions?.[permission])
    return true
  }

  return false
}

export function defaultHomeForUser(user: User): string {
  return resolvePostLoginPath(user)
}
