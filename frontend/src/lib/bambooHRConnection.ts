import { getBambooHRStatus } from '@/api'

let cachedConnected: boolean | null = null
let cachePromise: Promise<boolean> | null = null

export function fetchBambooHRConnected(): Promise<boolean> {
  if (cachedConnected !== null) return Promise.resolve(cachedConnected)
  if (!cachePromise) {
    cachePromise = getBambooHRStatus()
      .then((res) => {
        const connected = Boolean(res.data.connected)
        cachedConnected = connected
        return connected
      })
      .catch(() => {
        cachedConnected = false
        return false
      })
  }
  return cachePromise
}

export function invalidateBambooHRConnectionCache() {
  cachedConnected = null
  cachePromise = null
}
