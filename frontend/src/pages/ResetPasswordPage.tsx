import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { checkResetToken, confirmPasswordReset } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { AuthShell, PasswordField, authButtonClass, authLinkClass } from '../components/auth/AuthShell'
import { MIN_PASSWORD_LENGTH } from './AuthPage'

// Read once, before the effect below removes it from the address bar.
function tokenFromUrl(): string {
  return new URLSearchParams(window.location.search).get('token') || ''
}

// /reset-password?token=...: the link from the reset email.
export function ResetPasswordPage() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [token] = useState(tokenFromUrl)
  const [status, setStatus] = useState<'checking' | 'invalid' | 'ready'>(token ? 'checking' : 'invalid')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    // Keep the token out of the address bar and browser history.
    window.history.replaceState(window.history.state, '', window.location.pathname)
    if (!token) return
    let active = true
    checkResetToken(token)
      .then((valid) => active && setStatus(valid ? 'ready' : 'invalid'))
      .catch(() => active && setStatus('ready')) // let the submit report any problem
    return () => {
      active = false
    }
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`)
      return
    }
    if (password !== confirm) {
      setError("The two passwords don't match.")
      return
    }
    setBusy(true)
    setError(null)
    try {
      const message = await confirmPasswordReset(token, password)
      // The reset ended every session, including this browser's if it had one.
      if (user) await logout().catch(() => {})
      navigate('/login', { replace: true, state: { notice: message } })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.')
      setBusy(false)
    }
  }

  const footer = <Link to="/login" className={authLinkClass}>Back to log in</Link>

  if (status === 'checking') {
    return (
      <AuthShell title="Set a new password" subtitle="Checking your reset link..." footer={footer}>
        <div className="flex justify-center py-6"><LoadingSpinner size={28} className="text-[#3B82F6]" /></div>
      </AuthShell>
    )
  }

  if (status === 'invalid') {
    return (
      <AuthShell title="This link doesn't work" subtitle="Reset links work once and expire after a while." footer={footer}>
        <div role="alert" className="flex flex-col items-center text-center gap-3 py-2">
          <AlertTriangle size={30} className="text-[#FBBF24]" />
          <p className="text-sm text-[#D1D5DB]">This reset link is invalid, has expired or was already used.</p>
          <Link to="/forgot-password" className={authButtonClass}>Send a new link</Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Set a new password" subtitle="Choose a new password for your SecondBrain account." footer={footer}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <PasswordField
          id="new-password"
          label="New password"
          value={password}
          onChange={(v) => { setPassword(v); setError(null) }}
          autoComplete="new-password"
          hint={`At least ${MIN_PASSWORD_LENGTH} characters. You'll be logged out everywhere.`}
        />
        <PasswordField
          id="confirm-password"
          label="Confirm new password"
          value={confirm}
          onChange={(v) => { setConfirm(v); setError(null) }}
          autoComplete="new-password"
        />
        {error && (
          <p role="alert" className="text-xs text-[#F87171]">
            {error}
            {error.startsWith('This reset link') && (
              <> <Link to="/forgot-password" className={authLinkClass}>Send a new link</Link></>
            )}
          </p>
        )}
        <button type="submit" disabled={busy || !password || !confirm} className={authButtonClass}>
          {busy && <LoadingSpinner size={16} className="!text-white" />}
          <span>Change password</span>
        </button>
      </form>
    </AuthShell>
  )
}
