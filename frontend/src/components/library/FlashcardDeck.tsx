import { useEffect, useState, useTransition } from 'react'
import {
  X,
  ChevronLeft,
  ChevronRight,
  Shuffle,
  RotateCw,
  RefreshCw,
  Layers,
  AlertCircle,
  HelpCircle,
  CheckCircle2,
} from 'lucide-react'
import { getFlashcards, generateFlashcards } from '../../api/client'
import { LoadingSpinner } from '../ui/LoadingSpinner'
import { EmptyState } from '../ui/EmptyState'
import type { DocumentItem, Flashcard } from '../../types'

interface FlashcardDeckProps {
  document: DocumentItem
  onClose: () => void
}

export function FlashcardDeck({ document, onClose }: FlashcardDeckProps) {
  const [cards, setCards] = useState<Flashcard[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isFlipped, setIsFlipped] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [, startTransition] = useTransition()

  const loadFlashcards = async (forceRegenerate = false) => {
    if (forceRegenerate) {
      setIsRegenerating(true)
    } else {
      setIsLoading(true)
    }
    setError(null)
    setIsFlipped(false)

    try {
      if (forceRegenerate) {
        const res = await generateFlashcards(document.id, 10)
        startTransition(() => {
          setCards(res.flashcards)
          setCurrentIndex(0)
        })
      } else {
        const res = await getFlashcards(document.id)
        if (res.flashcards && res.flashcards.length > 0) {
          startTransition(() => {
            setCards(res.flashcards)
            setCurrentIndex(0)
          })
        } else {
          // If none exist yet, generate 10 flashcards
          const genRes = await generateFlashcards(document.id, 10)
          startTransition(() => {
            setCards(genRes.flashcards)
            setCurrentIndex(0)
          })
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load flashcards')
    } finally {
      setIsLoading(false)
      setIsRegenerating(false)
    }
  }

  useEffect(() => {
    loadFlashcards(false)
  }, [document.id])

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

  const currentCard = cards[currentIndex]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in">
      <div
        className="relative w-full max-w-2xl flex flex-col bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-primary)] bg-[var(--bg-elevated)]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-[var(--accent-primary-muted)] text-[var(--accent-primary)] flex items-center justify-center">
              <Layers size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                Flashcard Deck
                {cards.length > 0 && !isLoading && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--bg-secondary)] text-[var(--text-secondary)] font-mono border border-[var(--border-primary)]">
                    {cards.length} cards
                  </span>
                )}
              </h2>
              <p className="text-xs text-[var(--text-secondary)] truncate max-w-xs md:max-w-md" title={document.filename}>
                {document.filename}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {cards.length > 0 && !isLoading && (
              <>
                <button
                  onClick={handleShuffle}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--border-primary)] text-[var(--text-secondary)] hover:text-white hover:bg-[var(--bg-hover)] transition-colors"
                  title="Shuffle deck"
                >
                  <Shuffle size={14} />
                  <span>Shuffle</span>
                </button>

                <button
                  onClick={() => loadFlashcards(true)}
                  disabled={isRegenerating}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--border-primary)] text-[var(--text-secondary)] hover:text-white hover:bg-[var(--bg-hover)] transition-colors disabled:opacity-50"
                  title="Regenerate flashcards"
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

        {/* Deck Content */}
        <div className="p-6 md:p-8 flex flex-col items-center justify-center min-h-[360px]">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <LoadingSpinner size={44} className="mb-4" />
              <h3 className="text-base font-semibold text-white mb-1">Generating Spaced-Repetition Flashcards</h3>
              <p className="text-xs text-[var(--text-secondary)] max-w-sm">
                Parsing core concepts, key definitions, and exam questions with AI...
              </p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center text-[var(--error)] mb-4">
                <AlertCircle size={28} />
              </div>
              <h3 className="text-base font-semibold text-white mb-2">Failed to Load Flashcards</h3>
              <p className="text-xs text-[var(--text-secondary)] max-w-md mb-6">{error}</p>
              <button
                onClick={() => loadFlashcards(false)}
                className="px-4 py-2 bg-[var(--accent-primary)] hover:bg-[var(--accent-primary-hover)] text-white text-xs font-medium rounded-lg transition-colors"
              >
                Try Again
              </button>
            </div>
          ) : cards.length === 0 ? (
            <EmptyState
              icon={<Layers size={32} />}
              title="No Flashcards Yet"
              description="Click below to generate high-yield exam flashcards for this document."
              action={
                <button
                  onClick={() => loadFlashcards(true)}
                  className="mt-4 px-4 py-2 bg-[var(--accent-primary)] text-white text-xs font-medium rounded-lg"
                >
                  Generate Flashcards
                </button>
              }
            />
          ) : (
            <div className="w-full flex flex-col items-center">
              {/* Progress bar */}
              <div className="w-full mb-6 flex items-center justify-between text-xs text-[var(--text-secondary)]">
                <span className="font-mono">
                  Card {currentIndex + 1} of {cards.length}
                </span>
                <div className="w-48 h-1.5 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[var(--accent-primary)] transition-all duration-300"
                    style={{ width: `${((currentIndex + 1) / cards.length) * 100}%` }}
                  />
                </div>
                <span className="text-[var(--text-tertiary)] flex items-center gap-1">
                  <RotateCw size={12} /> Click card or space to flip
                </span>
              </div>

              {/* 3D Flip Flashcard */}
              <div
                className="w-full h-72 cursor-pointer [perspective:1000px] select-none group"
                onClick={() => setIsFlipped((prev) => !prev)}
              >
                <div
                  className={`relative w-full h-full duration-500 [transform-style:preserve-3d] transition-transform rounded-2xl ${
                    isFlipped ? '[transform:rotateY(180deg)]' : ''
                  }`}
                >
                  {/* Front: Question */}
                  <div className="absolute inset-0 w-full h-full [backface-visibility:hidden] bg-[var(--bg-elevated)] border-2 border-[var(--border-secondary)] group-hover:border-[var(--border-accent)] rounded-2xl p-8 flex flex-col justify-between shadow-xl transition-colors">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold text-[var(--accent-primary)] bg-[var(--accent-primary-muted)] px-2.5 py-1 rounded-md">
                        <HelpCircle size={14} /> QUESTION
                      </span>
                      <span className="text-xs text-[var(--text-tertiary)]">Click to flip</span>
                    </div>

                    <div className="my-auto text-center px-4 overflow-y-auto max-h-40">
                      <p className="text-base md:text-lg font-medium text-white leading-relaxed">
                        {currentCard?.question}
                      </p>
                    </div>

                    <div className="flex justify-between items-center text-[10px] text-[var(--text-muted)] font-mono">
                      <span>SecondBrain Study Deck</span>
                      <span>#{currentIndex + 1}</span>
                    </div>
                  </div>

                  {/* Back: Answer */}
                  <div className="absolute inset-0 w-full h-full [backface-visibility:hidden] [transform:rotateY(180deg)] bg-[var(--bg-tertiary)] border-2 border-[var(--success-muted)] rounded-2xl p-8 flex flex-col justify-between shadow-xl">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold text-[var(--success)] bg-[var(--success-muted)] px-2.5 py-1 rounded-md">
                        <CheckCircle2 size={14} /> ANSWER
                      </span>
                      <span className="text-xs text-[var(--text-tertiary)]">Click to flip back</span>
                    </div>

                    <div className="my-auto text-center px-4 overflow-y-auto max-h-40">
                      <p className="text-base md:text-lg text-[var(--text-primary)] leading-relaxed font-normal">
                        {currentCard?.answer}
                      </p>
                    </div>

                    <div className="flex justify-between items-center text-[10px] text-[var(--text-muted)] font-mono">
                      <span>Concept Mastered?</span>
                      <span>#{currentIndex + 1}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Navigation Controls */}
              <div className="flex items-center justify-center gap-4 mt-6">
                <button
                  onClick={handlePrev}
                  disabled={currentIndex === 0}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)] text-white hover:bg-[var(--bg-hover)] disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                  aria-label="Previous card"
                >
                  <ChevronLeft size={18} />
                  <span className="text-xs font-medium">Previous</span>
                </button>

                <button
                  onClick={() => setIsFlipped((prev) => !prev)}
                  className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-[var(--accent-primary-muted)] text-[var(--accent-primary)] hover:bg-[var(--accent-primary)] hover:text-white border border-[var(--border-accent)] text-xs font-medium transition-all"
                >
                  <RotateCw size={14} />
                  <span>Flip Card</span>
                </button>

                <button
                  onClick={handleNext}
                  disabled={currentIndex === cards.length - 1}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-primary)] text-white hover:bg-[var(--bg-hover)] disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                  aria-label="Next card"
                >
                  <span className="text-xs font-medium">Next</span>
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-[var(--border-primary)] bg-[var(--bg-elevated)] flex justify-between items-center text-xs text-[var(--text-tertiary)]">
          <span>Shortcuts: Space to flip, ← / → to navigate</span>
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
