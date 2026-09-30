import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useDocuments } from '../context/DocumentContext'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { AuthShell, PasswordField, authButtonClass, authInputClass, authLinkClass } from '../components/auth/AuthShell'

export const MIN_PASSWORD_LENGTH = 8 // same as the backend (auth_service.py)

// /login and /signup. After signing in, goes back to the page that sent the user here.
export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const { user, login, signup } = useAuth()
  const { refreshDocuments } = useDocuments()
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as { from?: string; notice?: string } | null
  const from = state?.from || '/'
  const isSignup = mode === 'signup'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={from} replace />

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    if (isSignup && password.length < MIN_PASSWORD_LENGTH) {
      setError(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await (isSignup ? signup : login)(email, password)
      // The sidebar and Home read the shared list; load this account's documents.
      refreshDocuments().catch(() => {})
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.')
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title={isSignup ? 'Create your account' : 'Welcome back'}
      subtitle={isSignup ? 'Your study library, summaries and flashcards stay private to you.' : 'Log in to your SecondBrain.'}
      footer={
        <>
          {isSignup ? 'Already have an account? ' : 'New to SecondBrain? '}
          <Link to={isSignup ? '/login' : '/signup'} state={{ from: state?.from }} className={authLinkClass}>
            {isSignup ? 'Log in' : 'Create an account'}
          </Link>
        </>
      }
    >
      {state?.notice && !isSignup && (
        <p role="status" className="mb-4 p-3 rounded-xl flex items-start gap-2 text-xs text-[#6EE7B7] bg-[rgba(52,211,153,0.1)] border border-[rgba(52,211,153,0.3)]">
          <CheckCircle2 size={15} className="flex-shrink-0 mt-px" />
          <span>{state.notice}</span>
        </p>
      )}
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div>
          <label htmlFor="auth-email" className="block text-xs font-medium text-[#D1D5DB] mb-1.5">Email</label>
          <input
            id="auth-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => { setEmail(e.target.value); setError(null) }}
            className={authInputClass}
            placeholder="you@example.com"
          />
        </div>
        <PasswordField
          id="auth-password"
          label="Password"
          value={password}
          onChange={(v) => { setPassword(v); setError(null) }}
          autoComplete={isSignup ? 'new-password' : 'current-password'}
          hint={isSignup ? `At least ${MIN_PASSWORD_LENGTH} characters.` : undefined}
          labelAside={
            !isSignup && (
              <Link to="/forgot-password" className="text-[11px] font-medium text-[#93C5FD] hover:text-[#BFDBFE] hover:underline">
                Forgot password?
              </Link>
            )
          }
        />

        {error && <p role="alert" className="text-xs text-[#F87171]">{error}</p>}

        <button type="submit" disabled={busy || !email.trim() || !password} className={authButtonClass}>
          {busy && <LoadingSpinner size={16} className="!text-white" />}
          <span>{isSignup ? 'Create account' : 'Log in'}</span>
        </button>
      </form>
    </AuthShell>
  )
}
