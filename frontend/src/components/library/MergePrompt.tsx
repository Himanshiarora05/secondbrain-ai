import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Layers, X, Search, ArrowRight, AlertTriangle } from 'lucide-react'
import { createMergedSet } from '../../api/client'
import type { DocumentItem, MergedSet } from '../../types'
import { sourceBadge } from './sourceBadge'
import { LoadingSpinner } from '../ui/LoadingSpinner'

// Same limits as the backend (app/routes/merged_sets.py), which also caps the
// total text (MERGED_MAX_CHARS, default 300,000 characters) and explains when a selection is over it.
export const MIN_MERGED = 2
export const MAX_MERGED = 8
// A merged summary makes roughly one AI call per three chunks, so past this
// many chunks it takes a lot of calls (and of a free model's daily requests).
const LARGE_SELECTION_CHUNKS = 150
// Show the filter box once the list is longer than this.
const FILTER_FROM = 6

interface MergePromptProps {
  // The documents just uploaded, in upload order; they start out selected.
  newIds: number[]
  // The user's whole library (the new documents included), fetched after the upload.
  documents: DocumentItem[]
  onDismiss: () => void
  onCreated?: (set: MergedSet) => void
}

// Offered after an upload: make a merged set from the new document(s) and any
// existing ones, through the existing merged-sets API. It doesn't open the set
// (that would generate its summary); it shows a link to it instead.
export function MergePrompt({ newIds, documents, onDismiss, onCreated }: MergePromptProps) {
  const newDocs = newIds
    .map((id) => documents.find((d) => d.id === id))
    .filter((d): d is DocumentItem => d !== undefined)
  const others = documents.filter((d) => !newIds.includes(d.id))

  // Selected ids in order: new documents first (upload order), then picks in the order they're ticked.
  const [selected, setSelected] = useState<number[]>(() => newDocs.map((d) => d.id))
  // A single upload has to pick something first; a batch of 2–8 can merge straight away.
  const [picking, setPicking] = useState(false)
  const [filter, setFilter] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ set: MergedSet; created: boolean } | null>(null)

  const byId = new Map(documents.map((d) => [d.id, d]))
  const count = selected.length
  const chunks = selected.reduce((sum, id) => sum + (byId.get(id)?.total_chunks ?? 0), 0)
  const canCreate = count >= MIN_MERGED && count <= MAX_MERGED && !isCreating

  const toggle = (id: number) => {
    setError(null)
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= MAX_MERGED ? prev : [...prev, id]
    )
  }

  const handleCreate = async () => {
    if (!canCreate) return
    setIsCreating(true)
    setError(null)
    try {
      const res = await createMergedSet(selected)
      setResult({ set: res.merged_set, created: res.created })
      onCreated?.(res.merged_set)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create merged set')
    } finally {
      setIsCreating(false)
    }
  }

  const newLabel =
    newDocs.length === 1 ? <span className="text-[#E9D5FF]">{newDocs[0].filename}</span> : `these ${newDocs.length} documents`

  if (result) {
    return (
      <Panel onDismiss={onDismiss} label="Merged set created">
        <p className="text-sm font-semibold text-white">
          {result.created ? 'Merged set created: ' : 'You already have a merged set with these documents: '}
          <span className="text-[#E9D5FF]">{result.set.name}</span>
        </p>
        <p className="text-xs text-[#DDD6FE] mt-1">
          Nothing has been generated yet. Its summary and flashcards are made when you open them.
        </p>
        <div className="flex justify-end mt-3">
          <Link
            to={`/library/merged/${result.set.id}/summary`}
            state={{ reopened: !result.created }}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-[#8B5CF6] to-[#6D28D9] shadow-[0_0_20px_rgba(139,92,246,0.35)] hover:brightness-110 transition-all duration-200"
          >
            <span>Open merged set</span>
            <ArrowRight size={14} />
          </Link>
        </div>
      </Panel>
    )
  }

  const query = filter.trim().toLowerCase()
  const listed = [...newDocs, ...others].filter((d) => !query || d.filename.toLowerCase().includes(query))

  return (
    <Panel onDismiss={onDismiss} label="Merge into a merged set">
      <p className="text-sm font-semibold text-white">
        Merge {newLabel} {others.length > 0 ? 'with other documents ' : ''}into a merged set?
      </p>
      <p className="text-xs text-[#DDD6FE] mt-1">
        You'll get one summary and flashcard deck from all of them; each document keeps its own.
      </p>

      {picking && (
        <div className="mt-3">
          {newDocs.length + others.length > FILTER_FROM && (
            <div className="relative mb-2">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#71717A]" aria-hidden="true" />
              <input
                type="text"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter documents"
                aria-label="Filter documents"
                className="w-full bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.1)] rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-[#5C5C6E] focus:outline-none focus:border-[#8B5CF6] focus:ring-1 focus:ring-[#8B5CF6]"
              />
            </div>
          )}
          <ul className="max-h-64 overflow-y-auto space-y-1 pr-1" aria-label="Documents">
            {listed.map((d) => {
              const badge = sourceBadge(d.source_type, 12)
              const checked = selected.includes(d.id)
              const full = !checked && count >= MAX_MERGED
              return (
                <li key={d.id}>
                  <label
                    className={`flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-xs transition-colors ${
                      full ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer hover:bg-[rgba(255,255,255,0.05)]'
                    } ${checked ? 'bg-[rgba(167,139,250,0.12)]' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={full || isCreating}
                      onChange={() => toggle(d.id)}
                      className="accent-[#8B5CF6] flex-shrink-0"
                    />
                    <span className={`px-1.5 py-0.5 rounded-md text-[10px] font-bold flex-shrink-0 ${badge.style}`}>
                      {badge.label}
                    </span>
                    <span className="text-[#D1D5DB] truncate min-w-0 flex-1" title={d.filename}>
                      {d.filename}
                    </span>
                    {newIds.includes(d.id) && (
                      <span className="text-[10px] font-semibold text-[#C4B5FD] flex-shrink-0">New</span>
                    )}
                    <span className="text-[10px] text-[#71717A] font-mono flex-shrink-0">{d.total_chunks} chunks</span>
                  </label>
                </li>
              )
            })}
            {listed.length === 0 && <li className="px-2.5 py-2 text-xs text-[#71717A]">No documents match.</li>}
          </ul>
        </div>
      )}

      {(picking || count > MAX_MERGED) && (
        <p className="mt-2 text-xs text-[#DDD6FE]" aria-live="polite">
          {count} of {MAX_MERGED} selected
          {count < MIN_MERGED && ` · pick at least ${MIN_MERGED}`}
          {count > MAX_MERGED && ` · a merged set can have at most ${MAX_MERGED}; untick some`}
        </p>
      )}
      {chunks > LARGE_SELECTION_CHUNKS && count >= MIN_MERGED && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-[#FBBF24]">
          <AlertTriangle size={13} className="flex-shrink-0 mt-px" aria-hidden="true" />
          <span>
            Large selection ({chunks} chunks): its summary will take many AI calls, which can use up a free model's
            daily requests.
          </span>
        </p>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2 mt-3">
        <button
          onClick={onDismiss}
          disabled={isCreating}
          className="px-3.5 py-2 rounded-xl text-xs font-medium text-[#A1A1AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)] disabled:opacity-40 transition-all duration-200"
        >
          Not now
        </button>
        {!picking && (others.length > 0 || count > MAX_MERGED) && (
          <button
            onClick={() => setPicking(true)}
            className={`px-3.5 py-2 rounded-xl text-xs font-semibold transition-all duration-200 ${
              count >= MIN_MERGED
                ? 'text-[#DDD6FE] hover:text-white hover:bg-[rgba(255,255,255,0.06)]'
                : 'text-white bg-gradient-to-r from-[#8B5CF6] to-[#6D28D9] shadow-[0_0_20px_rgba(139,92,246,0.35)] hover:brightness-110'
            }`}
          >
            {newDocs.length > 1 && count <= MAX_MERGED ? 'Add other documents' : 'Choose documents'}
          </button>
        )}
        {(picking || count >= MIN_MERGED) && (
          <button
            onClick={handleCreate}
            disabled={!canCreate}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-[#8B5CF6] to-[#6D28D9] shadow-[0_0_20px_rgba(139,92,246,0.35)] hover:brightness-110 disabled:opacity-40 disabled:shadow-none disabled:cursor-not-allowed transition-all duration-200"
          >
            {isCreating ? <LoadingSpinner size={14} /> : <Layers size={14} />}
            <span>{isCreating ? 'Creating…' : 'Create merged set'}</span>
          </button>
        )}
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-[#F87171]">{error}</p>}
    </Panel>
  )
}

function Panel({ label, onDismiss, children }: { label: string; onDismiss: () => void; children: React.ReactNode }) {
  return (
    <div
      className="mt-5 p-4 rounded-2xl bg-[rgba(167,139,250,0.1)] border border-[rgba(167,139,250,0.3)] animate-fade-in text-left"
      role="group"
      aria-label={label}
    >
      <div className="flex items-start gap-3">
        <Layers size={17} className="flex-shrink-0 mt-0.5 text-[#C4B5FD]" aria-hidden="true" />
        <div className="min-w-0 flex-1">{children}</div>
        <button
          onClick={onDismiss}
          className="p-1 -m-1 rounded-lg text-[#71717A] hover:text-white hover:bg-[rgba(255,255,255,0.06)] transition-colors flex-shrink-0"
          aria-label="Close"
          title="Close"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  )
}
