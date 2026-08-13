import { Bell, CheckCheck } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import {
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { formatDateTime } from '@/lib/utils'
import type { ExpenseNotification } from '@/types'

const POLL_INTERVAL_MS = 60_000

function getDropdownStyle(button: HTMLButtonElement): CSSProperties {
  const rect = button.getBoundingClientRect()
  return {
    position: 'fixed',
    top: rect.bottom + 8,
    right: Math.max(16, window.innerWidth - rect.right),
    width: Math.min(384, window.innerWidth - 32),
    zIndex: 60,
  }
}

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [notifications, setNotifications] = useState<ExpenseNotification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [error, setError] = useState('')
  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties>({})
  const buttonRef = useRef<HTMLButtonElement>(null)

  const updateDropdownPosition = useCallback(() => {
    if (!buttonRef.current) return
    setDropdownStyle(getDropdownStyle(buttonRef.current))
  }, [])

  const loadNotifications = useCallback(async () => {
    try {
      const { data } = await getNotifications()
      setNotifications(data.results)
      setUnreadCount(data.unread_count)
      setError('')
    } catch (err) {
      setError(getApiErrorMessage(err))
    }
  }, [])

  useEffect(() => {
    void loadNotifications()
    const interval = window.setInterval(() => {
      void loadNotifications()
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [loadNotifications])

  useEffect(() => {
    if (!open) return

    updateDropdownPosition()

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node
      if (buttonRef.current?.contains(target)) return
      if (document.getElementById('notification-dropdown-panel')?.contains(target)) return
      setOpen(false)
    }

    const handleReposition = () => updateDropdownPosition()

    document.addEventListener('mousedown', handlePointerDown)
    window.addEventListener('resize', handleReposition)
    window.addEventListener('scroll', handleReposition, true)

    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      window.removeEventListener('resize', handleReposition)
      window.removeEventListener('scroll', handleReposition, true)
    }
  }, [open, updateDropdownPosition])

  const handleOpen = async () => {
    const nextOpen = !open
    setOpen(nextOpen)
    if (nextOpen) {
      setLoading(true)
      await loadNotifications()
      setLoading(false)
      updateDropdownPosition()
    }
  }

  const handleMarkRead = async (notification: ExpenseNotification) => {
    if (notification.is_read) return

    try {
      const { data } = await markNotificationRead(notification.id)
      setNotifications((current) =>
        current.map((item) =>
          item.id === notification.id ? data.notification : item,
        ),
      )
      setUnreadCount((current) => Math.max(0, current - 1))
    } catch (err) {
      setError(getApiErrorMessage(err))
    }
  }

  const handleMarkAllRead = async () => {
    if (unreadCount === 0) return

    try {
      const { data } = await markAllNotificationsRead()
      setNotifications((current) =>
        current.map((item) => ({
          ...item,
          is_read: true,
          read_at: item.read_at ?? new Date().toISOString(),
        })),
      )
      setUnreadCount(0)
      setError('')
      if (data.updated_count > 0) {
        await loadNotifications()
      }
    } catch (err) {
      setError(getApiErrorMessage(err))
    }
  }

  const dropdown = open
    ? createPortal(
        <div
          id="notification-dropdown-panel"
          style={dropdownStyle}
          className="overflow-hidden rounded-xl border border-[#e2e8f0] bg-white shadow-lg"
        >
          <div className="flex items-center justify-between border-b border-[#e2e8f0] px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-gray-900">Notifications</p>
              <p className="text-xs text-gray-500">
                {unreadCount > 0 ? `${unreadCount} unread` : 'All caught up'}
              </p>
            </div>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => void handleMarkAllRead()}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-primary/5"
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {loading && notifications.length === 0 ? (
              <p className="px-4 py-6 text-sm text-gray-500">Loading notifications…</p>
            ) : notifications.length === 0 ? (
              <p className="px-4 py-6 text-sm text-gray-500">No notifications yet.</p>
            ) : (
              notifications.map((notification) => (
                <button
                  key={notification.id}
                  type="button"
                  onClick={() => void handleMarkRead(notification)}
                  className={`block w-full border-b border-[#e2e8f0] px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-gray-50 ${
                    notification.is_read ? 'bg-white' : 'bg-blue-50/40'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900">{notification.title}</p>
                      <p className="mt-1 text-sm text-gray-600">{notification.message}</p>
                      <p className="mt-2 text-xs text-gray-400">
                        {formatDateTime(notification.created_at)}
                      </p>
                    </div>
                    {!notification.is_read && (
                      <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-primary" />
                    )}
                  </div>
                </button>
              ))
            )}
          </div>

          {error && (
            <p className="border-t border-[#e2e8f0] px-4 py-2 text-xs text-red-600">{error}</p>
          )}
        </div>,
        document.body,
      )
    : null

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => void handleOpen()}
        className="relative inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[#e2e8f0] bg-white text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900"
        aria-label="Notifications"
        aria-expanded={open}
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 inline-flex min-h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[11px] font-semibold text-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>
      {dropdown}
    </>
  )
}
