import { useState } from 'react'
import { BookOpen, Layers, ListChecks, Pencil, Trash2, AlertTriangle } from 'lucide-react'
import type { MergedSet } from '../../types'
import { DocumentNameEditor } from './DocumentNameEditor'
import { sourceBadge } from './sourceBadge'

interface MergedSetCardProps {
  set: MergedSet
  onOpenSummary: (set: MergedSet) => void
  onOpenFlashcards: (set: MergedSet) => void
  onOpenQuiz: (set: MergedSet) => void
  onRename: (set: MergedSet, name: string) => Promise<void>
  onDelete: (set: MergedSet) => void
}

export function MergedSetCard({ set, onOpenSummary, onOpenFlashcards, onOpenQuiz, onRename, onDelete }: MergedSetCardProps) {
  const [isRenaming, setIsRenaming] = useState(false)
  const types = [...new Set(set.documents.map((d) => d.source_type || 'pdf'))]
  const stale = set.summary_stale || set.flashcards_stale

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (window.confirm(
      `Delete the merged set "${set.name}" and its merged summary and flashcards? ` +
      'Its documents, and their own summaries and flashcards, are not affected.'
    )) {
      onDelete(set)
    }
  }

  return (
    <div
      onClick={isRenaming ? undefined : () => onOpenSummary(set)}
      style={{
        background: 'linear-gradient(135deg, rgba(167, 139, 250, 0.07) 0%, rgba(255, 255, 255, 0.015) 100%)',
      }}
      className="group @container p-6 rounded-2xl backdrop-blur-xl border border-[rgba(167,139,250,0.2)] hover:border-[rgba(167,139,250,0.45)] hover:shadow-[0_0_28px_rgba(167,139,250,0.15)] transition-all duration-300 cursor-pointer relative overflow-hidden"
    >
      <div className="flex flex-col @2xl:flex-row @2xl:items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <div className="w-12 h-12 rounded-2xl bg-[rgba(167,139,250,0.15)] border border-[rgba(255,255,255,0.05)] flex items-center justify-center flex-shrink-0 text-[#C4B5FD] group-hover:scale-105 transition-all duration-200">
            <Layers size={22} />
          </div>
          <div className="min-w-0 flex-1">
            {isRenaming ? (
              <DocumentNameEditor
                initialName={set.name}
                onSave={(name) => onRename(set, name)}
                onDone={() => setIsRenaming(false)}
              />
            ) : (
              <h4
                className="text-sm font-semibold text-white truncate group-hover:text-[#C4B5FD] transition-colors duration-200"
                title={`${set.name}\n\n${set.documents.map((d, i) => `${i + 1}. ${d.filename}`).join('\n')}`}
              >
                {set.name}
              </h4>
            )}
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-md border text-[#C4B5FD] bg-[rgba(167,139,250,0.2)] border-[rgba(167,139,250,0.3)]">
                MERGED
              </span>
              <span className="text-xs text-[#A1A1AA] font-mono">{set.documents.length} {set.documents.length === 1 ? 'source' : 'sources'}</span>
              <span className="flex items-center gap-1" aria-label={`Source types: ${types.join(', ')}`}>
                {types.map((t) => (
                  <span key={t} title={sourceBadge(t).label}>{sourceBadge(t, 12).icon}</span>
                ))}
              </span>
              {stale && (
                <span
                  className="inline-flex items-center gap-1 text-[10px] font-mono font-medium text-[#FBBF24] bg-[rgba(251,191,36,0.15)] border border-[rgba(251,191,36,0.3)] px-2 py-0.5 rounded-md"
                  title="A document in this set was deleted after its summary or flashcards were made"
                >
                  <AlertTriangle size={10} /> Out of date
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 self-end @2xl:self-center" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => onOpenSummary(set)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-full bg-[rgba(59,130,246,0.12)] text-[#93C5FD] border border-[rgba(59,130,246,0.25)] hover:bg-gradient-to-r hover:from-[#3B82F6] hover:to-[#1D4ED8] hover:text-white hover:shadow-[0_0_16px_rgba(59,130,246,0.3)] transition-all duration-200"
            title="Merged summary of all the documents"
          >
            <BookOpen size={13} />
            <span>Summary</span>
          </button>
          <button
            onClick={() => onOpenFlashcards(set)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-full bg-[rgba(59,130,246,0.12)] text-[#93C5FD] border border-[rgba(59,130,246,0.25)] hover:bg-gradient-to-r hover:from-[#3B82F6] hover:to-[#1D4ED8] hover:text-white hover:shadow-[0_0_16px_rgba(59,130,246,0.3)] transition-all duration-200"
            title="Merged flashcard deck"
          >
            <Layers size={13} />
            <span>Flashcards</span>
          </button>
          <button
            onClick={() => onOpenQuiz(set)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-full bg-[rgba(59,130,246,0.12)] text-[#93C5FD] border border-[rgba(59,130,246,0.25)] hover:bg-gradient-to-r hover:from-[#3B82F6] hover:to-[#1D4ED8] hover:text-white hover:shadow-[0_0_16px_rgba(59,130,246,0.3)] transition-all duration-200"
            title="Quiz on all the documents"
          >
            <ListChecks size={13} />
            <span>Quiz</span>
          </button>
          <div className="flex items-center gap-2 ml-1">
            <button
              onClick={() => setIsRenaming(true)}
              disabled={isRenaming}
              className="flex items-center justify-center w-8 h-8 rounded-full bg-[rgba(255,255,255,0.03)] text-[#71717A] border border-[rgba(255,255,255,0.08)] hover:bg-[rgba(59,130,246,0.12)] hover:text-[#93C5FD] hover:border-[rgba(59,130,246,0.3)] transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none"
              title="Rename this merged set"
              aria-label="Rename merged set"
            >
              <Pencil size={13} />
            </button>
            <button
              onClick={handleDelete}
              className="flex items-center justify-center w-8 h-8 rounded-full bg-[rgba(255,255,255,0.03)] text-[#71717A] border border-[rgba(255,255,255,0.08)] hover:bg-[rgba(239,68,68,0.15)] hover:text-[#F87171] hover:border-[rgba(239,68,68,0.3)] hover:shadow-[0_0_14px_rgba(239,68,68,0.25)] transition-all duration-200"
              title="Delete this merged set (its documents are kept)"
              aria-label="Delete merged set"
            >
              <Trash2 size={13} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
