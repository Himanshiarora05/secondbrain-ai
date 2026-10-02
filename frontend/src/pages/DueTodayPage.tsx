import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarCheck, CheckCircle2, Layers, ArrowRight, RotateCw } from 'lucide-react'
import { getDueCards, reviewCard } from '../api/client'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { EmptyState } from '../components/ui/EmptyState'
import { FlipCard } from '../components/library/FlipCard'
import { ReviewButtons } from '../components/library/ReviewButtons'
import { GRADE_KEYS, dueLabel, nextReviewText } from '../components/library/reviewSchedule'
import { sourceBadge, MERGED_BADGE_STYLE } from '../components/library/sourceBadge'
import type { DueCard, DueCardsResponse, ReviewGrade } from '../types'

function deckLink(card: DueCard): string {
  return card.kind === 'merged' ? `/library/merged/${card.deck_id}/flashcards` : `/library/${card.deck_id}/flashcards`
}

function deckBadge(card: DueCard) {
  return card.deck_source_type === 'merged'
    ? { icon: <Layers size={12} className="text-[#C4B5FD]" />, label: 'MERGED', style: MERGED_BADGE_STYLE }
    : sourceBadge(card.deck_source_type, 12)
}

// The due cards grouped by deck, in the order the decks first appear in the queue.
function groupByDeck(cards: DueCard[]): { key: string; cards: DueCard[] }[] {
  const groups = new Map<string, DueCard[]>()
  for (const card of cards) {
    const key = `${card.kind}:${card.deck_id}`
    groups.set(key, [...(groups.get(key) ?? []), card])
  }
  return [...groups].map(([key, list]) => ({ key, cards: list }))
}

