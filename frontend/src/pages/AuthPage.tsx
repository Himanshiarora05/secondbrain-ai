import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useDocuments } from '../context/DocumentContext'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'

const MIN_PASSWORD_LENGTH = 8 // same as the backend (auth_service.py)

// /login and /signup. After signing in, goes back to the page that sent the user here.
export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const { user, login, signup } = useAuth()
  const { refreshDocuments } = useDocuments()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from || '/'
  const isSignup = mode === 'signup'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
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

  const inputClass =
    'w-full bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.1)] rounded-xl px-4 py-3 text-sm text-white placeholder-[#5C5C6E] focus:outline-none focus:border-[rgba(59,130,246,0.5)] focus:shadow-[0_0_20px_rgba(59,130,246,0.12)] transition-all duration-200'

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#05070C] px-4 py-10">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8] flex items-center justify-center text-white font-black text-xl tracking-tight shadow-[0_0_30px_rgba(59,130,246,0.35)]">
            SB
          </div>
          <h1 className="mt-5 text-2xl font-bold text-white tracking-tight">
            {isSignup ? 'Create your account' : 'Welcome back'}
          </h1>
          <p className="mt-1.5 text-sm text-[#A1A1AA]">
            {isSignup ? 'Your study library, summaries and flashcards stay private to you.' : 'Log in to your SecondBrain.'}
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          noValidate
          className="p-6 sm:p-7 rounded-3xl bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] shadow-[0_8px_32px_rgba(0,0,0,0.5)] space-y-4"
        >
          <div>
            <label htmlFor="auth-email" className="block text-xs font-medium text-[#D1D5DB] mb-1.5">Email</label>
            <input
              id="auth-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => { setEmail(e.target.value); setError(null) }}
              className={inputClass}
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label htmlFor="auth-password" className="block text-xs font-medium text-[#D1D5DB] mb-1.5">Password</label>
            <div className="relative">
              <input
                id="auth-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete={isSignup ? 'new-password' : 'current-password'}
                required
                value={password}
                onChange={(e) => { setPassword(e.target.value); setError(null) }}
                className={`${inputClass} pr-11`}
                aria-describedby={isSignup ? 'auth-password-hint' : undefined}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute inset-y-0 right-0 px-3.5 flex items-center text-[#71717A] hover:text-white transition-colors"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {isSignup && (
              <p id="auth-password-hint" className="mt-1.5 text-[11px] text-[#71717A]">At least {MIN_PASSWORD_LENGTH} characters.</p>
            )}
          </div>

          {error && <p role="alert" className="text-xs text-[#F87171]">{error}</p>}

          <button
            type="submit"
            disabled={busy || !email.trim() || !password}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
          >
            {busy && <LoadingSpinner size={16} className="!text-white" />}
            <span>{isSignup ? 'Create account' : 'Log in'}</span>
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-[#A1A1AA]">
          {isSignup ? 'Already have an account? ' : 'New to SecondBrain? '}
          <Link
            to={isSignup ? '/login' : '/signup'}
            state={location.state}
            className="font-semibold text-[#93C5FD] hover:text-[#BFDBFE] underline underline-offset-2"
          >
            {isSignup ? 'Log in' : 'Create an account'}
          </Link>
        </p>
      </div>
    </div>
  )
}
