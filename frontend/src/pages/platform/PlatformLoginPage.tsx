import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import platformLoginImg from '@/assets/platform_login.png'
import { getApiErrorMessage, useAuth } from '@/context/AuthContext'
import { AuthSplitLayout } from '@/components/layout/AuthSplitLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import logo from '@/assets/logo.png'

export function PlatformLoginPage() {
  const { login, logout } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(email, password)
      const stored = localStorage.getItem('zepex_user')
      const user = stored ? JSON.parse(stored) : null
      if (user?.role !== 'PLATFORM_OWNER' && user?.role !== 'PLATFORM_ADMIN') {
        logout()
        setError('This account is not authorized for platform access.')
        return
      }
      if (remember) {
        localStorage.setItem('zepex_remember_platform_email', email)
      } else {
        localStorage.removeItem('zepex_remember_platform_email')
      }
      navigate('/platform')
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthSplitLayout
      heroImage={platformLoginImg}
    >
      <div className="mb-8 flex items-center gap-2">
        <img src={logo} alt="ZepEX" className="h-full w-25" />
      </div>

      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Platform Sign In</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Use your platform owner credentials.
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
          {loading ? 'Signing in...' : 'Sign In to platform'}
        </Button>
      </form>
    </AuthSplitLayout>
  )
}
