import { useEffect, useState, useTransition } from 'react'
import { useParams, useLocation, Link } from 'react-router-dom'
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Shuffle,
  RotateCw,
  RefreshCw,
  Layers,
  AlertCircle,
} from 'lucide-react'
import {
  getDocuments,
  getFlashcards,
  generateFlashcards,
  getMergedSet,
  getMergedFlashcards,
  generateMergedFlashcards,
  localToday,
  reviewCard,
} from '../api/client'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { sourceBadge, MERGED_BADGE_STYLE } from '../components/library/sourceBadge'
import { MergedSetMembers, MergedSetNotices } from '../components/library/MergedSetHeader'
import { FlipCard } from '../components/library/FlipCard'
import { ReviewButtons } from '../components/library/ReviewButtons'
import { GRADE_KEYS, dueLabel, nextReviewText } from '../components/library/reviewSchedule'
import type { DocumentItem, Flashcard, MergedSet, ReviewGrade } from '../types'

// With `merged`, the page shows a merged set's deck (route /library/merged/:setId/flashcards).
export function FlashcardPage({ merged = false }: { merged?: boolean }) {
  const params = useParams<{ documentId?: string; setId?: string }>()
  const rawId = merged ? params.setId : params.documentId
  const docIdNum = rawId ? parseInt(rawId, 10) : NaN
  const location = useLocation()
  const reopened = merged && Boolean((location.state as { reopened?: boolean } | null)?.reopened)

  const [document, setDocument] = useState<DocumentItem | null>(null)
  const [mergedSet, setMergedSet] = useState<MergedSet | null>(null)
  const [stale, setStale] = useState(false)
  const [cards, setCards] = useState<Flashcard[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isFlipped, setIsFlipped] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isRating, setIsRating] = useState(false)
  // What the last rating did ("Next review in 6 days"), or why it failed.
  const [reviewNote, setReviewNote] = useState<{ text: string; error?: boolean } | null>(null)
  const [, startTransition] = useTransition()

  // Load document (or merged set) and flashcards
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
      setIsFlipped(false)

      try {
        if (merged) {
          const set = await getMergedSet(docIdNum)
          if (isMounted) setMergedSet(set)
          const res = await getMergedFlashcards(docIdNum)
          // Auto-generate 10 flashcards if none exist yet
          const deck = res.flashcards.length > 0 ? res : await generateMergedFlashcards(docIdNum, 10)
          if (isMounted) {
            startTransition(() => {
              setCards(deck.flashcards)
              setStale(deck.stale)
              setCurrentIndex(0)
            })
          }
          return
        }

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
  }, [docIdNum, merged])

  const cannotRegenerate = merged && mergedSet !== null && mergedSet.documents.length < 2

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
      } else if (isFlipped && !isRating && GRADE_KEYS[e.key]) {
        e.preventDefault()
        handleRate(GRADE_KEYS[e.key])
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [cards, currentIndex, isLoading, isFlipped, isRating])

  const handleNext = () => {
    if (currentIndex < cards.length - 1) {
      setIsFlipped(false)
      setReviewNote(null)
      setCurrentIndex((prev) => prev + 1)
    }
  }

  const handlePrev = () => {
    if (currentIndex > 0) {
      setIsFlipped(false)
      setReviewNote(null)
      setCurrentIndex((prev) => prev - 1)
    }
  }

  // Saves the rating, then moves on to the next card (or stays on the last one).
  const handleRate = async (grade: ReviewGrade) => {
    const card = cards[currentIndex]
    if (!card || isRating) return
    setIsRating(true)
    try {
      const schedule = await reviewCard(merged ? 'merged' : 'document', card.id, grade)
      setCards((prev) => prev.map((c) => (c.id === card.id ? { ...c, ...schedule } : c)))
      const isLast = currentIndex === cards.length - 1
      setReviewNote({ text: isLast ? `${nextReviewText(schedule)} · Last card in the deck` : nextReviewText(schedule) })
      setIsFlipped(false)
      if (!isLast) setCurrentIndex((prev) => prev + 1)
    } catch (err: any) {
      setReviewNote({ text: err.message || 'Failed to save your answer', error: true })
      setIsFlipped(false)
    } finally {
      setIsRating(false)
    }
  }

  const today = localToday()
  const dueInDeck = cards.filter((c) => c.due_date && c.due_date <= today).length

  const handleShuffle = () => {
    if (cards.length <= 1) return
    setIsFlipped(false)
    setReviewNote(null)
    const shuffled = [...cards].sort(() => Math.random() - 0.5)
    setCards(shuffled)
    setCurrentIndex(0)
  }

  const handleRegenerate = async () => {
    if (isNaN(docIdNum) || cannotRegenerate) return
    setIsRegenerating(true)
    setError(null)
    setIsFlipped(false)
    setReviewNote(null)

    try {
      if (merged) {
        const res = await generateMergedFlashcards(docIdNum, 10)
        startTransition(() => {
          setCards(res.flashcards)
          setStale(res.stale)
          setCurrentIndex(0)
        })
        return
      }
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
            <h1 className="text-xl font-bold text-white tracking-tight truncate max-w-md" title={title}>
              {title}
            </h1>
            {mergedSet && <MergedSetMembers set={mergedSet} page="flashcards" />}
            {cards.length > 0 && !isLoading && (
              <p className="text-xs text-[#A1A1AA] mt-1 font-mono">
                {cards.length} revision cards ready
                {dueInDeck > 0 && <span className="text-[#FBBF24]"> · {dueInDeck} due today</span>}
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
              disabled={isRegenerating || cannotRegenerate}
              className="flex items-center gap-1.5 px-4 py-2.5 text-xs font-semibold rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] hover:brightness-110 text-white transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] disabled:opacity-50 disabled:cursor-not-allowed"
              title={cannotRegenerate ? 'A merged set needs at least 2 documents' : 'Regenerate cards with AI (new cards start a fresh review schedule)'}
            >
              <RefreshCw size={14} className={isRegenerating ? 'animate-spin' : ''} />
              <span>{isRegenerating ? 'Regenerating...' : 'Regenerate'}</span>
            </button>
          </div>
        )}
      </div>

      {mergedSet && !isLoading && (
        <MergedSetNotices set={mergedSet} what="deck" stale={stale} reopened={reopened} />
      )}

      {/* Main Deck Area */}
      <div className="p-4 sm:p-8 md:p-12 rounded-3xl bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col items-center justify-center min-h-[480px]">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <LoadingSpinner size={44} className="mb-4 text-[#3B82F6]" />
            <h3 className="text-base font-semibold text-white mb-1.5">Generating Flashcard Deck</h3>
            <p className="text-xs text-[#A1A1AA] max-w-sm">
              {merged
                ? 'Making cards from every document in the set, each citing its source. Large sets can take a minute...'
                : 'Extracting core definitions, testable concepts, and exam questions with AI...'}
            </p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-14 h-14 rounded-full bg-[rgba(248,113,113,0.15)] flex items-center justify-center text-[#F87171] mb-4 border border-[rgba(248,113,113,0.25)] shadow-[0_0_20px_rgba(248,113,113,0.15)]">
              <AlertCircle size={28} />
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Failed to Load Flashcards</h3>
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
        ) : cards.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Layers size={36} className="text-[#5C5C6E] mb-3" />
            <h3 className="text-base font-semibold text-white mb-1">No Flashcards Yet</h3>
            <p className="text-xs text-[#A1A1AA] max-w-sm mb-6">
              Generate study cards to test your knowledge on this {merged ? 'merged set' : 'document'}.
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

            <FlipCard
              card={currentCard}
              isFlipped={isFlipped}
              onFlip={() => setIsFlipped((prev) => !prev)}
              number={`#${currentIndex + 1}`}
              frontFooter={currentCard ? dueLabel(currentCard) : undefined}
            />

            {/* Spaced repetition: rate the card once its answer is showing */}
            <div className="mt-6 min-h-[76px] flex flex-col items-center justify-center">
              {isFlipped ? (
                <ReviewButtons onRate={handleRate} disabled={isRating} />
              ) : reviewNote ? (
                <p className={`text-xs font-mono ${reviewNote.error ? 'text-[#F87171]' : 'text-[#34D399]'}`}>
                  {reviewNote.text}
                </p>
              ) : (
                <p className="text-xs font-mono text-[#5C5C6E]">Flip the card, then rate how well you knew it</p>
              )}
            </div>

            {/* Navigation Controls */}
            <div className="flex items-center justify-center gap-4 mt-4">
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
              Shortcuts: Space to flip, ← / → arrows to navigate, 1 / 2 / 3 to rate
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
