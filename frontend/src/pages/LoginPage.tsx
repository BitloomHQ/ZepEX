
import { useState, useEffect, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import loginImg from '@/assets/login_img.png'
import { getApiErrorMessage, useAuth } from '@/context/AuthContext'
import { AuthSplitLayout } from '@/components/layout/AuthSplitLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import logo from '@/assets/logo.png'
import { toast } from '@/lib/toast'

export function LoginPage() {
  const { login, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const message = (location.state as { message?: string } | null)?.message
    if (message) {
      toast.success(message)
      navigate(location.pathname, { replace: true, state: null })
    }
  }, [location.pathname, location.state, navigate])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const redirect = await login(email, password)
      const stored = localStorage.getItem('zepex_user')
      const user = stored ? JSON.parse(stored) : null
      if (user?.role === 'PLATFORM_OWNER' || user?.role === 'PLATFORM_ADMIN') {
        logout()
        setError('Platform accounts must sign in at /platform/login')
        return
      }
      if (remember) {
        localStorage.setItem('zepex_remember_email', email)
      } else {
        localStorage.removeItem('zepex_remember_email')
      }
      navigate(redirect)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthSplitLayout heroImage={loginImg}>
      <div className="mb-8 flex items-center gap-2">
        <img src={logo} alt="ZepEX" className="h-full w-25" />
      </div>

      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Welcome Back</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Sign in to access the best expense services at your fingertips.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="email">Email Address</Label>
          <Input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Enter your email address"
            className="h-11"
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link
              to="/forgot-password"
              className="text-sm font-medium text-primary hover:underline"
            >
              Forgot Password
            </Link>
          </div>
          <PasswordInput
            id="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter your password here"
            className="h-11"
            autoComplete="current-password"
          />
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700">{error}</p>
        )}

        <Button type="submit" className="h-11 w-full text-base" disabled={loading}>
          {loading ? 'Signing in...' : 'Sign In'}
        </Button>
      </form>

      <div className="mt-8 flex items-center gap-3">
        <div className="h-px flex-1 bg-border" />
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Or
        </span>
        <div className="h-px flex-1 bg-border" />
      </div>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        New Company?{' '}
        <Link to="/register" className="font-semibold text-primary hover:underline">
          Register now
        </Link>
      </p>
    </AuthSplitLayout>
  )
}
