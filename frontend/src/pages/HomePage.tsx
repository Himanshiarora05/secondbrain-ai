import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Search, Sparkles, Clock, ArrowRight } from 'lucide-react'
import { searchSecondBrain } from '../api/client'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { SourceCard } from '../components/chat/SourceCard'
import { UploadZone } from '../components/library/UploadZone'
import { AuroraBackground } from '../components/home/AuroraBackground'
import { useDocuments } from '../context/DocumentContext'
import type { SearchResult } from '../types'

export function HomePage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { documents, refreshDocuments } = useDocuments()

  const recentDocs = [...documents].sort((a, b) => b.id - a.id).slice(0, 4)

  useEffect(() => {
    // If documents are not yet loaded (e.g. direct mount after timeout), fetch them
    if (documents.length === 0) {
      refreshDocuments().catch(err => console.error('Failed to load documents on Home:', err))
    }
  }, [documents.length, refreshDocuments])

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!searchQuery.trim()) return

    setIsLoading(true)
    setError(null)
    setResult(null)

    try {
      const data = await searchSecondBrain(searchQuery.trim())
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setIsLoading(false)
    }
  }

  const getSourceIcon = (type?: string) => {
    switch (type) {
      case 'pptx':
        return <span className="text-xs font-mono font-bold text-[#FBBF24]">PPT</span>
      case 'docx':
        return <span className="text-xs font-mono font-bold text-[#60A5FA]">DOC</span>
      case 'youtube':
        return <span className="text-xs font-mono font-bold text-[#F87171]">YT</span>
      case 'pdf':
      default:
        return <span className="text-xs font-mono font-bold text-[#FB7185]">PDF</span>
    }
  }

  const getSourceBadgeStyle = (type?: string) => {
    switch (type) {
      case 'pptx':
        return 'text-[#FBBF24] bg-[rgba(251,191,36,0.2)] border border-[rgba(251,191,36,0.3)]'
      case 'docx':
        return 'text-[#60A5FA] bg-[rgba(96,165,250,0.2)] border border-[rgba(96,165,250,0.3)]'
      case 'youtube':
        return 'text-[#F87171] bg-[rgba(248,113,113,0.2)] border border-[rgba(248,113,113,0.3)]'
      case 'pdf':
      default:
        return 'text-[#FB7185] bg-[rgba(251,113,133,0.2)] border border-[rgba(251,113,133,0.3)]'
    }
  }

  return (
    <div className="relative w-full flex-1 flex flex-col items-center animate-fade-in pb-20 pt-6 min-w-0">
      {/* Home-exclusive Aurora Background */}
      <AuroraBackground />

      <div className="w-full max-w-4xl flex flex-col items-center min-w-0">
        {/* Short Headline & One-Line Description with Gradient Typography */}
        <div className="text-center mb-12 max-w-3xl flex flex-col items-center">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[rgba(59,130,246,0.12)] border border-[rgba(59,130,246,0.25)] text-[#93C5FD] text-xs font-mono font-medium mb-6 shadow-[0_0_15px_rgba(59,130,246,0.15)]">
            <Sparkles size={13} />
            <span>AI-Powered Study Workspace</span>
          </div>

          <h1 className="text-5xl md:text-6xl font-bold tracking-tight mb-5 leading-tight select-none text-[#F2F4F8]">
            Your Second Brain
            <br />
            <span
              style={{
                background: 'linear-gradient(135deg, #93C5FD 0%, #3B82F6 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              Always With You
            </span>
          </h1>

          <p className="text-base md:text-lg text-[#8B93A7] leading-relaxed max-w-xl font-normal">
            Ingest lecture slides, readings, or YouTube videos to instantly generate exam-tailored revision summaries and active flashcard decks.
          </p>
        </div>

        {/* Semantic Search Bar (Frosted Glass with Soft Blue Glow) */}
        <form onSubmit={handleSearch} className="w-full mb-16">
          <div className="relative flex items-center bg-[#0A0D16]/90 backdrop-blur-xl border border-[#1C2233] rounded-2xl p-1.5 shadow-[0_4px_24px_rgba(0,0,0,0.6)] focus-within:border-[rgba(59,130,246,0.4)] focus-within:shadow-[0_0_24px_rgba(59,130,246,0.15)] transition-all duration-200">
            <div className="pl-4 flex items-center pointer-events-none text-[#545C70]">
              <Search size={19} />
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search across all ingested documents and video transcripts..."
              className="w-full bg-transparent border-0 pl-3.5 pr-28 py-3 text-sm text-[#F2F4F8] placeholder-[#545C70] focus:outline-none focus:ring-0"
            />
            <button
              type="submit"
              disabled={isLoading || !searchQuery.trim()}
              className="px-5 py-2.5 bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold rounded-xl transition-all duration-200 disabled:opacity-40 flex items-center gap-1.5 shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110 flex-shrink-0"
            >
              {isLoading ? (
                <>
                  <LoadingSpinner size={14} className="text-white" />
                  <span>Searching</span>
                </>
              ) : (
                <>
                  <span>Search</span>
                  <ArrowRight size={14} />
                </>
              )}
            </button>
          </div>
        </form>

        {/* Search Error Alert */}
        {error && (
          <div className="w-full p-4 bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.3)] text-[#F87171] rounded-2xl text-xs mb-8 text-center animate-fade-in">
            {error}
          </div>
        )}

        {/* Search Results Display (Glass Card) */}
        {result && !isLoading && (
          <div className="w-full p-8 rounded-3xl bg-[#0A0D16] border border-[#1C2233] shadow-[0_8px_32px_rgba(0,0,0,0.6)] mb-14 animate-fade-in">
            <div className="flex items-center justify-between mb-5 pb-4 border-b border-[#1C2233]">
              <h3 className="text-sm font-semibold text-[#F2F4F8] flex items-center gap-2">
                <Sparkles size={16} className="text-[#93C5FD]" />
                <span>AI Synthesis</span>
              </h3>
              <button
                onClick={() => { setResult(null); setSearchQuery(''); }}
                className="text-xs text-[#545C70] hover:text-[#F2F4F8] transition-colors duration-200"
              >
                Clear
              </button>
            </div>

            <div className="text-sm text-[#F2F4F8] leading-relaxed whitespace-pre-line mb-6 font-normal">
              {result.answer}
            </div>

            {result.top_matches && result.top_matches.length > 0 && (
              <div>
                <h4 className="text-[11px] font-mono font-semibold text-[#8B93A7] uppercase tracking-wider mb-3">
                  Source Citations & Video Clips
                </h4>
                <div className="flex flex-wrap gap-3">
                  {result.top_matches.map((match, i) => (
                    <SourceCard key={i} source={match} index={i + 1} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Prominent Single Upload Action Area */}
        <div className="w-full mb-14 mt-2">
          <UploadZone onUploadSuccess={() => { refreshDocuments().catch(console.error) }} />
        </div>

        {/* Recently Added Strip */}
        {recentDocs.length > 0 && (
          <div className="w-full">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2 text-xs font-mono font-semibold text-[#545C70] uppercase tracking-wider">
                <Clock size={15} />
                <span>Recently Added Materials</span>
              </div>
              <Link
                to="/library"
                className="text-xs text-[#93C5FD] hover:text-[#BFDBFE] font-medium transition-colors duration-200 flex items-center gap-1"
              >
                <span>Open Library</span>
                <ArrowRight size={13} />
              </Link>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {recentDocs.map((doc) => (
                <Link
                  key={doc.id}
                  to={`/library/${doc.id}/summary`}
                  className="p-5 rounded-2xl bg-[#0A0D16] border border-[#1C2233] hover:border-[rgba(59,130,246,0.35)] hover:shadow-[0_0_24px_rgba(59,130,246,0.18)] transition-all duration-300 flex items-center justify-between gap-4 group relative overflow-hidden"
                >
                  <div className="flex items-center gap-3.5 min-w-0">
                    <div className="w-9 h-9 rounded-xl bg-[#12161F] border border-[#1C2233] flex items-center justify-center flex-shrink-0">
                      {getSourceIcon(doc.source_type)}
                    </div>
                    <div className="min-w-0">
                      <p
                        className="text-xs font-semibold text-[#F2F4F8] truncate group-hover:text-[#93C5FD] transition-colors duration-200"
                        title={doc.filename}
                      >
                        {doc.filename}
                      </p>
                      <p className="text-[11px] text-[#545C70] font-mono mt-0.5">
                        {doc.total_chunks} chunks indexed
                      </p>
                    </div>
                  </div>

                  <span className={`text-[10px] font-mono font-bold px-2.5 py-1 rounded-lg uppercase flex-shrink-0 ${getSourceBadgeStyle(doc.source_type)}`}>
                    {doc.source_type || 'pdf'}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
