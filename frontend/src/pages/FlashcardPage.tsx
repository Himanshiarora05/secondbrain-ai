import { useEffect, useState, useTransition } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Shuffle,
  RotateCw,
  RefreshCw,
  Layers,
  AlertCircle,
  HelpCircle,
  CheckCircle2,
  Presentation,
  FileText,
  FileEdit,
  Video,
  Globe,
  ExternalLink,
} from 'lucide-react'
import { getDocuments, getFlashcards, generateFlashcards } from '../api/client'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import type { DocumentItem, Flashcard } from '../types'

export function FlashcardPage() {
  const { documentId } = useParams<{ documentId: string }>()
  const docIdNum = documentId ? parseInt(documentId, 10) : NaN

  const [document, setDocument] = useState<DocumentItem | null>(null)
  const [cards, setCards] = useState<Flashcard[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isFlipped, setIsFlipped] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [, startTransition] = useTransition()

  // Load document and flashcards
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
      setIsFlipped(false)

      try {
        const docs = await getDocuments()
        const found = docs.find((d) => d.id === docIdNum)
        if (isMounted && found) {
          setDocument(found)
        }

        const res = await getFlashcards(docIdNum)
        if (res.flashcards && res.flashcards.length > 0) {
          if (isMounted) {
            startTransition(() => {
              setCards(res.flashcards)
              setCurrentIndex(0)
            })
          }
        } else {
          // Auto-generate 10 flashcards if none exist yet
          const genRes = await generateFlashcards(docIdNum, 10)
          if (isMounted) {
            startTransition(() => {
              setCards(genRes.flashcards)
              setCurrentIndex(0)
            })
          }
        }
      } catch (err: any) {
        if (isMounted) {
          setError(err.message || 'Failed to load flashcards')
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

  // Keyboard navigation: Space/Enter to flip, Left/Right arrows to navigate
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isLoading || cards.length === 0) return
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        setIsFlipped((prev) => !prev)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        handleNext()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        handlePrev()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [cards.length, currentIndex, isLoading])

  const handleNext = () => {
    if (currentIndex < cards.length - 1) {
      setIsFlipped(false)
      setCurrentIndex((prev) => prev + 1)
    }
  }

  const handlePrev = () => {
    if (currentIndex > 0) {
      setIsFlipped(false)
      setCurrentIndex((prev) => prev - 1)
    }
  }

  const handleShuffle = () => {
    if (cards.length <= 1) return
    setIsFlipped(false)
    const shuffled = [...cards].sort(() => Math.random() - 0.5)
    setCards(shuffled)
    setCurrentIndex(0)
  }

  const handleRegenerate = async () => {
    if (isNaN(docIdNum)) return
    setIsRegenerating(true)
    setError(null)
    setIsFlipped(false)

    try {
      const res = await generateFlashcards(docIdNum, 10)
      startTransition(() => {
        setCards(res.flashcards)
        setCurrentIndex(0)
      })
    } catch (err: any) {
      setError(err.message || 'Failed to regenerate flashcards')
    } finally {
      setIsRegenerating(false)
    }
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
      case 'website':
        return {
          icon: <Globe size={14} className="text-[#22D3EE]" />,
          label: 'WEB',
          style: 'text-[#22D3EE] bg-[rgba(34,211,238,0.2)] border border-[rgba(34,211,238,0.3)]',
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
  const currentCard = cards[currentIndex]

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
            <Layers size={22} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-[rgba(59,130,246,0.12)] text-[#93C5FD] font-mono font-medium border border-[rgba(59,130,246,0.25)]">
                Flashcard Deck
              </span>
              <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-md flex items-center gap-1.5 ${badge.style}`}>
                {badge.icon}
                <span>{badge.label}</span>
              </span>
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight truncate max-w-md" title={document?.filename}>
              {document ? document.filename : `Document #${docIdNum}`}
            </h1>
            {cards.length > 0 && !isLoading && (
              <p className="text-xs text-[#A1A1AA] mt-1 font-mono">
                {cards.length} revision cards ready
              </p>
            )}
          </div>
        </div>

        {/* Action Controls */}
        {cards.length > 0 && !isLoading && (
          <div className="flex items-center gap-2.5 sm:self-center self-start">
            <button
              onClick={handleShuffle}
              className="flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] text-[#A1A1AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.15)] transition-all duration-200"
              title="Shuffle deck"
            >
              <Shuffle size={14} />
              <span>Shuffle</span>
            </button>

            <button
              onClick={handleRegenerate}
              disabled={isRegenerating}
              className="flex items-center gap-1.5 px-4 py-2.5 text-xs font-semibold rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] hover:brightness-110 text-white transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] disabled:opacity-50"
              title="Regenerate cards with AI"
            >
              <RefreshCw size={14} className={isRegenerating ? 'animate-spin' : ''} />
              <span>{isRegenerating ? 'Regenerating...' : 'Regenerate'}</span>
            </button>
          </div>
        )}
      </div>

      {/* Main Deck Area */}
      <div className="p-8 md:p-12 rounded-3xl bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col items-center justify-center min-h-[480px]">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <LoadingSpinner size={44} className="mb-4 text-[#3B82F6]" />
            <h3 className="text-base font-semibold text-white mb-1.5">Generating Flashcard Deck</h3>
            <p className="text-xs text-[#A1A1AA] max-w-sm">
              Extracting core definitions, testable concepts, and exam questions with AI...
            </p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-14 h-14 rounded-full bg-[rgba(248,113,113,0.15)] flex items-center justify-center text-[#F87171] mb-4 border border-[rgba(248,113,113,0.25)] shadow-[0_0_20px_rgba(248,113,113,0.15)]">
              <AlertCircle size={28} />
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Failed to Load Flashcards</h3>
            <p className="text-xs text-[#A1A1AA] max-w-md mb-6">{error}</p>
            <button
              onClick={handleRegenerate}
              className="px-5 py-2.5 bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold rounded-xl transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110"
            >
              Try Again
            </button>
          </div>
        ) : cards.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Layers size={36} className="text-[#5C5C6E] mb-3" />
            <h3 className="text-base font-semibold text-white mb-1">No Flashcards Yet</h3>
            <p className="text-xs text-[#A1A1AA] max-w-sm mb-6">
              Generate study cards to test your knowledge on this document.
            </p>
            <button
              onClick={handleRegenerate}
              className="px-5 py-2.5 bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold rounded-xl transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110"
            >
              Generate Flashcards
            </button>
          </div>
        ) : (
          <div className="w-full flex flex-col items-center">
            {/* Progress indicator with gradient bar */}
            <div className="w-full mb-8 flex items-center justify-between text-xs text-[#A1A1AA]">
              <span className="font-mono font-medium text-white">
                Card {currentIndex + 1} of {cards.length}
              </span>
              <div className="w-48 sm:w-72 h-2.5 bg-[rgba(255,255,255,0.05)] rounded-full overflow-hidden border border-[rgba(255,255,255,0.08)]">
                <div
                  className="h-full bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] transition-all duration-300 rounded-full shadow-[0_0_12px_rgba(59,130,246,0.5)]"
                  style={{ width: `${((currentIndex + 1) / cards.length) * 100}%` }}
                />
              </div>
              <span className="text-[#5C5C6E] hidden sm:flex items-center gap-1.5 font-mono text-[11px]">
                <RotateCw size={12} /> Click card or Space to flip
              </span>
            </div>

            {/* 3D Flip Card */}
            <div
              className="w-full h-84 cursor-pointer [perspective:1000px] select-none group"
              onClick={() => setIsFlipped((prev) => !prev)}
            >
              <div
                className={`relative w-full h-full duration-500 [transform-style:preserve-3d] transition-transform rounded-3xl ${
                  isFlipped ? '[transform:rotateY(180deg)]' : ''
                }`}
              >
                {/* Front face: Question (Frosted Glass Floating Card) */}
                <div className="absolute inset-0 w-full h-full [backface-visibility:hidden] bg-[rgba(255,255,255,0.05)] backdrop-blur-2xl border border-[rgba(255,255,255,0.12)] group-hover:bg-[rgba(255,255,255,0.08)] group-hover:border-[rgba(59,130,246,0.4)] group-hover:shadow-[0_0_35px_rgba(59,130,246,0.18)] rounded-3xl p-8 md:p-10 flex flex-col justify-between shadow-[0_12px_40px_rgba(0,0,0,0.6)] transition-all duration-200">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold text-[#93C5FD] bg-[rgba(59,130,246,0.15)] px-3 py-1 rounded-lg border border-[rgba(59,130,246,0.3)]">
                      <HelpCircle size={14} /> QUESTION
                    </span>
                    <span className="text-xs text-[#A1A1AA] flex items-center gap-1.5 font-mono">
                      <span>Click to flip</span>
                      <RotateCw size={12} />
                    </span>
                  </div>

                  <div className="my-auto text-center px-4 overflow-y-auto max-h-48">
                    <p className="text-xl md:text-2xl font-semibold text-white leading-relaxed tracking-tight">
                      {currentCard?.question}
                    </p>
                  </div>

                  <div className="flex justify-between items-center text-[11px] text-[#A1A1AA] font-mono border-t border-[rgba(255,255,255,0.08)] pt-3.5">
                    <span>SecondBrain Study Deck</span>
                    <span>#{currentIndex + 1}</span>
                  </div>
                </div>

                {/* Back face: Answer (Frosted Glass Floating Card with green tint) */}
                <div className="absolute inset-0 w-full h-full [backface-visibility:hidden] [transform:rotateY(180deg)] bg-[rgba(255,255,255,0.05)] backdrop-blur-2xl border border-[rgba(52,211,153,0.35)] group-hover:bg-[rgba(255,255,255,0.08)] group-hover:border-[rgba(52,211,153,0.5)] group-hover:shadow-[0_0_35px_rgba(52,211,153,0.18)] rounded-3xl p-8 md:p-10 flex flex-col justify-between shadow-[0_12px_40px_rgba(0,0,0,0.6)] transition-all duration-200">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold text-[#34D399] bg-[rgba(52,211,153,0.18)] px-3 py-1 rounded-lg border border-[rgba(52,211,153,0.3)]">
                      <CheckCircle2 size={14} /> ANSWER
                    </span>
                    <span className="text-xs text-[#A1A1AA] flex items-center gap-1.5 font-mono">
                      <span>Click to flip back</span>
                      <RotateCw size={12} />
                    </span>
                  </div>

                  <div className="my-auto text-center px-4 overflow-y-auto max-h-48">
                    <p className="text-lg md:text-xl text-white leading-relaxed font-normal">
                      {currentCard?.answer}
                    </p>
                  </div>

                  <div className="flex justify-between items-center gap-4 text-[11px] text-[#A1A1AA] font-mono border-t border-[rgba(255,255,255,0.08)] pt-3.5">
                    {currentCard?.source_label ? (
                      currentCard.source_url ? (
                        <a
                          href={currentCard.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          tabIndex={isFlipped ? 0 : -1}
                          className="inline-flex items-center gap-1.5 min-w-0 text-[#34D399] hover:text-[#6EE7B7] hover:underline transition-colors"
                          title={`Open the source: ${currentCard.source_url}`}
                        >
                          <span className="truncate">Source: {currentCard.source_label}</span>
                          <ExternalLink size={11} className="flex-shrink-0" />
                        </a>
                      ) : (
                        <span className="truncate text-[#34D399]">Source: {currentCard.source_label}</span>
                      )
                    ) : (
                      <span className="text-[#34D399]">Concept Mastered</span>
                    )}
                    <span className="flex-shrink-0">#{currentIndex + 1}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Navigation Controls */}
            <div className="flex items-center justify-center gap-4 mt-8">
              <button
                onClick={handlePrev}
                disabled={currentIndex === 0}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] text-[#A1A1AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.15)] disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 text-xs font-medium shadow-sm"
                aria-label="Previous card"
              >
                <ChevronLeft size={16} />
                <span>Previous</span>
              </button>

              <button
                onClick={() => setIsFlipped((prev) => !prev)}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110 transition-all duration-200"
              >
                <RotateCw size={14} />
                <span>Flip Card</span>
              </button>

              <button
                onClick={handleNext}
                disabled={currentIndex === cards.length - 1}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] text-[#A1A1AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.15)] disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 text-xs font-medium shadow-sm"
                aria-label="Next card"
              >
                <span>Next</span>
                <ChevronRight size={16} />
              </button>
            </div>

            <p className="text-xs text-[#5C5C6E] mt-4 font-mono text-center">
              Shortcuts: Space to flip, ← / → arrows to navigate
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
