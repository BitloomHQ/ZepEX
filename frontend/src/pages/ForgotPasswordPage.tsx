import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import loginImg from '@/assets/login_img.png'
import { forgotPassword } from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AuthSplitLayout } from '@/components/layout/AuthSplitLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/lib/toast'
import logo from '@/assets/logo.png'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const { data } = await forgotPassword(email)
      toast.success(data.message)
      setSent(true)
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
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Forgot password</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {sent
            ? 'Check your email for a password reset link. It expires automatically.'
            : "Enter your email and we'll send you a password reset link."}
        </p>
      </div>

      {sent ? (
        <div className="space-y-5">
          <p className="rounded-lg bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800">
            If an account exists for <span className="font-medium">{email}</span>, a reset link has been
            sent.
          </p>
          <Button
            type="button"
            variant="outline"
            className="h-11 w-full text-base"
            disabled={loading}
            onClick={() => {
              setSent(false)
              setError('')
            }}
          >
            Use a different email
          </Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="email">Email address</Label>
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

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700">{error}</p>
          )}

          <Button type="submit" className="h-11 w-full text-base" disabled={loading}>
            {loading ? 'Sending...' : 'Send reset link'}
          </Button>
        </form>
      )}

      <p className="mt-8 text-center text-sm text-muted-foreground">
        <Link to="/login" className="font-semibold text-primary hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthSplitLayout>
  )
}
