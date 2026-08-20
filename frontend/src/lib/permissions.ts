import type { User, UserPermissions, UserRole } from '@/types'

export const COMPANY_ADMIN_PERMISSIONS: UserPermissions = {
  can_upload_receipt: true,
  can_submit_expense: true,
  can_approve_expense: true,
  can_mark_paid: true,
  can_manage_company: true,
  can_manage_roles: true,
  can_manage_employees: true,
  can_manage_departments: true,
  can_manage_users: true,
  can_manage_policy: true,
  can_manage_workflow: true,
  can_view_company_reports: true,
  can_view_all_reports: true,
  can_view_audit_logs: true,
}

const EMPTY_PERMISSIONS: UserPermissions = {
  can_upload_receipt: false,
  can_submit_expense: false,
  can_approve_expense: false,
  can_mark_paid: false,
  can_manage_company: false,
  can_manage_roles: false,
  can_manage_employees: false,
  can_manage_departments: false,
  can_manage_users: false,
  can_manage_policy: false,
  can_manage_workflow: false,
  can_view_company_reports: false,
  can_view_all_reports: false,
  can_view_audit_logs: false,
}

export function resolveUserPermissions(
  role: UserRole,
  permissions?: Partial<UserPermissions> | null,
): UserPermissions {
  if (role === 'COMPANY_ADMIN') {
    return COMPANY_ADMIN_PERMISSIONS
  }

  return {
    ...EMPTY_PERMISSIONS,
    ...permissions,
    can_manage_users: permissions?.can_manage_users ?? permissions?.can_manage_employees ?? false,
    can_view_all_reports:
      permissions?.can_view_all_reports ?? permissions?.can_view_company_reports ?? false,
  }
}

export function permissionsForUser(user: User | null): UserPermissions {
  if (!user) return EMPTY_PERMISSIONS
  return resolveUserPermissions(user.role, user.permissions)
}
