import {
  Building2,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Menu,
  ScrollText,
  Settings,
  Shield,
  UserCog,
  Users,
  Wallet,
  X,
} from 'lucide-react'

import { useState, type ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { SidebarUserSummary } from '@/components/layout/SidebarUserSummary'
import { useAuth } from '@/context/AuthContext'
import { cn } from '@/lib/utils'
import logo from '@/assets/logo.png'
export interface NavItem {
  label: string
  to: string
  icon: React.ComponentType<{ className?: string }>
}

interface DashboardLayoutProps {
  title: string
  subtitle?: string
  breadcrumb?: string
  icon?: React.ComponentType<{ className?: string }>
  headerLeading?: ReactNode
  headerAction?: ReactNode
  navItems: NavItem[]
  children: ReactNode
  portal?: 'platform' | 'tenant'
}

export function DashboardLayout({
  title,
  subtitle,
  breadcrumb,
  icon: PageIcon,
  headerLeading,
  headerAction,
  navItems,
  children,
  portal = 'tenant',
}: DashboardLayoutProps) {
  const { logout, user } = useAuth()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate(portal === 'platform' ? '/platform/login' : '/login')
  }

  return (
    <div className="min-h-screen w-full overflow-x-clip bg-[#f3f4f6] lg:flex">
      {sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="Close sidebar"
        />
      )}

      <aside
        className={cn(
          'z-50 flex h-screen w-[min(15rem,85vw)] flex-col overflow-hidden border-r border-[#e2e8f0] bg-white lg:sticky lg:top-0 lg:w-56 lg:shrink-0',
          sidebarOpen ? 'fixed inset-y-0 left-0' : 'hidden lg:flex',
        )}
      >
        <div className="flex h-16 shrink-0 items-center gap-2.5 px-5">
          <img src={logo} alt="ZepEX" className="h-10 w-25" />
          <button
            type="button"
            className="ml-auto lg:hidden"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to.split('/').length <= 2}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-[#eff6ff] text-primary'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
                )
              }
            >
              <item.icon className="h-[18px] w-[18px]" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="shrink-0 space-y-2 border-t border-[#e2e8f0] p-4">
          {user && <SidebarUserSummary />}
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-red-500 px-3 py-2.5 text-sm font-medium text-red-500 transition-colors hover:bg-red-50"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-h-screen w-full min-w-0 flex-1 flex-col lg:min-h-0">
        <div className="sticky top-0 z-30 flex h-12 shrink-0 items-center border-b border-[#e2e8f0] bg-[#f3f4f6] px-4 lg:hidden">
          <button type="button" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            <Menu className="h-5 w-5 text-gray-600" />
          </button>
        </div>

        <main className="box-border w-full min-w-0 max-w-full flex-1 overflow-x-clip bg-[#f3f4f6] p-4 sm:p-6 lg:p-8">
          {breadcrumb && (
            <p className="mb-4 text-sm text-gray-400">
              Home <span className="mx-1.5 text-gray-300">&gt;</span> {breadcrumb}
            </p>
          )}

          <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
            <div className="flex min-w-0 items-start gap-4">
              {headerLeading}
              {!headerLeading && PageIcon && (
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary text-white shadow-sm">
                  <PageIcon className="h-7 w-7" />
                </div>
              )}
              <div className="min-w-0 pt-1">
                <h1 className="text-2xl font-bold tracking-tight text-gray-900">{title}</h1>
                {subtitle && <p className="mt-1 text-sm text-gray-500">{subtitle}</p>}
              </div>
            </div>
            {headerAction && (
              <div className="flex flex-wrap items-center gap-2">{headerAction}</div>
            )}
          </div>

          {children}
        </main>
      </div>
    </div>
  )
}

export const platformNav: NavItem[] = [
  { label: 'Dashboard', to: '/platform', icon: LayoutDashboard },
  { label: 'Companies', to: '/platform/companies', icon: Building2 },
  { label: 'Company Requests', to: '/platform/requests', icon: ClipboardList },
  { label: 'Platform Users', to: '/platform/users', icon: Users },
]

export const platformNavWithAudit: NavItem[] = [
  ...platformNav,
  { label: 'Audit Logs', to: '/platform/audit-logs', icon: ScrollText },
]

/** @deprecated Use buildAdminNav() from @/lib/adminNav */
export const adminNav: NavItem[] = [
  { label: 'Dashboard', to: '/admin', icon: LayoutDashboard },
  { label: 'Departments', to: '/admin/departments', icon: Building2 },
  { label: 'Employees', to: '/admin/employees', icon: Users },
  { label: 'Roles', to: '/admin/roles', icon: UserCog },
  { label: 'Policy', to: '/admin/policy', icon: Shield },
  { label: 'Settings', to: '/admin/settings', icon: Settings },
  { label: 'Audit Logs', to: '/admin/audit-logs', icon: ScrollText },
]

export const employeeNav: NavItem[] = [
  { label: 'Dashboard', to: '/employee', icon: LayoutDashboard },
  { label: 'Expenses', to: '/employee/expenses', icon: Wallet },
]

export const managerNav: NavItem[] = [
  { label: 'Dashboard', to: '/manager', icon: LayoutDashboard },
  { label: 'Pending Reports', to: '/manager/reports', icon: Wallet },
]

export const accountsNav: NavItem[] = [
  { label: 'Dashboard', to: '/accounts', icon: LayoutDashboard },
  { label: 'Approved Reports', to: '/accounts/reports', icon: Wallet },
]
