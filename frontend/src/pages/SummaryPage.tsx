import { useEffect, useState, useTransition } from 'react'
import { useParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import {
  ArrowLeft,
  RefreshCw,
  Copy,
  Check,
  BookOpen,
  AlertCircle,
  Sparkles,
  Presentation,
  FileText,
  FileEdit,
  Video,
} from 'lucide-react'
import { getDocuments, getSummary, generateSummary } from '../api/client'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import type { DocumentItem } from '../types'

export function SummaryPage() {
  const { documentId } = useParams<{ documentId: string }>()
  const docIdNum = documentId ? parseInt(documentId, 10) : NaN

  const [document, setDocument] = useState<DocumentItem | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [, startTransition] = useTransition()

  // Load document info and summary
  useEffect(() => {
    if (isNaN(docIdNum)) {
      setError('Invalid document ID')
      setIsLoading(false)
      return
    }

    let isMounted = true

    const loadData = async () => {
      setIsLoading(true)
      setError(null)

      try {
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
  }, [docIdNum])

  const handleRegenerate = async () => {
    if (isNaN(docIdNum)) return
    setIsRegenerating(true)
    setError(null)

    try {
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

  const getSourceBadge = () => {
    const type = document?.source_type || 'pdf'
    switch (type) {
      case 'pptx':
        return {
          icon: <Presentation size={14} className="text-[#FBBF24]" />,
          label: 'PPTX',
          style: 'text-[#FBBF24] bg-[rgba(251,191,36,0.2)] border border-[rgba(251,191,36,0.3)]',
        }
      case 'docx':
        return {
          icon: <FileEdit size={14} className="text-[#60A5FA]" />,
          label: 'DOCX',
          style: 'text-[#60A5FA] bg-[rgba(96,165,250,0.2)] border border-[rgba(96,165,250,0.3)]',
        }
      case 'youtube':
        return {
          icon: <Video size={14} className="text-[#F87171]" />,
          label: 'YOUTUBE',
          style: 'text-[#F87171] bg-[rgba(248,113,113,0.2)] border border-[rgba(248,113,113,0.3)]',
        }
      case 'pdf':
      default:
        return {
          icon: <FileText size={14} className="text-[#FB7185]" />,
          label: 'PDF',
          style: 'text-[#FB7185] bg-[rgba(251,113,133,0.2)] border border-[rgba(251,113,133,0.3)]',
        }
    }
  }

  const badge = getSourceBadge()

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
            <h1 className="text-xl font-bold text-white tracking-tight truncate max-w-lg" title={document?.filename}>
              {document ? document.filename : `Document #${docIdNum}`}
            </h1>
            {document && (
              <p className="text-xs text-[#A1A1AA] mt-1 font-mono">
                {document.total_chunks} chunks indexed
              </p>
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
              disabled={isRegenerating}
              className="flex items-center gap-1.5 px-4 py-2.5 text-xs font-semibold rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] hover:brightness-110 text-white transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] disabled:opacity-50"
              title="Regenerate summary with AI"
            >
              <RefreshCw size={14} className={isRegenerating ? 'animate-spin' : ''} />
              <span>{isRegenerating ? 'Regenerating...' : 'Regenerate'}</span>
            </button>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <div className="p-8 md:p-12 rounded-3xl bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] shadow-[0_8px_32px_rgba(0,0,0,0.5)] min-h-[400px]">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <LoadingSpinner size={44} className="mb-4 text-[#3B82F6]" />
            <h3 className="text-base font-semibold text-white mb-1.5">Synthesizing Exam Revision Summary</h3>
            <p className="text-xs text-[#A1A1AA] max-w-sm">
              Analyzing document chunks, extracting definitions, and generating structured notes...
            </p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-14 h-14 rounded-full bg-[rgba(248,113,113,0.15)] flex items-center justify-center text-[#F87171] mb-4 border border-[rgba(248,113,113,0.25)] shadow-[0_0_20px_rgba(248,113,113,0.15)]">
              <AlertCircle size={28} />
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Unable to Generate Summary</h3>
            <p className="text-xs text-[#A1A1AA] max-w-md mb-6">{error}</p>
            <button
              onClick={handleRegenerate}
              className="px-5 py-2.5 bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold rounded-xl transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110"
            >
              Try Again
            </button>
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
              <ReactMarkdown>{summary}</ReactMarkdown>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <BookOpen size={36} className="text-[#5C5C6E] mb-3" />
            <h3 className="text-base font-semibold text-white mb-1">No Summary Available</h3>
            <p className="text-xs text-[#A1A1AA] max-w-sm mb-6">
              No revision summary has been generated for this document yet.
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
