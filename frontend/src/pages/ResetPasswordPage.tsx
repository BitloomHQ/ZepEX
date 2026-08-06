import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import loginImg from '@/assets/login_img.png'
import { resetPassword } from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AuthSplitLayout } from '@/components/layout/AuthSplitLayout'
import { Button } from '@/components/ui/button'
import { PasswordInput } from '@/components/ui/password-input'
import { Label } from '@/components/ui/label'
import logo from '@/assets/logo.png'

export function ResetPasswordPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const uid = searchParams.get('uid')?.trim() ?? ''
  const token = searchParams.get('token')?.trim() ?? ''
  const linkValid = useMemo(() => Boolean(uid && token), [uid, token])

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!linkValid) {
      setError('Invalid or missing reset link. Request a new one from Forgot password.')
      return
    }
    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    setError('')
    try {
      const { data } = await resetPassword({
        uid,
        token,
        new_password: newPassword,
        confirm_password: confirmPassword,
      })
      navigate('/login', { state: { message: data.message } })
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
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Reset password</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Choose a new password for your account.
        </p>
      </div>

      {!linkValid ? (
        <div className="space-y-5">
          <p className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700">
            This reset link is invalid or incomplete. Request a new link from Forgot password.
          </p>
          <Link
            to="/forgot-password"
            className="inline-flex h-11 w-full items-center justify-center rounded-md bg-primary text-base font-medium text-primary-foreground hover:bg-primary/90"
          >
            Forgot password
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="new_password">New password</Label>
            <PasswordInput
              id="new_password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="At least 8 characters"
              className="h-11"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirm_password">Confirm password</Label>
            <PasswordInput
              id="confirm_password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Re-enter new password"
              className="h-11"
            />
          </div>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700">{error}</p>
          )}

          <Button type="submit" className="h-11 w-full text-base" disabled={loading}>
            {loading ? 'Resetting...' : 'Reset password'}
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
