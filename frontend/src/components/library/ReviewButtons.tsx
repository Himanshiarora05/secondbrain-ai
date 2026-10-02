import type { ReviewGrade } from '../../types'

const GRADES: { grade: ReviewGrade; label: string; hint: string; style: string }[] = [
  {
    grade: 'again',
    label: 'Again',
    hint: 'Forgot it: see it again today',
    style: 'text-[#F87171] bg-[rgba(248,113,113,0.1)] border-[rgba(248,113,113,0.3)] hover:bg-[rgba(248,113,113,0.2)]',
  },
  {
    grade: 'good',
    label: 'Good',
    hint: 'Remembered it',
    style: 'text-[#93C5FD] bg-[rgba(59,130,246,0.1)] border-[rgba(59,130,246,0.3)] hover:bg-[rgba(59,130,246,0.2)]',
  },
  {
    grade: 'easy',
    label: 'Easy',
    hint: 'Knew it instantly: wait longer',
    style: 'text-[#34D399] bg-[rgba(52,211,153,0.1)] border-[rgba(52,211,153,0.3)] hover:bg-[rgba(52,211,153,0.2)]',
  },
]

interface ReviewButtonsProps {
  onRate: (grade: ReviewGrade) => void
  disabled?: boolean
}

export function ReviewButtons({ onRate, disabled = false }: ReviewButtonsProps) {
  return (
    <div className="flex flex-col items-center gap-2">
      <span className="text-[11px] text-[#A1A1AA] font-mono">How well did you know it?</span>
      <div className="flex items-center justify-center gap-3">
        {GRADES.map(({ grade, label, hint, style }, i) => (
          <button
            key={grade}
            onClick={() => onRate(grade)}
            disabled={disabled}
            title={`${hint} (key ${i + 1})`}
            className={`min-w-[88px] px-5 py-2.5 rounded-xl border text-xs font-semibold transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed ${style}`}
          >
            {label}
            <span className="ml-1.5 font-mono text-[10px] opacity-60">{i + 1}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
