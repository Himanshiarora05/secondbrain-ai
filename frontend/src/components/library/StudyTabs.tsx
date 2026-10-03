import { Link } from 'react-router-dom'
import { BookOpen, Layers, ListChecks } from 'lucide-react'

export type StudyPage = 'summary' | 'flashcards' | 'quiz'

const TABS: { page: StudyPage; label: string; icon: typeof BookOpen }[] = [
  { page: 'summary', label: 'Summary', icon: BookOpen },
  { page: 'flashcards', label: 'Flashcards', icon: Layers },
  { page: 'quiz', label: 'Quiz', icon: ListChecks },
]

interface StudyTabsProps {
  // The document id, or the set id with `merged`.
  id: number
  merged?: boolean
  current: StudyPage
}

// Switches between the summary, flashcard and quiz pages of the same document or merged set.
export function StudyTabs({ id, merged = false, current }: StudyTabsProps) {
  const base = merged ? `/library/merged/${id}` : `/library/${id}`
  return (
    <nav
      aria-label="Study modes"
      className="inline-flex items-center gap-1 p-1 rounded-xl bg-[rgba(255,255,255,0.03)] backdrop-blur-md border border-[rgba(255,255,255,0.08)]"
    >
      {TABS.map(({ page, label, icon: Icon }) => {
        const active = page === current
        return (
          <Link
            key={page}
            to={`${base}/${page}`}
            aria-current={active ? 'page' : undefined}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
              active
                ? 'bg-[rgba(59,130,246,0.15)] text-[#93C5FD] border border-[rgba(59,130,246,0.3)]'
                : 'text-[#A1A1AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)] border border-transparent'
            }`}
          >
            <Icon size={13} />
            <span>{label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
