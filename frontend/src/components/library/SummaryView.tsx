import { useEffect, useState, useTransition } from 'react'
import ReactMarkdown from 'react-markdown'
import { X, RefreshCw, Copy, Check, BookOpen, AlertCircle, Sparkles } from 'lucide-react'
import { getSummary, generateSummary } from '../../api/client'
import { LoadingSpinner } from '../ui/LoadingSpinner'
import { EmptyState } from '../ui/EmptyState'
import type { DocumentItem } from '../../types'

interface SummaryViewProps {
  document: DocumentItem
  onClose: () => void
}

export function SummaryView({ document, onClose }: SummaryViewProps) {
  const [summary, setSummary] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [, startTransition] = useTransition()

  const loadSummary = async (forceRegenerate = false) => {
    if (forceRegenerate) {
      setIsRegenerating(true)
    } else {
      setIsLoading(true)
    }
    setError(null)

    try {
      if (forceRegenerate) {
        const res = await generateSummary(document.id, true)
        startTransition(() => {
          setSummary(res.summary)
        })
      } else {
        try {
          const res = await getSummary(document.id)
          startTransition(() => {
            setSummary(res.summary)
          })
        } catch (getErr: any) {
          // If summary doesn't exist yet, auto-generate it
          if (getErr.message?.includes('not found') || getErr.message?.includes('404')) {
            const genRes = await generateSummary(document.id, false)
            startTransition(() => {
              setSummary(genRes.summary)
            })
          } else {
            throw getErr
          }
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load summary')
    } finally {
      setIsLoading(false)
      setIsRegenerating(false)
    }
  }

  useEffect(() => {
    loadSummary(false)
  }, [document.id])

  const handleCopy = () => {
    if (!summary) return
    navigator.clipboard.writeText(summary)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in">
      <div 
        className="relative w-full max-w-3xl max-h-[85vh] flex flex-col bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-primary)] bg-[var(--bg-elevated)]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-[var(--accent-primary-muted)] text-[var(--accent-primary)] flex items-center justify-center">
              <BookOpen size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                Exam Summary
                <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--accent-primary-muted)] text-[var(--accent-primary)] font-mono font-normal">
                  AI Generated
                </span>
              </h2>
              <p className="text-xs text-[var(--text-secondary)] truncate max-w-md" title={document.filename}>
                {document.filename}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {summary && !isLoading && (
              <>
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--border-primary)] text-[var(--text-secondary)] hover:text-white hover:bg-[var(--bg-hover)] transition-colors"
                  title="Copy to clipboard"
                >
                  {copied ? (
                    <>
                      <Check size={14} className="text-[var(--success)]" />
                      <span className="text-[var(--success)]">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy size={14} />
                      <span>Copy</span>
                    </>
                  )}
                </button>

                <button
                  onClick={() => loadSummary(true)}
                  disabled={isRegenerating}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--border-primary)] text-[var(--text-secondary)] hover:text-white hover:bg-[var(--bg-hover)] transition-colors disabled:opacity-50"
                  title="Regenerate summary with AI"
                >
                  <RefreshCw size={14} className={isRegenerating ? 'animate-spin text-[var(--accent-primary)]' : ''} />
                  <span>{isRegenerating ? 'Regenerating...' : 'Regenerate'}</span>
                </button>
              </>
            )}

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:text-white hover:bg-[var(--bg-hover)] transition-colors"
              aria-label="Close modal"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 md:p-8">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <LoadingSpinner size={44} className="mb-4" />
              <h3 className="text-base font-semibold text-white mb-1">Synthesizing Exam Revision Summary</h3>
              <p className="text-xs text-[var(--text-secondary)] max-w-sm">
                Extracting definitions, key formulas, and high-yield concepts from the document...
              </p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center text-[var(--error)] mb-4">
                <AlertCircle size={28} />
              </div>
              <h3 className="text-base font-semibold text-white mb-2">Unable to Generate Summary</h3>
              <p className="text-xs text-[var(--text-secondary)] max-w-md mb-6">{error}</p>
              <button
                onClick={() => loadSummary(false)}
                className="px-4 py-2 bg-[var(--accent-primary)] hover:bg-[var(--accent-primary-hover)] text-white text-xs font-medium rounded-lg transition-colors shadow-sm"
              >
                Try Again
              </button>
            </div>
          ) : summary ? (
            <div className="space-y-4">
              {isRegenerating && (
                <div className="p-3 bg-[var(--accent-primary-muted)] border border-[var(--border-accent)] rounded-xl flex items-center gap-2 text-xs text-[var(--accent-primary)] mb-4 animate-pulse">
                  <Sparkles size={16} />
                  <span>Regenerating revision summary in background...</span>
                </div>
              )}
              <div className="prose prose-invert prose-headings:text-white prose-headings:font-bold prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-p:text-[var(--text-primary)] prose-p:leading-relaxed prose-li:text-[var(--text-secondary)] prose-strong:text-white max-w-none text-sm space-y-4">
                <ReactMarkdown>{summary}</ReactMarkdown>
              </div>
            </div>
          ) : (
            <EmptyState
              icon={<BookOpen size={32} />}
              title="No Summary Available"
              description="No summary could be found or generated for this document."
              action={
                <button
                  onClick={() => loadSummary(true)}
                  className="mt-4 px-4 py-2 bg-[var(--accent-primary)] text-white text-xs font-medium rounded-lg"
                >
                  Generate Summary
                </button>
              }
            />
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-[var(--border-primary)] bg-[var(--bg-elevated)] flex justify-between items-center text-xs text-[var(--text-tertiary)]">
          <span>High-yield exam revision notes</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-[var(--bg-hover)] text-white hover:bg-[var(--bg-active)] transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
