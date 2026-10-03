import { useEffect, useState } from 'react'
import { Server, CheckCircle2, AlertCircle, Loader2, UserRound, LogOut } from 'lucide-react'
import { healthCheck } from '../api/client'
import { useAuth } from '../context/AuthContext'
import type { HealthStatus } from '../types'

export function SettingsPage() {
  const { user, logout } = useAuth()
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthError, setHealthError] = useState<string | null>(null)

  const checkHealth = async () => {
    setHealthLoading(true)
    setHealthError(null)
    try {
      const data = await healthCheck()
      setHealth(data)
    } catch (err: any) {
      setHealthError(err?.message || 'Failed to connect to backend server')
      setHealth(null)
    } finally {
      setHealthLoading(false)
    }
  }

  // System diagnostics are for local development only; production shows just the account.
  const showDevInfo = import.meta.env.DEV

  useEffect(() => {
    if (showDevInfo) checkHealth()
  }, [showDevInfo])

  return (
    <div className="w-full max-w-4xl mx-auto animate-fade-in pb-16">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white tracking-tight">{showDevInfo ? 'System & Settings' : 'Settings'}</h1>
        <p className="text-[var(--text-secondary)] text-sm mt-1">
          {showDevInfo ? 'Your account, plus backend health and API details (local development only).' : 'Your account.'}
        </p>
      </div>

      <div className="flex flex-col gap-6 max-w-3xl">

        {/* Account Card (also the way to log out on phones, where the sidebar is hidden) */}
        {user && (
          <div className="bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-2xl p-6 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)] flex items-center justify-center text-[var(--accent-primary)] flex-shrink-0">
                <UserRound size={20} />
              </div>
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-white">Account</h2>
                <p className="text-xs text-[var(--text-secondary)] truncate">Signed in as {user.email}</p>
              </div>
            </div>
            <button
              onClick={() => logout()}
              className="self-start sm:self-auto flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold text-[#F87171] border border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)] hover:bg-[rgba(239,68,68,0.15)] transition-all duration-200"
            >
              <LogOut size={14} />
              <span>Log out</span>
            </button>
          </div>
        )}

        {showDevInfo && (<>
        {/* About Card */}
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-5">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8] flex items-center justify-center text-white font-bold text-sm shadow-[0_0_12px_rgba(59,130,246,0.35)]">
              SB
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">SecondBrain AI</h2>
              <p className="text-xs text-[var(--text-tertiary)] font-mono">Deep Blue Palette & Glass Layout</p>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div className="p-3.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)]">
              <span className="text-[var(--text-tertiary)] text-[11px] font-mono uppercase tracking-wider block mb-1">Version</span>
              <span className="text-white font-semibold">2.0.0</span>
            </div>
            <div className="p-3.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)]">
              <span className="text-[var(--text-tertiary)] text-[11px] font-mono uppercase tracking-wider block mb-1">Database</span>
              <span className="text-white font-semibold">PostgreSQL</span>
            </div>
            <div className="p-3.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)]">
              <span className="text-[var(--text-tertiary)] text-[11px] font-mono uppercase tracking-wider block mb-1">Vector Index</span>
              <span className="text-white font-semibold">pgvector</span>
            </div>
            <div className="p-3.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)]">
              <span className="text-[var(--text-tertiary)] text-[11px] font-mono uppercase tracking-wider block mb-1">File Limit</span>
              <span className="text-white font-semibold">20 MB</span>
            </div>
          </div>
        </div>

        {/* Backend Health Card */}
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-5">
            <div className="w-10 h-10 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)] flex items-center justify-center text-[var(--accent-primary)]">
              <Server size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">API Health Status</h2>
              <p className="text-xs text-[var(--text-tertiary)]">FastAPI backend connection check</p>
            </div>
          </div>

          {healthLoading ? (
            <div className="flex items-center gap-2.5 text-[var(--text-secondary)] text-sm py-4">
              <Loader2 size={16} className="animate-spin text-[var(--accent-primary)]" />
              <span>Checking backend connection...</span>
            </div>
          ) : healthError ? (
            <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-xs flex items-center gap-2">
              <AlertCircle size={16} />
              <span>Unreachable — {healthError}</span>
            </div>
          ) : health ? (
            <div className="flex flex-col gap-4 text-sm">
              <div className="flex items-center gap-2 text-[var(--success)] font-medium">
                <CheckCircle2 size={16} />
                <span>Backend Connected and Operational</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)]">
                  <span className="text-[var(--text-tertiary)] text-[11px] font-mono uppercase tracking-wider block mb-0.5">Service</span>
                  <span className="text-white font-medium">{health.service}</span>
                </div>
                <div className="p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)]">
                  <span className="text-[var(--text-tertiary)] text-[11px] font-mono uppercase tracking-wider block mb-0.5">API Version</span>
                  <span className="text-white font-medium">{health.version}</span>
                </div>
                <div className="p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)]">
                  <span className="text-[var(--text-tertiary)] text-[11px] font-mono uppercase tracking-wider block mb-0.5">Health State</span>
                  <span className="text-[var(--success)] font-medium capitalize">{health.status}</span>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Developer info: API endpoints */}
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-2xl p-6 shadow-sm">
          <h2 className="text-base font-semibold text-white mb-1">Developer info</h2>
          <p className="text-xs text-[var(--text-secondary)] mb-4">Backend API endpoints for ingestion, search, study, review and accounts</p>
          <div className="flex flex-col divide-y divide-[var(--border-primary)] font-mono text-xs">
            {[
              ['POST', '/api/v1/upload/pdf', 'PDF document ingestion with sentence chunking'],
              ['POST', '/api/v1/upload/pptx', 'PowerPoint slide extraction with speaker notes'],
              ['POST', '/api/v1/upload/docx', 'Word document parsing with heading hierarchy'],
              ['POST', '/api/v1/upload/images', 'Photos and screenshots read by AI text recognition, one page per image'],
              ['POST', '/api/v1/upload/youtube', 'YouTube transcript fetch with timestamp links'],
              ['POST', '/api/v1/upload/website', 'Web page article extraction with SSRF-safe fetching'],
              ['GET', '/api/v1/search?query=…', 'pgvector semantic search + AI answer'],
              ['POST', '/api/v1/documents/:id/summary', 'Map-reduce exam revision summary generation'],
              ['POST', '/api/v1/documents/:id/flashcards', 'Strict JSON flashcard deck generation'],
              ['POST', '/api/v1/documents/:id/quiz', 'Cited multiple-choice quiz generation, with saved scores'],
              ['POST', '/api/v1/documents/:id/quiz/:quizId/attempts', 'Submit quiz answers, scored on the server'],
              ['POST', '/api/v1/merged-sets', 'Combine 2–8 documents into one merged study set'],
              ['GET', '/api/v1/merged-sets', 'List merged sets'],
              ['POST', '/api/v1/merged-sets/:id/summary', 'Cross-source summary citing each document'],
              ['POST', '/api/v1/merged-sets/:id/flashcards', 'Flashcards shared across the set’s sources'],
              ['POST', '/api/v1/merged-sets/:id/quiz', 'Multiple-choice quiz over the whole set'],
              ['POST', '/api/v1/merged-sets/:id/quiz/:quizId/attempts', 'Submit answers for a merged set quiz'],
              ['GET', '/api/v1/review/due?today=…', 'Flashcards due today (SM-2 spaced repetition)'],
              ['GET', '/api/v1/review/due/count?today=…', 'Due and new card counts, without the cards'],
              ['POST', '/api/v1/review/cards/:kind/:cardId', 'Rate a card again / good / easy (kind: document or merged)'],
              ['POST', '/api/v1/auth/signup', 'Create an account and start a session'],
              ['POST', '/api/v1/auth/login', 'Email and password login (HttpOnly session cookie)'],
              ['POST', '/api/v1/auth/logout', 'End the current session'],
              ['GET', '/api/v1/auth/me', 'The signed-in user'],
              ['POST', '/api/v1/auth/password-reset/request', 'Email a password reset link'],
              ['POST', '/api/v1/auth/password-reset/confirm', 'Set a new password with a reset token'],
            ].map(([method, path, desc]) => (
              <div key={`${method} ${path}`} className="flex flex-col sm:flex-row sm:items-center gap-2 py-3">
                <span className={`w-14 text-center px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                  method === 'POST'
                    ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    : 'bg-[var(--accent-primary-muted)] text-[var(--accent-primary)] border border-[var(--border-accent)]'
                }`}>
                  {method}
                </span>
                <span className="text-white text-xs font-semibold sm:w-80 sm:flex-shrink-0 break-all">{path}</span>
                <span className="text-[var(--text-tertiary)] font-sans text-xs">{desc}</span>
              </div>
            ))}
          </div>
        </div>
        </>)}

      </div>
    </div>
  )
}
