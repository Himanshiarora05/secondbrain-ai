import { useState } from 'react'
import { FileText, BookOpen, Layers, Presentation, FileEdit, Video, Globe, Trash2, Pencil, Check } from 'lucide-react'
import type { DocumentItem } from '../../types'
import { DocumentNameEditor } from './DocumentNameEditor'

interface DocumentCardProps {
  document: DocumentItem
  onOpenSummary?: (doc: DocumentItem) => void
  onOpenFlashcards?: (doc: DocumentItem) => void
  onDelete?: (doc: DocumentItem) => void
  onRename?: (doc: DocumentItem, name: string) => Promise<void>
  onClick?: () => void
  // Selection mode (picking documents for a merged set): the whole card is a
  // checkbox and its action buttons are hidden.
  selectable?: boolean
  selected?: boolean
  onToggleSelect?: () => void
  // Set when the card can't be picked (e.g. too long to merge): shown on the card, which ignores clicks.
  unselectableReason?: string
}

export function DocumentCard({
  document,
  onOpenSummary,
  onOpenFlashcards,
  onDelete,
  onRename,
  onClick,
  selectable = false,
  selected = false,
  onToggleSelect,
  unselectableReason,
}: DocumentCardProps) {
  const [isRenaming, setIsRenaming] = useState(false)
  const blocked = selectable && !!unselectableReason
  const toggle = blocked ? undefined : onToggleSelect
  const selectProps = selectable
    ? {
        role: 'checkbox',
        'aria-checked': selected,
        'aria-disabled': blocked || undefined,
        'aria-label': blocked ? `${document.filename}: ${unselectableReason}` : `Select ${document.filename}`,
        title: blocked ? unselectableReason : undefined,
        tabIndex: 0,
        onKeyDown: (e: React.KeyboardEvent) => {
          if (e.key === ' ' || e.key === 'Enter') {
            e.preventDefault()
            toggle?.()
          }
        },
      }
    : {}
  const sourceType = (document.source_type || 'pdf').toLowerCase()

  const getSourceIconAndBadge = () => {
    switch (sourceType) {
      case 'pptx':
        return {
          icon: <Presentation size={22} className="text-[#FBBF24]" />,
          bgColor: 'bg-[rgba(251,191,36,0.15)]',
          badgeText: 'PPTX',
          badgeStyle: 'text-[#FBBF24] bg-[rgba(251,191,36,0.2)] border-[rgba(251,191,36,0.3)]',
        }
      case 'docx':
        return {
          icon: <FileEdit size={22} className="text-[#60A5FA]" />,
          bgColor: 'bg-[rgba(96,165,250,0.15)]',
          badgeText: 'DOCX',
          badgeStyle: 'text-[#60A5FA] bg-[rgba(96,165,250,0.2)] border-[rgba(96,165,250,0.3)]',
        }
      case 'youtube':
        return {
          icon: <Video size={22} className="text-[#F87171]" />,
          bgColor: 'bg-[rgba(248,113,113,0.15)]',
          badgeText: 'YOUTUBE',
          badgeStyle: 'text-[#F87171] bg-[rgba(248,113,113,0.2)] border-[rgba(248,113,113,0.3)]',
        }
      case 'website':
        return {
          icon: <Globe size={22} className="text-[#22D3EE]" />,
          bgColor: 'bg-[rgba(34,211,238,0.15)]',
          badgeText: 'WEB',
          badgeStyle: 'text-[#22D3EE] bg-[rgba(34,211,238,0.2)] border-[rgba(34,211,238,0.3)]',
        }
      case 'pdf':
      default:
        return {
          icon: <FileText size={22} className="text-[#FB7185]" />,
          bgColor: 'bg-[rgba(251,113,133,0.15)]',
          badgeText: 'PDF',
          badgeStyle: 'text-[#FB7185] bg-[rgba(251,113,133,0.2)] border-[rgba(251,113,133,0.3)]',
        }
    }
  }

  const { icon, bgColor, badgeText, badgeStyle } = getSourceIconAndBadge()

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    const confirmed = window.confirm(
      'Delete this document and all its summaries/flashcards? This cannot be undone.'
    )
    if (confirmed && onDelete) {
      onDelete(document)
    }
  }

  return (
    <div
      onClick={selectable ? toggle : isRenaming ? undefined : onClick}
      {...selectProps}
      style={{
        background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0.015) 100%)',
      }}
      className={`group @container p-6 rounded-2xl backdrop-blur-xl border transition-all duration-300 relative overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3B82F6] ${
        blocked
          ? 'opacity-50 cursor-not-allowed border-[rgba(255,255,255,0.08)]'
          : selected
            ? 'cursor-pointer hover:shadow-[0_0_28px_rgba(59,130,246,0.18)] border-[rgba(59,130,246,0.7)] bg-[rgba(59,130,246,0.08)] shadow-[0_0_24px_rgba(59,130,246,0.2)]'
            : 'cursor-pointer hover:shadow-[0_0_28px_rgba(59,130,246,0.18)] border-[rgba(255,255,255,0.08)] hover:border-[rgba(59,130,246,0.35)]'
      }`}
    >
      {/* Layout follows the card's own width, not the window's: in the two-column
          library a card is ~480px wide, and buttons beside the title left it ~80px. */}
      <div className="flex flex-col @2xl:flex-row @2xl:items-center justify-between gap-4">
      <div className="flex items-center gap-4 min-w-0">
        {selectable && (
          <span
            aria-hidden="true"
            className={`w-5 h-5 rounded-md border flex items-center justify-center flex-shrink-0 transition-colors ${
              selected ? 'bg-[#3B82F6] border-[#3B82F6] text-white' : 'border-[rgba(255,255,255,0.3)] bg-[rgba(255,255,255,0.03)]'
            }`}
          >
            {selected && <Check size={13} strokeWidth={3} />}
          </span>
        )}
        <div className={`w-12 h-12 rounded-2xl ${bgColor} border border-[rgba(255,255,255,0.05)] flex items-center justify-center flex-shrink-0 group-hover:scale-105 transition-all duration-200`}>
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          {isRenaming && onRename ? (
            <DocumentNameEditor
              initialName={document.filename}
              onSave={(name) => onRename(document, name)}
              onDone={() => setIsRenaming(false)}
            />
          ) : (
            <h4
              className="text-sm font-semibold text-white truncate group-hover:text-[#93C5FD] transition-colors duration-200"
              title={document.filename}
            >
              {document.filename}
            </h4>
          )}
          <div className="flex items-center gap-2.5 mt-1.5 flex-wrap">
            <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-md border ${badgeStyle}`}>
              {badgeText}
            </span>
            <span className="text-xs text-[#A1A1AA] font-mono">
              {document.total_chunks} chunks
            </span>
            <span className="text-[#5C5C6E]">•</span>
            {document.total_chunks > 0 ? (
              <span className="text-[10px] font-mono font-medium text-[#34D399] bg-[rgba(52,211,153,0.15)] border border-[rgba(52,211,153,0.25)] px-2 py-0.5 rounded-md">
                Indexed
              </span>
            ) : (
              <span className="text-[10px] font-mono font-medium text-[#FBBF24] bg-[rgba(251,191,36,0.15)] border border-[rgba(251,191,36,0.3)] px-2 py-0.5 rounded-md">
                No content indexed
              </span>
            )}
          </div>
          {blocked && <p className="mt-1.5 text-[11px] font-medium text-[#FBBF24]">{unselectableReason}</p>}
        </div>
      </div>

      {!selectable && (
      <div className="flex flex-wrap items-center justify-end gap-2 self-end @2xl:self-center" onClick={(e) => e.stopPropagation()}>
        {onOpenSummary && (
          <button
            onClick={() => onOpenSummary(document)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-full bg-[rgba(59,130,246,0.12)] text-[#93C5FD] border border-[rgba(59,130,246,0.25)] hover:bg-gradient-to-r hover:from-[#3B82F6] hover:to-[#1D4ED8] hover:text-white hover:shadow-[0_0_16px_rgba(59,130,246,0.3)] transition-all duration-200"
            title="View AI Exam Summary"
          >
            <BookOpen size={13} />
            <span>Summary</span>
          </button>
        )}

        {onOpenFlashcards && (
          <button
            onClick={() => onOpenFlashcards(document)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-full bg-[rgba(59,130,246,0.12)] text-[#93C5FD] border border-[rgba(59,130,246,0.25)] hover:bg-gradient-to-r hover:from-[#3B82F6] hover:to-[#1D4ED8] hover:text-white hover:shadow-[0_0_16px_rgba(59,130,246,0.3)] transition-all duration-200"
            title="Study with AI Flashcards"
          >
            <Layers size={13} />
            <span>Flashcards</span>
          </button>
        )}

        {/* Kept together so on a narrow card they wrap as a pair, not one by one. */}
        {(onRename || onDelete) && (
          <div className="flex items-center gap-2 ml-1">
            {onRename && (
              <button
                onClick={() => setIsRenaming(true)}
                disabled={isRenaming}
                className="flex items-center justify-center w-8 h-8 rounded-full bg-[rgba(255,255,255,0.03)] text-[#71717A] border border-[rgba(255,255,255,0.08)] hover:bg-[rgba(59,130,246,0.12)] hover:text-[#93C5FD] hover:border-[rgba(59,130,246,0.3)] transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none"
                title="Rename this document"
                aria-label="Rename document"
              >
                <Pencil size={13} />
              </button>
            )}

            {onDelete && (
              <button
                onClick={handleDelete}
                className="flex items-center justify-center w-8 h-8 rounded-full bg-[rgba(255,255,255,0.03)] text-[#71717A] border border-[rgba(255,255,255,0.08)] hover:bg-[rgba(239,68,68,0.15)] hover:text-[#F87171] hover:border-[rgba(239,68,68,0.3)] hover:shadow-[0_0_14px_rgba(239,68,68,0.25)] transition-all duration-200"
                title="Delete this document"
                aria-label="Delete document"
              >
                <Trash2 size={13} />
              </button>
            )}
          </div>
        )}
      </div>
      )}
      </div>
    </div>
  )
}

