import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MailCheck } from 'lucide-react'
import { requestPasswordReset } from '../api/client'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { AuthShell, authButtonClass, authInputClass, authLinkClass } from '../components/auth/AuthShell'

// /forgot-password: asks for a reset link. The answer is the same whether or
// not the email has an account (the backend decides whether to send anything).
export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sentMessage, setSentMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      setSentMessage(await requestPasswordReset(email))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle="Enter your account's email and we'll send you a link to set a new password."
      footer={<Link to="/login" className={authLinkClass}>Back to log in</Link>}
    >
      {sentMessage ? (
        <div role="status" className="flex flex-col items-center text-center gap-3 py-2">
          <MailCheck size={32} className="text-[#6EE7B7]" />
          <p className="text-sm text-[#D1D5DB]">{sentMessage}</p>
          <p className="text-xs text-[#71717A]">Check your spam folder if it doesn't arrive in a few minutes.</p>
          <button
            type="button"
            onClick={() => { setSentMessage(null); setEmail('') }}
            className="mt-1 text-xs font-medium text-[#93C5FD] hover:text-[#BFDBFE] hover:underline"
          >
            Use a different email
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <div>
            <label htmlFor="reset-email" className="block text-xs font-medium text-[#D1D5DB] mb-1.5">Email</label>
            <input
              id="reset-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => { setEmail(e.target.value); setError(null) }}
              className={authInputClass}
              placeholder="you@example.com"
            />
          </div>
          {error && <p role="alert" className="text-xs text-[#F87171]">{error}</p>}
          <button type="submit" disabled={busy || !email.trim()} className={authButtonClass}>
            {busy && <LoadingSpinner size={16} className="!text-white" />}
            <span>Send reset link</span>
          </button>
        </form>
      )}
    </AuthShell>
  )
}
