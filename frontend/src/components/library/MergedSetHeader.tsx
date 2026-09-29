import { Link } from 'react-router-dom'
import { AlertTriangle, Info } from 'lucide-react'
import type { MergedSet } from '../../types'
import { sourceBadge } from './sourceBadge'

// Member list shown under a merged set's title on its summary and flashcard pages.
export function MergedSetMembers({ set, page }: { set: MergedSet; page: 'summary' | 'flashcards' }) {
  return (
    <ol className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Documents in this set">
      {set.documents.map((doc, i) => {
        const badge = sourceBadge(doc.source_type, 11)
        return (
          <li key={doc.id} className="min-w-0 max-w-full">
            <Link
              to={`/library/${doc.id}/${page}`}
              className="inline-flex items-center gap-1.5 max-w-[16rem] px-2 py-1 rounded-lg text-[11px] text-[#D1D5DB] bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.08)] hover:border-[rgba(59,130,246,0.35)] hover:text-white transition-colors"
              title={`Source ${i + 1}: ${doc.filename} (open its own ${page})`}
            >
              <span className="font-mono text-[#71717A]">{i + 1}</span>
              {badge.icon}
              <span className="truncate">{doc.filename}</span>
            </Link>
          </li>
        )
      })}
    </ol>
  )
}

interface MergedSetNoticesProps {
  set: MergedSet
  // What was generated: 'summary' or 'deck'.
  what: 'summary' | 'deck'
  stale: boolean
  reopened: boolean
}

// Notices above a merged set's content: reopened instead of duplicated, stale after a deletion.
export function MergedSetNotices({ set, what, stale, reopened }: MergedSetNoticesProps) {
  const tooFew = set.documents.length < 2
  return (
    <>
      {reopened && (
        <div className="mb-4 p-3.5 rounded-2xl flex items-start gap-2.5 text-xs text-[#93C5FD] bg-[rgba(59,130,246,0.1)] border border-[rgba(59,130,246,0.25)]">
          <Info size={15} className="flex-shrink-0 mt-px" />
          <span>You already had a merged set with these documents, so it was opened instead of creating a copy.</span>
        </div>
      )}
      {(stale || tooFew) && (
        <div role="status" className="mb-4 p-3.5 rounded-2xl flex items-start gap-2.5 text-xs text-[#FBBF24] bg-[rgba(251,191,36,0.1)] border border-[rgba(251,191,36,0.3)]">
          <AlertTriangle size={15} className="flex-shrink-0 mt-px" />
          <span>
            {tooFew
              ? `Only ${set.documents.length === 1 ? 'one document is' : 'no documents are'} left in this set, so it can't be regenerated. Create a new set from the Library.`
              : `A document in this set was deleted after this ${what} was made, so some citations point to a source that's no longer in the set. Regenerate to update it.`}
          </span>
        </div>
      )}
    </>
  )
}