// Every card due today, from document decks and merged decks, reviewed in one session.
export function DueTodayPage() {
  // Still to review: the head is the card showing. "Again" sends a card to the back.
  const [queue, setQueue] = useState<DueCard[]>([])
  const [reviewed, setReviewed] = useState(0)
  // The day's totals as loaded (reviews, new cards, the new-card limit).
  const [totals, setTotals] = useState<Omit<DueCardsResponse, 'cards'> | null>(null)
  const [isFlipped, setIsFlipped] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isRating, setIsRating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<{ text: string; error?: boolean } | null>(null)

  useEffect(() => {
    let isMounted = true
    getDueCards()
      .then((res) => {
        if (isMounted) {
          const { cards, ...rest } = res
          setQueue(cards)
          setTotals(rest)
        }
      })
      .catch((err) => {
        if (isMounted) setError(err.message || 'Failed to load due cards')
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })
    return () => {
      isMounted = false
    }
  }, [])

  const current = queue[0]

  const handleRate = async (grade: ReviewGrade) => {
    if (!current || isRating) return
    setIsRating(true)
    try {
      const schedule = await reviewCard(current.kind, current.id, grade)
      const updated = { ...current, ...schedule }
      setQueue((prev) => (grade === 'again' ? [...prev.slice(1), updated] : prev.slice(1)))
      setReviewed((n) => n + 1)
      setNote({ text: grade === 'again' ? 'It will come back at the end of this session' : nextReviewText(schedule) })
      setIsFlipped(false)
    } catch (err: any) {
      setNote({ text: err.message || 'Failed to save your answer', error: true })
      setIsFlipped(false)
    } finally {
      setIsRating(false)
    }
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!current) return
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        setIsFlipped((prev) => !prev)
      } else if (isFlipped && !isRating && GRADE_KEYS[e.key]) {
        e.preventDefault()
        handleRate(GRADE_KEYS[e.key])
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [queue, isFlipped, isRating])

  const groups = groupByDeck(queue)

  return (
    <div className="flex flex-col w-full max-w-4xl mx-auto animate-fade-in pb-16 min-w-0">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl bg-[rgba(251,191,36,0.12)] border border-[rgba(251,191,36,0.3)] flex items-center justify-center text-[#FBBF24]">
            <CalendarCheck size={20} />
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Due today</h1>
        </div>
        <p className="text-[#A1A1AA] text-sm max-w-xl">
          Cards from all your decks that are due for review. Rate each one: <span className="text-[#F87171]">Again</span>{' '}
          brings it back today, <span className="text-[#93C5FD]">Good</span> and <span className="text-[#34D399]">Easy</span>{' '}
          space it out further each time. Cards you haven't rated yet join as new cards, up to {totals?.new_limit ?? 20} a day (oldest first); new cards you start in a deck count too.
        </p>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20">
          <LoadingSpinner size={40} className="mb-4 text-[#3B82F6]" />
          <p className="text-sm text-[#A1A1AA]">Loading due cards...</p>
        </div>
      ) : error ? (
        <div className="p-6 bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.3)] text-[#F87171] rounded-2xl text-center max-w-md mx-auto">
          <p className="text-sm">{error}</p>
        </div>
      ) : !current ? (
        <EmptyState
          icon={<CheckCircle2 size={36} />}
          title={reviewed > 0 ? 'All done for today' : 'Nothing due today'}
          description={
            (reviewed > 0
              ? `You reviewed ${reviewed} ${reviewed === 1 ? 'card' : 'cards'}. Come back when the next ones are due.`
              : totals && totals.new_waiting > 0
                ? "You've started today's new cards."
                : 'Generate flashcards for a document or merged set to start reviewing.') +
            (totals && totals.new_waiting > 0
              ? ` ${totals.new_waiting} more new ${totals.new_waiting === 1 ? 'card is' : 'cards are'} waiting: up to ${totals.new_limit} new cards join each day.`
              : '')
          }
          action={
            <Link
              to="/flashcards"
              className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold hover:brightness-110 transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)]"
            >
              <span>Go to Flashcards</span>
              <ArrowRight size={13} />
            </Link>
          }
        />
      ) : (
        <>
          {/* Review session */}
          <div className="p-4 sm:p-8 md:p-10 rounded-3xl bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col items-center mb-10">
            <div className="w-full mb-6 flex items-center justify-between gap-4 text-xs text-[#A1A1AA]">
              <span className="font-mono font-medium text-white">
                {queue.length} left{reviewed > 0 && <span className="text-[#A1A1AA]"> · {reviewed} reviewed</span>}
              </span>
              <Link
                to={deckLink(current)}
                className="flex items-center gap-2 min-w-0 hover:text-white transition-colors"
                title={`Open the deck: ${current.deck_name}`}
              >
                <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-md flex items-center gap-1.5 flex-shrink-0 ${deckBadge(current).style}`}>
                  {deckBadge(current).icon}
                  <span>{deckBadge(current).label}</span>
                </span>
                <span className="truncate">{current.deck_name}</span>
              </Link>
            </div>

            <FlipCard
              card={current}
              isFlipped={isFlipped}
              onFlip={() => setIsFlipped((prev) => !prev)}
              number={`#${reviewed + 1}`}
              frontFooter={dueLabel(current)}
            />

            <div className="mt-6 min-h-[76px] flex flex-col items-center justify-center">
              {isFlipped ? (
                <ReviewButtons onRate={handleRate} disabled={isRating} />
              ) : (
                <>
                  <button
                    onClick={() => setIsFlipped(true)}
                    className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110 transition-all duration-200"
                  >
                    <RotateCw size={14} />
                    <span>Show Answer</span>
                  </button>
                  {note && (
                    <p className={`mt-3 text-xs font-mono ${note.error ? 'text-[#F87171]' : 'text-[#34D399]'}`}>{note.text}</p>
                  )}
                </>
              )}
            </div>
            <p className="text-xs text-[#5C5C6E] mt-2 font-mono text-center">Shortcuts: Space to flip, 1 / 2 / 3 to rate</p>
          </div>

          {/* What's still due, by deck */}
          <section aria-labelledby="due-list-heading">
            <h2 id="due-list-heading" className="text-sm font-semibold text-white mb-4">
              Still due ({queue.length})
            </h2>
            {totals && (
              <p className="text-xs text-[#A1A1AA] font-mono -mt-2 mb-4">
                Today: {totals.review_count} {totals.review_count === 1 ? 'review' : 'reviews'} · {totals.new_count} new
                {totals.new_waiting > 0 && ` · ${totals.new_waiting} more new waiting (daily limit ${totals.new_limit})`}
              </p>
            )}
            <div className="flex flex-col gap-4">
              {groups.map(({ key, cards }) => {
                const badge = deckBadge(cards[0])
                return (
                  <div key={key} className="p-5 rounded-2xl bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)]">
                    <div className="flex items-center justify-between gap-3 mb-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-md flex items-center gap-1.5 flex-shrink-0 ${badge.style}`}>
                          {badge.icon}
                          <span>{badge.label}</span>
                        </span>
                        <span className="text-sm font-medium text-white truncate" title={cards[0].deck_name}>
                          {cards[0].deck_name}
                        </span>
                      </div>
                      <Link
                        to={deckLink(cards[0])}
                        className="flex-shrink-0 inline-flex items-center gap-1 text-xs text-[#93C5FD] hover:text-white transition-colors"
                      >
                        <span>{cards.length} {cards.length === 1 ? 'card' : 'cards'} · Open deck</span>
                        <ArrowRight size={12} />
                      </Link>
                    </div>
                    <ul className="flex flex-col gap-1.5">
                      {cards.map((card) => (
                        <li key={`${card.kind}-${card.id}`} className="text-xs text-[#A1A1AA] truncate" title={card.question}>
                          {card === current ? <span className="text-[#FBBF24]">▸ </span> : '· '}
                          {card.question}
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })}
            </div>
          </section>
        </>
      )}
    </div>
  )
}
