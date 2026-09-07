import { useEffect, useState } from 'react'
import { getCompanyAdminDashboard } from '@/api'
import type { NavItem } from '@/components/layout/DashboardLayout'
import { useAuth } from '@/context/AuthContext'
import { buildAdminNav } from '@/lib/adminNav'
import { fetchBambooHRConnected } from '@/lib/bambooHRConnection'
import { getNavForUser } from '@/lib/dashboardNav'
import { isSetupComplete } from '@/lib/adminSetup'

let cachedSetup: Record<string, boolean> | null = null
let cachePromise: Promise<Record<string, boolean>> | null = null

export function fetchAdminSetupStatus(): Promise<Record<string, boolean>> {
  if (cachedSetup) return Promise.resolve(cachedSetup)
  if (!cachePromise) {
    cachePromise = getCompanyAdminDashboard()
      .then((res) => {
        const status = res.data.setup_status ?? {}
        cachedSetup = status
        return status
      })
      .catch(() => {
        const status: Record<string, boolean> = {}
        cachedSetup = status
        return status
      })
  }
  return cachePromise!
}

export function invalidateAdminSetupCache() {
  cachedSetup = null
  cachePromise = null
}

function navForUser(user: Parameters<typeof getNavForUser>[0]) {
  if (!user || user.role === 'COMPANY_ADMIN') return buildAdminNav(user)
  return getNavForUser(user)
}

// The Payroll screen only makes sense once BambooHR is connected — hide the
// nav entry until we know the connection state to avoid dead-ending users.
function withPayrollGate(items: NavItem[], bambooConnected: boolean): NavItem[] {
  if (bambooConnected) return items
  return items.filter((item) => item.to !== '/admin/payroll')
}

export function useAdminNav() {
  const { user } = useAuth()
  const [navItems, setNavItems] = useState<NavItem[]>(() => withPayrollGate(navForUser(user), false))
  const [setupComplete, setSetupComplete] = useState(false)
  const [setupStatus, setSetupStatus] = useState<Record<string, boolean>>({})
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let bambooConnected = false
    setNavItems(withPayrollGate(navForUser(user), bambooConnected))
    Promise.all([fetchAdminSetupStatus(), fetchBambooHRConnected()]).then(
      ([status, connected]) => {
        bambooConnected = connected
        const complete = isSetupComplete(status)
        setSetupStatus(status)
        setSetupComplete(complete)
        setNavItems(withPayrollGate(navForUser(user), bambooConnected))
        setReady(true)
      },
    )
  }, [user])

  return { navItems, setupComplete, setupStatus, ready }
}
