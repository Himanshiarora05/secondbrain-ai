import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Layers,
  Presentation,
  FileText,
  FileEdit,
  Video,
  Globe,
  Image as ImageIcon,
  ArrowRight,
  BookOpen,
} from 'lucide-react'
import { getDocuments, listMergedSets } from '../api/client'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { EmptyState } from '../components/ui/EmptyState'
import { sourceBadge } from '../components/library/sourceBadge'
import type { DocumentItem, MergedSet } from '../types'

export function FlashcardsHubPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [mergedSets, setMergedSets] = useState<MergedSet[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true
    // Merged decks are extra: if they fail to load, the document decks still show.
    listMergedSets()
      .then((sets) => {
        if (isMounted) setMergedSets(sets)
      })
      .catch(() => {})
    getDocuments()
      .then((docs) => {
        if (isMounted) {
          setDocuments(docs)
          setIsLoading(false)
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || 'Failed to load documents')
          setIsLoading(false)
        }
      })
    return () => {
      isMounted = false
    }
  }, [])

  const getSourceBadge = (type?: string) => {
    switch (type) {
      case 'pptx':
        return {
          icon: <Presentation size={18} className="text-[#FBBF24]" />,
          bgColor: 'bg-[rgba(251,191,36,0.15)]',
          badgeText: 'PPTX',
          badgeStyle: 'text-[#FBBF24] bg-[rgba(251,191,36,0.2)] border-[rgba(251,191,36,0.3)]',
        }
      case 'docx':
        return {
          icon: <FileEdit size={18} className="text-[#60A5FA]" />,
          bgColor: 'bg-[rgba(96,165,250,0.15)]',
          badgeText: 'DOCX',
          badgeStyle: 'text-[#60A5FA] bg-[rgba(96,165,250,0.2)] border-[rgba(96,165,250,0.3)]',
        }
      case 'youtube':
        return {
          icon: <Video size={18} className="text-[#F87171]" />,
          bgColor: 'bg-[rgba(248,113,113,0.15)]',
          badgeText: 'YOUTUBE',
          badgeStyle: 'text-[#F87171] bg-[rgba(248,113,113,0.2)] border-[rgba(248,113,113,0.3)]',
        }
      case 'website':
        return {
          icon: <Globe size={18} className="text-[#22D3EE]" />,
          bgColor: 'bg-[rgba(34,211,238,0.15)]',
          badgeText: 'WEB',
          badgeStyle: 'text-[#22D3EE] bg-[rgba(34,211,238,0.2)] border-[rgba(34,211,238,0.3)]',
        }
      case 'image':
        return {
          icon: <ImageIcon size={18} className="text-[#34D399]" />,
          bgColor: 'bg-[rgba(52,211,153,0.15)]',
          badgeText: 'IMAGE',
          badgeStyle: 'text-[#34D399] bg-[rgba(52,211,153,0.2)] border-[rgba(52,211,153,0.3)]',
        }
      case 'pdf':
      default:
        return {
          icon: <FileText size={18} className="text-[#FB7185]" />,
          bgColor: 'bg-[rgba(251,113,133,0.15)]',
          badgeText: 'PDF',
          badgeStyle: 'text-[#FB7185] bg-[rgba(251,113,133,0.2)] border-[rgba(251,113,133,0.3)]',
        }
    }
  }

  return (
    <div className="relative flex flex-col w-full max-w-5xl mx-auto animate-fade-in pb-16 min-w-0">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#3B82F6]/20 to-[#1D4ED8]/20 border border-[rgba(59,130,246,0.35)] flex items-center justify-center text-[#93C5FD] shadow-[0_0_15px_rgba(59,130,246,0.2)]">
            <Layers size={20} />
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Flashcard Decks</h1>
        </div>
        <p className="text-[#A1A1AA] text-sm max-w-xl">
          Select any document from your library to start an interactive revision session with AI-generated flashcards.
        </p>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20">
          <LoadingSpinner size={40} className="mb-4 text-[#3B82F6]" />
          <p className="text-sm text-[#A1A1AA]">Loading available study decks...</p>
        </div>
      ) : error ? (
        <div className="p-6 bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.3)] text-[#F87171] rounded-2xl text-center max-w-md mx-auto">
          <p className="text-sm">{error}</p>
        </div>
      ) : documents.length === 0 ? (
        <EmptyState
          icon={<Layers size={36} />}
          title="No Study Material Yet"
          description="Upload lecture slides, notes, or YouTube videos to automatically generate flashcards."
          action={
            <Link
              to="/"
              className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold hover:brightness-110 transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)]"
            >
              Upload Material
            </Link>
          }
        />
      ) : (
        <>
        {mergedSets.length > 0 && (
          <section className="mb-10" aria-labelledby="merged-decks-heading">
            <h2 id="merged-decks-heading" className="flex items-center gap-2 text-sm font-semibold text-white mb-4">
              <Layers size={16} className="text-[#C4B5FD]" />
              Merged decks
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {mergedSets.map((set) => (
                <div
                  key={set.id}
                  style={{
                    background: 'linear-gradient(135deg, rgba(167, 139, 250, 0.07) 0%, rgba(255, 255, 255, 0.015) 100%)',
                  }}
                  className="p-7 rounded-3xl backdrop-blur-xl border border-[rgba(167,139,250,0.2)] hover:border-[rgba(167,139,250,0.45)] hover:shadow-[0_0_28px_rgba(167,139,250,0.15)] transition-all duration-300 flex flex-col justify-between group"
                >
                  <div>
                    <div className="flex items-center justify-between gap-3 mb-4">
                      <div className="w-11 h-11 rounded-2xl bg-[rgba(167,139,250,0.15)] flex items-center justify-center border border-[rgba(255,255,255,0.05)] text-[#C4B5FD]">
                        <Layers size={18} />
                      </div>
                      <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-md border text-[#C4B5FD] bg-[rgba(167,139,250,0.2)] border-[rgba(167,139,250,0.3)]">
                        MERGED
                      </span>
                    </div>
                    <h3 className="text-base font-semibold text-white tracking-tight truncate group-hover:text-[#C4B5FD] transition-colors duration-200 mb-2" title={set.name}>
                      {set.name}
                    </h3>
                    <div className="flex items-center gap-2 text-xs text-[#A1A1AA] font-mono flex-wrap">
                      <span>{set.documents.length} {set.documents.length === 1 ? 'source' : 'sources'}</span>
                      <span className="flex items-center gap-1">
                        {[...new Set(set.documents.map((d) => d.source_type))].map((t) => (
                          <span key={t}>{sourceBadge(t, 12).icon}</span>
                        ))}
                      </span>
                      <span>•</span>
                      {set.flashcard_count > 0 ? (
                        <span className="text-[#34D399]">{set.flashcard_count} cards</span>
                      ) : (
                        <span>Not generated yet</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center justify-between pt-6 mt-6 border-t border-[rgba(255,255,255,0.06)]">
                    <Link
                      to={`/library/merged/${set.id}/summary`}
                      className="inline-flex items-center gap-1.5 text-xs font-medium text-[#A1A1AA] hover:text-white px-2.5 py-1.5 rounded-lg hover:bg-[rgba(255,255,255,0.06)] transition-all duration-200"
                    >
                      <BookOpen size={14} className="text-[#71717A]" />
                      <span>View Summary</span>
                    </Link>
                    <Link
                      to={`/library/merged/${set.id}/flashcards`}
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white shadow-[0_0_18px_rgba(59,130,246,0.35)] hover:shadow-[0_0_24px_rgba(59,130,246,0.5)] hover:brightness-110 transition-all duration-200"
                    >
                      <span>Study Deck</span>
                      <ArrowRight size={13} />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
        {mergedSets.length > 0 && (
          <h2 className="flex items-center gap-2 text-sm font-semibold text-white mb-4">
            <FileText size={16} className="text-[#93C5FD]" />
            Document decks
          </h2>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {documents.map((doc) => {
            const badge = getSourceBadge(doc.source_type)
            return (
              <div
                key={doc.id}
                style={{
                  background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0.015) 100%)',
                }}
                className="p-7 rounded-3xl backdrop-blur-xl border border-[rgba(255,255,255,0.08)] hover:border-[rgba(59,130,246,0.35)] hover:shadow-[0_0_28px_rgba(59,130,246,0.18)] transition-all duration-300 flex flex-col justify-between group relative overflow-hidden"
              >
                <div>
                  <div className="flex items-center justify-between gap-3 mb-4">
                    <div className={`w-11 h-11 rounded-2xl ${badge.bgColor} flex items-center justify-center border border-[rgba(255,255,255,0.05)] group-hover:scale-105 transition-all duration-200`}>
                      {badge.icon}
                    </div>
                    <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-md border ${badge.badgeStyle}`}>
                      {badge.badgeText}
                    </span>
                  </div>

                  <h3
                    className="text-base font-semibold text-white tracking-tight truncate group-hover:text-[#93C5FD] transition-colors duration-200 mb-2"
                    title={doc.filename}
                  >
                    {doc.filename}
                  </h3>

                  <div className="flex items-center gap-3 text-xs text-[#A1A1AA] font-mono">
                    <span>{doc.total_chunks} chunks</span>
                    <span>•</span>
                    {doc.total_chunks > 0 ? (
                      <span className="text-[#34D399]">Ready to study</span>
                    ) : (
                      <span className="text-[#FBBF24]">No content indexed</span>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between pt-6 mt-6 border-t border-[rgba(255,255,255,0.06)]">
                  {/* Secondary subtle action */}
                  <Link
                    to={`/library/${doc.id}/summary`}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-[#A1A1AA] hover:text-white px-2.5 py-1.5 rounded-lg hover:bg-[rgba(255,255,255,0.06)] transition-all duration-200"
                  >
                    <BookOpen size={14} className="text-[#71717A]" />
                    <span>View Summary</span>
                  </Link>

                  {/* Primary prominent action */}
                  <Link
                    to={`/library/${doc.id}/flashcards`}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white shadow-[0_0_18px_rgba(59,130,246,0.35)] hover:shadow-[0_0_24px_rgba(59,130,246,0.5)] hover:brightness-110 transition-all duration-200"
                  >
                    <span>Study Deck</span>
                    <ArrowRight size={13} />
                  </Link>
                </div>
              </div>
            )
          })}
        </div>
        </>
      )}
    </div>
  )
}
