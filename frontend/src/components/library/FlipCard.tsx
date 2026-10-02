import { RotateCw, HelpCircle, CheckCircle2, ExternalLink } from 'lucide-react'
import type { Flashcard } from '../../types'

interface FlipCardProps {
  card: Flashcard | undefined
  isFlipped: boolean
  onFlip: () => void
  // Shown bottom right on both faces, e.g. "#3".
  number: string
  // Shown bottom left on the question face.
  frontFooter?: React.ReactNode
}

// The 3D flip card used by a deck and by the Due today review.
export function FlipCard({ card, isFlipped, onFlip, number, frontFooter = 'SecondBrain Study Deck' }: FlipCardProps) {
  return (
    <div className="w-full h-84 cursor-pointer [perspective:1000px] select-none group" onClick={onFlip}>
      <div
        className={`relative w-full h-full duration-500 [transform-style:preserve-3d] transition-transform rounded-3xl ${
          isFlipped ? '[transform:rotateY(180deg)]' : ''
        }`}
      >
        {/* Front face: Question (Frosted Glass Floating Card) */}
        <div className="absolute inset-0 w-full h-full [backface-visibility:hidden] bg-[rgba(255,255,255,0.05)] backdrop-blur-2xl border border-[rgba(255,255,255,0.12)] group-hover:bg-[rgba(255,255,255,0.08)] group-hover:border-[rgba(59,130,246,0.4)] group-hover:shadow-[0_0_35px_rgba(59,130,246,0.18)] rounded-3xl p-5 sm:p-8 md:p-10 flex flex-col justify-between shadow-[0_12px_40px_rgba(0,0,0,0.6)] transition-all duration-200">
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold text-[#93C5FD] bg-[rgba(59,130,246,0.15)] px-3 py-1 rounded-lg border border-[rgba(59,130,246,0.3)]">
              <HelpCircle size={14} /> QUESTION
            </span>
            <span className="text-xs text-[#A1A1AA] flex items-center gap-1.5 font-mono">
              <span>Click to flip</span>
              <RotateCw size={12} />
            </span>
          </div>

          <div className="my-auto text-center px-1 sm:px-4 overflow-y-auto max-h-48">
            <p className="text-lg sm:text-xl md:text-2xl font-semibold text-white leading-relaxed tracking-tight">
              {card?.question}
            </p>
          </div>

          <div className="flex justify-between items-center gap-4 text-[11px] text-[#A1A1AA] font-mono border-t border-[rgba(255,255,255,0.08)] pt-3.5">
            <span className="truncate">{frontFooter}</span>
            <span className="flex-shrink-0">{number}</span>
          </div>
        </div>

        {/* Back face: Answer (Frosted Glass Floating Card with green tint) */}
        <div className="absolute inset-0 w-full h-full [backface-visibility:hidden] [transform:rotateY(180deg)] bg-[rgba(255,255,255,0.05)] backdrop-blur-2xl border border-[rgba(52,211,153,0.35)] group-hover:bg-[rgba(255,255,255,0.08)] group-hover:border-[rgba(52,211,153,0.5)] group-hover:shadow-[0_0_35px_rgba(52,211,153,0.18)] rounded-3xl p-5 sm:p-8 md:p-10 flex flex-col justify-between shadow-[0_12px_40px_rgba(0,0,0,0.6)] transition-all duration-200">
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold text-[#34D399] bg-[rgba(52,211,153,0.18)] px-3 py-1 rounded-lg border border-[rgba(52,211,153,0.3)]">
              <CheckCircle2 size={14} /> ANSWER
            </span>
            <span className="text-xs text-[#A1A1AA] flex items-center gap-1.5 font-mono">
              <span>Click to flip back</span>
              <RotateCw size={12} />
            </span>
          </div>

          <div className="my-auto text-center px-1 sm:px-4 overflow-y-auto max-h-48">
            <p className="text-base sm:text-lg md:text-xl text-white leading-relaxed font-normal">
              {card?.answer}
            </p>
          </div>

          <div className="flex justify-between items-center gap-4 text-[11px] text-[#A1A1AA] font-mono border-t border-[rgba(255,255,255,0.08)] pt-3.5">
            {card?.source_label ? (
              card.source_url ? (
                <a
                  href={card.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  tabIndex={isFlipped ? 0 : -1}
                  className="inline-flex items-center gap-1.5 min-w-0 text-[#34D399] hover:text-[#6EE7B7] hover:underline transition-colors"
                  title={`Open the source: ${card.source_url}`}
                >
                  <span className="truncate">Source: {card.source_label}</span>
                  <ExternalLink size={11} className="flex-shrink-0" />
                </a>
              ) : (
                <span className="truncate text-[#34D399]">Source: {card.source_label}</span>
              )
            ) : (
              <span className="text-[#34D399]">Concept Mastered</span>
            )}
            <span className="flex-shrink-0">{number}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
