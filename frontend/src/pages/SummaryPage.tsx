import { useEffect, useState, useTransition } from 'react'
import type { ReactNode } from 'react'
import { useParams, useLocation, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import {
  ArrowLeft,
  RefreshCw,
  Copy,
  Check,
  BookOpen,
  AlertCircle,
  Sparkles,
  ExternalLink,
  Layers,
} from 'lucide-react'
import {
  getDocuments,
  getSummary,
  generateSummary,
  getMergedSet,
  getMergedSummary,
  generateMergedSummary,
} from '../api/client'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { sourceBadge, MERGED_BADGE_STYLE } from '../components/library/sourceBadge'
import { MergedSetMembers, MergedSetNotices } from '../components/library/MergedSetHeader'
import type { DocumentItem, MergedSet } from '../types'

// Citation links ("02:05", "3: 02:05", "4") stay compact on one line; other
// links (titles in a merged summary's Sources list, a website footer) wrap.
const CITATION_TEXT = /^(\d+(: .+)?|\d{1,2}:\d{2}(:\d{2})?)$/

function linkText(children: ReactNode): string {
  if (typeof children === 'string') return children
  if (Array.isArray(children)) return children.map((c) => (typeof c === 'string' ? c : '')).join('')
  return ''
}

// With `merged`, the page shows a merged set (route /library/merged/:setId/summary).
export function SummaryPage({ merged = false }: { merged?: boolean }) {
  const params = useParams<{ documentId?: string; setId?: string }>()
  const rawId = merged ? params.setId : params.documentId
  const docIdNum = rawId ? parseInt(rawId, 10) : NaN
  const location = useLocation()
  const reopened = merged && Boolean((location.state as { reopened?: boolean } | null)?.reopened)

  const [document, setDocument] = useState<DocumentItem | null>(null)
  const [mergedSet, setMergedSet] = useState<MergedSet | null>(null)
  const [stale, setStale] = useState(false)
  const [summary, setSummary] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [, startTransition] = useTransition()

  // Load document (or merged set) info and summary
  useEffect(() => {
    if (isNaN(docIdNum)) {
      setError(merged ? 'Invalid merged set ID' : 'Invalid document ID')
      setIsLoading(false)
      return
    }

    let isMounted = true

    const loadData = async () => {
      setIsLoading(true)
      setError(null)

      try {
        if (merged) {
          const set = await getMergedSet(docIdNum)
          if (isMounted) setMergedSet(set)
          try {
            const res = await getMergedSummary(docIdNum)
            if (isMounted) {
              startTransition(() => {
                setSummary(res.summary)
                setStale(res.stale)
              })
            }
          } catch (getErr: any) {
            if (!getErr.message?.includes('not found')) throw getErr
            const genRes = await generateMergedSummary(docIdNum, false)
            if (isMounted) {
              startTransition(() => {
                setSummary(genRes.summary)
                setStale(genRes.stale)
              })
            }
          }
          return
        }

        // Fetch document metadata
        const docs = await getDocuments()
        const found = docs.find((d) => d.id === docIdNum)
        if (isMounted && found) {
          setDocument(found)
        }

        // Fetch or auto-generate summary
        try {
          const res = await getSummary(docIdNum)
          if (isMounted) {
            startTransition(() => {
              setSummary(res.summary)
            })
          }
        } catch (getErr: any) {
          if (getErr.message?.includes('not found') || getErr.message?.includes('404')) {
            const genRes = await generateSummary(docIdNum, false)
            if (isMounted) {
              startTransition(() => {
                setSummary(genRes.summary)
              })
            }
          } else {
            throw getErr
          }
        }
      } catch (err: any) {
        if (isMounted) {
          setError(err.message || 'Failed to load summary')
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    loadData()

    return () => {
      isMounted = false
    }
  }, [docIdNum, merged])

  const cannotRegenerate = merged && mergedSet !== null && mergedSet.documents.length < 2

  const handleRegenerate = async () => {
    if (isNaN(docIdNum) || cannotRegenerate) return
    setIsRegenerating(true)
    setError(null)

    try {
      if (merged) {
        const res = await generateMergedSummary(docIdNum, true)
        startTransition(() => {
          setSummary(res.summary)
          setStale(res.stale)
        })
        return
      }
      const res = await generateSummary(docIdNum, true)
      startTransition(() => {
        setSummary(res.summary)
      })
    } catch (err: any) {
      setError(err.message || 'Failed to regenerate summary')
    } finally {
      setIsRegenerating(false)
    }
  }

  const handleCopy = () => {
    if (!summary) return
    navigator.clipboard.writeText(summary)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const badge = merged
    ? {
        icon: <Layers size={14} className="text-[#C4B5FD]" />,
        label: `MERGED · ${mergedSet?.documents.length ?? '…'} ${mergedSet?.documents.length === 1 ? 'SOURCE' : 'SOURCES'}`,
        style: MERGED_BADGE_STYLE,
      }
    : sourceBadge(document?.source_type || 'pdf')
  const title = merged
    ? mergedSet?.name ?? `Merged set #${docIdNum}`
    : document ? document.filename : `Document #${docIdNum}`

  return (
    <div className="flex flex-col w-full max-w-4xl mx-auto animate-fade-in pb-16 min-w-0">
      {/* Navigation Breadcrumb */}
      <div className="mb-6">
        <Link
          to="/library"
          className="inline-flex items-center gap-2 text-xs font-medium text-[#A1A1AA] hover:text-white transition-all duration-200 px-3.5 py-2 rounded-xl bg-[rgba(255,255,255,0.03)] backdrop-blur-md border border-[rgba(255,255,255,0.08)] hover:border-[rgba(59,130,246,0.3)] hover:bg-[rgba(255,255,255,0.06)]"
        >
          <ArrowLeft size={14} />
          <span>Back to Library</span>
        </Link>
      </div>

      {/* Header Panel */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-7 md:p-8 rounded-3xl bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] shadow-[0_8px_32px_rgba(0,0,0,0.5)] mb-8">
        <div className="flex items-start sm:items-center gap-4 min-w-0">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#3B82F6]/20 to-[#1D4ED8]/20 border border-[rgba(59,130,246,0.35)] text-[#93C5FD] flex items-center justify-center flex-shrink-0 shadow-[0_0_15px_rgba(59,130,246,0.2)]">
            <BookOpen size={22} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-[rgba(59,130,246,0.12)] text-[#93C5FD] font-mono font-medium border border-[rgba(59,130,246,0.25)]">
                AI Revision Summary
              </span>
              <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-md flex items-center gap-1.5 ${badge.style}`}>
                {badge.icon}
                <span>{badge.label}</span>
              </span>
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight truncate max-w-lg" title={title}>
              {title}
            </h1>
            {mergedSet && <MergedSetMembers set={mergedSet} page="summary" />}
            {document && (
              <p className="text-xs text-[#A1A1AA] mt-1 font-mono">
                {document.total_chunks} chunks indexed
              </p>
            )}
            {document?.source_type === 'website' && document.source_url && (
              <a
                href={document.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 mt-2 text-xs font-medium text-[#22D3EE] hover:text-[#67E8F9] hover:underline transition-colors"
                title={document.source_url}
              >
                <span>Open original page</span>
                <ExternalLink size={12} />
              </a>
            )}
          </div>
        </div>

        {/* Action Controls */}
        {summary && !isLoading && (
          <div className="flex items-center gap-2.5 sm:self-center self-start">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] text-[#A1A1AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.15)] transition-all duration-200"
              title="Copy markdown to clipboard"
            >
              {copied ? (
                <>
                  <Check size={14} className="text-[#34D399]" />
                  <span className="text-[#34D399]">Copied</span>
                </>
              ) : (
                <>
                  <Copy size={14} />
                  <span>Copy</span>
                </>
              )}
            </button>

            <button
              onClick={handleRegenerate}
              disabled={isRegenerating || cannotRegenerate}
              className="flex items-center gap-1.5 px-4 py-2.5 text-xs font-semibold rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] hover:brightness-110 text-white transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] disabled:opacity-50 disabled:cursor-not-allowed"
              title={cannotRegenerate ? 'A merged set needs at least 2 documents' : 'Regenerate summary with AI'}
            >
              <RefreshCw size={14} className={isRegenerating ? 'animate-spin' : ''} />
              <span>{isRegenerating ? 'Regenerating...' : 'Regenerate'}</span>
            </button>
          </div>
        )}
      </div>

      {mergedSet && !isLoading && (
        <MergedSetNotices set={mergedSet} what="summary" stale={stale} reopened={reopened} />
      )}

      {/* Main Content Area */}
      <div className="p-5 sm:p-8 md:p-12 rounded-3xl bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] shadow-[0_8px_32px_rgba(0,0,0,0.5)] min-h-[400px]">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <LoadingSpinner size={44} className="mb-4 text-[#3B82F6]" />
            <h3 className="text-base font-semibold text-white mb-1.5">
              {merged ? 'Combining Your Sources' : 'Synthesizing Exam Revision Summary'}
            </h3>
            <p className="text-xs text-[#A1A1AA] max-w-sm">
              {merged
                ? 'Reading every document in the set and writing one summary that cites where each point came from. Large sets can take a minute...'
                : 'Analyzing document chunks, extracting definitions, and generating structured notes...'}
            </p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-14 h-14 rounded-full bg-[rgba(248,113,113,0.15)] flex items-center justify-center text-[#F87171] mb-4 border border-[rgba(248,113,113,0.25)] shadow-[0_0_20px_rgba(248,113,113,0.15)]">
              <AlertCircle size={28} />
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Unable to Generate Summary</h3>
            <p className="text-xs text-[#A1A1AA] max-w-md mb-6">{error}</p>
            {!cannotRegenerate && (
              <button
                onClick={handleRegenerate}
                className="px-5 py-2.5 bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold rounded-xl transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110"
              >
                Try Again
              </button>
            )}
          </div>
        ) : summary ? (
          <div className="space-y-6">
            {isRegenerating && (
              <div className="p-4 bg-[rgba(59,130,246,0.12)] border border-[rgba(59,130,246,0.25)] rounded-2xl flex items-center gap-2.5 text-xs text-[#93C5FD] animate-pulse">
                <Sparkles size={16} />
                <span>Regenerating revision summary in background...</span>
              </div>
            )}
            <div className="prose prose-invert prose-headings:text-white prose-headings:font-bold prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg prose-p:text-[#D1D5DB] prose-p:leading-relaxed prose-li:text-[#A1A1AA] prose-strong:text-white max-w-none text-sm space-y-4">
              <ReactMarkdown
                components={{
                  // YouTube summaries cite [mm:ss] links into the video; open them
                  // in a new tab so the summary stays where the user left it.
                  a: ({ node: _node, ...props }) => (
                    <a
                      {...props}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={
                        CITATION_TEXT.test(linkText(props.children).trim())
                          ? 'font-mono text-xs text-[#93C5FD] hover:text-[#BFDBFE] underline underline-offset-2 whitespace-nowrap'
                          : 'text-[#93C5FD] hover:text-[#BFDBFE] underline underline-offset-2 break-words'
                      }
                    />
                  ),
                }}
              >
                {summary}
              </ReactMarkdown>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <BookOpen size={36} className="text-[#5C5C6E] mb-3" />
            <h3 className="text-base font-semibold text-white mb-1">No Summary Available</h3>
            <p className="text-xs text-[#A1A1AA] max-w-sm mb-6">
              No revision summary has been generated for this {merged ? 'merged set' : 'document'} yet.
            </p>
            <button
              onClick={handleRegenerate}
              className="px-5 py-2.5 bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold rounded-xl transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110"
            >
              Generate Summary
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
