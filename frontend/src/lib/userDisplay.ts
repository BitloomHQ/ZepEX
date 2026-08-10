import { getBackendOrigin, resolveBackendAssetUrl } from '@/lib/backendUrl'

export function resolveMediaUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined

  // Local previews from URL.createObjectURL or data URLs must pass through unchanged.
  if (url.startsWith('blob:') || url.startsWith('data:')) {
    return url
  }

  if (url.startsWith('http://') || url.startsWith('https://')) {
    try {
      const parsed = new URL(url)
      // Only rewrite Django absolute /media/ URLs that point at the API host.
      // Leave S3 / CloudFront signed URLs untouched.
      if (parsed.pathname.startsWith('/media/')) {
        const backendOrigin = getBackendOrigin()
        const isBackendHost =
          !backendOrigin || parsed.origin === new URL(backendOrigin).origin
        if (isBackendHost) {
          return resolveBackendAssetUrl(parsed.pathname)
        }
      }
    } catch {
      return url
    }
    return url
  }

  return resolveBackendAssetUrl(url.startsWith('/') ? url : `/${url}`)
}

export function getUserInitial(
  firstName?: string | null,
  lastName?: string | null,
  email?: string | null,
): string {
  const first = firstName?.trim()
  if (first) return first[0].toUpperCase()

  const last = lastName?.trim()
  if (last) return last[0].toUpperCase()

  const mail = email?.trim()
  if (mail) return mail[0].toUpperCase()

  return '?'
}

export function getUserDisplayName(
  firstName?: string | null,
  lastName?: string | null,
  email?: string | null,
): string {
  const fullName = `${firstName ?? ''} ${lastName ?? ''}`.trim()
  return fullName || email?.trim() || 'User'
}
