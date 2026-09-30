import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getDocuments,
  deleteDocument,
  renameDocument,
  listMergedSets,
  createMergedSet,
  renameMergedSet,
  deleteMergedSet,
} from '../api/client'
import type { DocumentItem, MergedSet } from '../types'
import { useDocuments } from '../context/DocumentContext'
import { UploadZone } from '../components/library/UploadZone'
import { DocumentCard } from '../components/library/DocumentCard'
import { DocumentNameEditor } from '../components/library/DocumentNameEditor'
import { MergedSetCard } from '../components/library/MergedSetCard'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import {
  Library as LibraryIcon,
  Plus,
  Search,
  RefreshCw,
  LayoutGrid,
  List,
  Trash2,
  Pencil,
  CheckSquare,
  X,
  Layers,
} from 'lucide-react'

// Same limits as the backend (app/routes/merged_sets.py), which also caps the
// total text (MERGED_MAX_CHARS, default 300,000 characters) and explains when a selection is over it.
const MIN_MERGED = 2
const MAX_MERGED = 8

export function LibraryPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [showUpload, setShowUpload] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards')
  const [renamingId, setRenamingId] = useState<number | null>(null)
  const [mergedSets, setMergedSets] = useState<MergedSet[]>([])
  const [setsError, setSetsError] = useState<string | null>(null)
  // Selection mode: picking documents for a merged set, in the order they're picked.
  const [selecting, setSelecting] = useState(false)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const navigate = useNavigate()
  const { refreshDocuments } = useDocuments()

  const fetchMergedSets = async () => {
    try {
      setMergedSets(await listMergedSets())
      setSetsError(null)
    } catch (err) {
      setSetsError(err instanceof Error ? err.message : 'Failed to load merged sets')
    }
  }

  const fetchDocuments = async () => {
    setIsLoading(true)
    setError(null)
    fetchMergedSets()
    try {
      const docs = await getDocuments()
      setDocuments(docs)
    } catch (err) {
      setError('Failed to load documents. Please check your connection or try again.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleDeleteDocument = async (doc: DocumentItem) => {
    try {
      await deleteDocument(doc.id)
      setDocuments((prev) => prev.filter((d) => d.id !== doc.id))
      // Sets that contained it lose that member and may now be out of date.
      fetchMergedSets()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete document')
    }
  }

  // Throws on failure so the name editor can show the message and stay open.
  const handleRenameDocument = async (doc: DocumentItem, name: string) => {
    const renamed = await renameDocument(doc.id, name)
    setDocuments((prev) => prev.map((d) => (d.id === doc.id ? { ...d, filename: renamed.filename } : d)))
    // The sidebar reads the shared list, which is a separate copy.
    refreshDocuments().catch(() => {})
    fetchMergedSets()
  }

  const handleRenameSet = async (set: MergedSet, name: string) => {
    const renamed = await renameMergedSet(set.id, name)
    setMergedSets((prev) => prev.map((s) => (s.id === set.id ? renamed : s)))
  }

  const handleDeleteSet = async (set: MergedSet) => {
    try {
      await deleteMergedSet(set.id)
      setMergedSets((prev) => prev.filter((s) => s.id !== set.id))
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete merged set')
    }
  }

  const startSelecting = () => {
    setSelecting(true)
    setShowUpload(false)
    setRenamingId(null)
  }

  const stopSelecting = () => {
    setSelecting(false)
    setSelectedIds([])
    setCreateError(null)
  }

  const toggleSelected = (id: number) => {
    setCreateError(null)
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= MAX_MERGED ? prev : [...prev, id]
    )
  }

  const handleCreateSet = async () => {
    if (selectedIds.length < MIN_MERGED || isCreating) return
    setIsCreating(true)
    setCreateError(null)
    try {
      const res = await createMergedSet(selectedIds)
      stopSelecting()
      navigate(`/library/merged/${res.merged_set.id}/summary`, { state: { reopened: !res.created } })
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create merged set')
    } finally {
      setIsCreating(false)
    }
  }

  useEffect(() => {
    fetchDocuments()
  }, [])

  // Escape leaves selection mode.
  useEffect(() => {
    if (!selecting) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') stopSelecting()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selecting])

  const handleUploadSuccess = (info?: { keepOpen: boolean }) => {
    // Per-file results or a merge prompt stay on screen, so the panel stays open for them.
    if (!info?.keepOpen) setShowUpload(false)
    fetchDocuments()
  }

  const query = searchQuery.toLowerCase()
  const filteredDocs = documents.filter((doc) =>
    doc.filename.toLowerCase().includes(query)
  )
  const filteredSets = mergedSets.filter(
    (s) => s.name.toLowerCase().includes(query) || s.documents.some((d) => d.filename.toLowerCase().includes(query))
  )
  const showSets = !selecting && !error && filteredSets.length > 0
  const selectionHint =
    selectedIds.length < MIN_MERGED
      ? `Pick at least ${MIN_MERGED}`
      : selectedIds.length >= MAX_MERGED
        ? `${MAX_MERGED} is the most a set can have`
        : ''

  return (
    <div className="relative flex flex-col w-full max-w-6xl mx-auto animate-fade-in pb-16 min-w-0">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-3 mb-1.5">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#3B82F6]/20 to-[#1D4ED8]/20 border border-[rgba(59,130,246,0.35)] flex items-center justify-center text-[#93C5FD] shadow-[0_0_15px_rgba(59,130,246,0.2)]">
              <LibraryIcon size={20} />
            </div>
            <h1 className="text-3xl font-bold text-white tracking-tight">Document Library</h1>
          </div>
          <p className="text-sm text-[#A1A1AA]">
            Explore your study materials, generated revision summaries, and active flashcard decks.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {documents.length >= MIN_MERGED && !error && (
            <button
              onClick={selecting ? stopSelecting : startSelecting}
              aria-pressed={selecting}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold border transition-all duration-200 ${
                selecting
                  ? 'border-[rgba(255,255,255,0.15)] bg-[rgba(255,255,255,0.06)] text-white hover:bg-[rgba(255,255,255,0.1)]'
                  : 'border-[rgba(167,139,250,0.35)] bg-[rgba(167,139,250,0.1)] text-[#C4B5FD] hover:bg-[rgba(167,139,250,0.18)] hover:text-white'
              }`}
              title={selecting ? 'Stop selecting (Esc)' : 'Select documents to study together as a merged set'}
            >
              {selecting ? <><X size={15} /> Cancel</> : <><CheckSquare size={15} /> Select</>}
            </button>
          )}
          <button
            onClick={fetchDocuments}
            disabled={isLoading}
            className="p-2.5 rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] text-[#A1A1AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)] hover:border-[rgba(59,130,246,0.3)] transition-all duration-200 disabled:opacity-50"
            aria-label="Refresh library"
            title="Refresh library"
          >
            <RefreshCw size={17} className={isLoading ? 'animate-spin' : ''} />
          </button>
          {!selecting && (
            <button
              onClick={() => setShowUpload(!showUpload)}
              className="flex items-center gap-2 bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white px-5 py-2.5 rounded-xl text-xs font-semibold transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110"
            >
              {showUpload ? 'Cancel' : <><Plus size={16} /> Add Material</>}
            </button>
          )}
        </div>
      </div>

      {showUpload && (
        <div className="mb-10 animate-fade-in">
          <UploadZone onUploadSuccess={handleUploadSuccess} onMergedSetCreated={() => fetchMergedSets()} />
        </div>
      )}

      {selecting && (
        <div className="mb-6 p-4 rounded-2xl flex items-start gap-3 text-xs text-[#DDD6FE] bg-[rgba(167,139,250,0.1)] border border-[rgba(167,139,250,0.3)] animate-fade-in">
          <Layers size={16} className="flex-shrink-0 mt-px text-[#C4B5FD]" />
          <p>
            Pick {MIN_MERGED}–{MAX_MERGED} documents of any type to study together. The merged set gets its own
            summary and flashcard deck; each document's own summary and flashcards stay as they are.
          </p>
        </div>
      )}

      {/* Search & View Mode Bar */}
      {documents.length > 0 && !error && (
        <div className="mb-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="relative w-full max-w-md">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[#5C5C6E]">
              <Search size={16} />
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter by name..."
              className="w-full bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-[#5C5C6E] focus:outline-none focus:border-[rgba(59,130,246,0.4)] focus:shadow-[0_0_20px_rgba(59,130,246,0.1)] transition-all duration-200"
            />
          </div>

          <div className="flex items-center gap-1 bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] p-1 rounded-xl self-end sm:self-auto">
            <button
              onClick={() => setViewMode('cards')}
              className={`p-2 rounded-lg transition-all duration-200 ${
                viewMode === 'cards'
                  ? 'bg-[rgba(255,255,255,0.1)] text-white shadow-sm'
                  : 'text-[#5C5C6E] hover:text-white'
              }`}
              title="Card View"
              aria-label="Card View"
            >
              <LayoutGrid size={16} />
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`p-2 rounded-lg transition-all duration-200 ${
                viewMode === 'table'
                  ? 'bg-[rgba(255,255,255,0.1)] text-white shadow-sm'
                  : 'text-[#5C5C6E] hover:text-white'
              }`}
              title="Table View"
              aria-label="Table View"
            >
              <List size={16} />
            </button>
          </div>
        </div>
      )}

      {showSets && (
        <section className="mb-10" aria-labelledby="merged-sets-heading">
          <h2 id="merged-sets-heading" className="flex items-center gap-2 text-sm font-semibold text-white mb-4">
            <Layers size={16} className="text-[#C4B5FD]" />
            Merged sets
            <span className="text-xs font-mono font-normal text-[#71717A]">{filteredSets.length}</span>
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {filteredSets.map((set) => (
              <MergedSetCard
                key={set.id}
                set={set}
                onOpenSummary={(s) => navigate(`/library/merged/${s.id}/summary`)}
                onOpenFlashcards={(s) => navigate(`/library/merged/${s.id}/flashcards`)}
                onRename={handleRenameSet}
                onDelete={handleDeleteSet}
              />
            ))}
          </div>
        </section>
      )}
      {setsError && !selecting && !error && (
        <p className="mb-6 text-xs text-[#F87171]" role="alert">Couldn't load merged sets: {setsError}</p>
      )}

      {(showSets || selecting) && documents.length > 0 && !error && (
        <h2 className="flex items-center gap-2 text-sm font-semibold text-white mb-4">
          <LibraryIcon size={16} className="text-[#93C5FD]" />
          Documents
        </h2>
      )}

      {/* Content Area */}
      {isLoading && documents.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center min-h-[300px] py-20">
          <LoadingSpinner size={40} className="mb-4 text-[var(--accent-primary)]" />
          <p className="text-[var(--text-secondary)] text-sm">Loading your documents...</p>
        </div>
      ) : error ? (
        <div className="p-8 bg-red-500/10 border border-red-500/20 text-red-400 rounded-2xl text-center max-w-lg mx-auto my-12">
          <h3 className="font-semibold mb-2 text-base">Error loading library</h3>
          <p className="text-sm opacity-90 mb-4">{error}</p>
          <button
            onClick={fetchDocuments}
            className="px-5 py-2 bg-red-500/20 hover:bg-red-500/30 text-white rounded-xl text-xs font-semibold transition-colors"
          >
            Try Again
          </button>
        </div>
      ) : documents.length === 0 ? (
        <EmptyState
          icon={<LibraryIcon size={36} />}
          title="Your library is empty"
          description="Upload your first PDF, PowerPoint, Word document, or YouTube video to build your study library."
          action={
            <button
              onClick={() => setShowUpload(true)}
              className="mt-4 px-5 py-2.5 rounded-xl bg-[var(--accent-primary)] text-white text-xs font-semibold hover:bg-[var(--accent-primary-hover)] transition-all shadow-sm"
            >
              Add your first material
            </button>
          }
        />
      ) : viewMode === 'cards' ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {filteredDocs.length > 0 ? (
            filteredDocs.map((doc) => (
              <DocumentCard
                key={doc.id}
                document={doc}
                onClick={() => navigate(`/library/${doc.id}/summary`)}
                onOpenSummary={() => navigate(`/library/${doc.id}/summary`)}
                onOpenFlashcards={() => navigate(`/library/${doc.id}/flashcards`)}
                onDelete={handleDeleteDocument}
                onRename={handleRenameDocument}
                selectable={selecting}
                selected={selectedIds.includes(doc.id)}
                onToggleSelect={() => toggleSelected(doc.id)}
              />
            ))
          ) : (
            <div className="col-span-full p-12 text-center text-[#A1A1AA] text-sm bg-[rgba(255,255,255,0.03)] backdrop-blur-md border border-[rgba(255,255,255,0.08)] rounded-2xl">
              No documents match your search "{searchQuery}".
            </div>
          )}
        </div>
      ) : (
        <div className="bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] rounded-2xl overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.5)] animate-fade-in">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-[rgba(255,255,255,0.08)] text-[#A1A1AA] text-xs uppercase tracking-wider bg-[rgba(255,255,255,0.04)]">
                  {selecting && (
                    <th className="pl-6 py-4 font-semibold">
                      <span className="sr-only">Selected</span>
                    </th>
                  )}
                  <th className="px-6 py-4 font-semibold w-full">Document Name</th>
                  <th className="px-6 py-4 font-semibold whitespace-nowrap">Chunks</th>
                  <th className="px-6 py-4 font-semibold whitespace-nowrap">Status</th>
                  {!selecting && <th className="px-6 py-4 font-semibold whitespace-nowrap text-right">Study Tools</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgba(255,255,255,0.06)]">
                {filteredDocs.length > 0 ? (
                  filteredDocs.map((doc) => (
                    <tr
                      key={doc.id}
                      onClick={
                        selecting
                          ? () => toggleSelected(doc.id)
                          : renamingId === doc.id
                            ? undefined
                            : () => navigate(`/library/${doc.id}/summary`)
                      }
                      className={`group transition-colors duration-200 cursor-pointer ${
                        selecting && selectedIds.includes(doc.id)
                          ? 'bg-[rgba(59,130,246,0.1)] hover:bg-[rgba(59,130,246,0.14)]'
                          : 'hover:bg-[rgba(255,255,255,0.05)]'
                      }`}
                    >
                      {selecting && (
                        <td className="pl-6 py-4" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selectedIds.includes(doc.id)}
                            onChange={() => toggleSelected(doc.id)}
                            aria-label={`Select ${doc.filename}`}
                            className="w-4 h-4 accent-[#3B82F6] cursor-pointer"
                          />
                        </td>
                      )}
                      <td className="px-6 py-4">
                        {renamingId === doc.id ? (
                          <DocumentNameEditor
                            initialName={doc.filename}
                            onSave={(name) => handleRenameDocument(doc, name)}
                            onDone={() => setRenamingId(null)}
                            className="max-w-[200px] md:max-w-[400px]"
                          />
                        ) : (
                          <span
                            className="font-medium text-sm text-white truncate max-w-[200px] md:max-w-[400px] block group-hover:text-[#93C5FD] transition-colors duration-200"
                            title={doc.filename}
                          >
                            {doc.filename}
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-sm text-[#A1A1AA] whitespace-nowrap font-mono">
                        {doc.total_chunks} chunks
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {doc.total_chunks > 0 ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-mono font-medium bg-[rgba(52,211,153,0.15)] text-[#34D399] border border-[rgba(52,211,153,0.25)]">
                            Indexed
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-mono font-medium bg-[rgba(251,191,36,0.15)] text-[#FBBF24] border border-[rgba(251,191,36,0.3)]">
                            No content indexed
                          </span>
                        )}
                      </td>
                      {!selecting && (
                      <td className="px-6 py-4 whitespace-nowrap text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => navigate(`/library/${doc.id}/summary`)}
                            className="px-3.5 py-1 rounded-full text-xs font-medium bg-[rgba(59,130,246,0.12)] text-[#93C5FD] hover:bg-gradient-to-r hover:from-[#3B82F6] hover:to-[#1D4ED8] hover:text-white border border-[rgba(59,130,246,0.25)] hover:shadow-[0_0_15px_rgba(59,130,246,0.3)] transition-all duration-200"
                          >
                            Summary
                          </button>
                          <button
                            onClick={() => navigate(`/library/${doc.id}/flashcards`)}
                            className="px-3.5 py-1 rounded-full text-xs font-medium bg-[rgba(59,130,246,0.12)] text-[#93C5FD] hover:bg-gradient-to-r hover:from-[#3B82F6] hover:to-[#1D4ED8] hover:text-white border border-[rgba(59,130,246,0.25)] hover:shadow-[0_0_15px_rgba(59,130,246,0.3)] transition-all duration-200"
                          >
                            Flashcards
                          </button>
                          <button
                            onClick={() => setRenamingId(doc.id)}
                            disabled={renamingId === doc.id}
                            className="p-1.5 rounded-full text-[#71717A] hover:text-[#93C5FD] hover:bg-[rgba(59,130,246,0.12)] border border-transparent hover:border-[rgba(59,130,246,0.3)] transition-all duration-200 ml-1 disabled:opacity-40 disabled:pointer-events-none"
                            title="Rename this document"
                            aria-label="Rename document"
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            onClick={() => {
                              if (window.confirm('Delete this document and all its summaries/flashcards? This cannot be undone.')) {
                                handleDeleteDocument(doc)
                              }
                            }}
                            className="p-1.5 rounded-full text-[#71717A] hover:text-[#F87171] hover:bg-[rgba(239,68,68,0.15)] border border-transparent hover:border-[rgba(239,68,68,0.3)] transition-all duration-200 ml-1"
                            title="Delete this document"
                            aria-label="Delete document"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                      )}
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="px-6 py-12 text-center text-[#A1A1AA] text-sm">
                      No documents match your search "{searchQuery}".
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Selection bar: stays in view at the bottom while picking documents */}
      {selecting && (
        <div className="sticky bottom-4 z-20 mt-8 animate-fade-in">
          <div
            role="region"
            aria-label="Merged set selection"
            className="mx-auto max-w-2xl flex flex-wrap items-center justify-between gap-3 px-4 sm:px-5 py-3.5 rounded-2xl bg-[rgba(17,17,27,0.92)] backdrop-blur-xl border border-[rgba(167,139,250,0.4)] shadow-[0_12px_40px_rgba(0,0,0,0.6)]"
          >
            <p className="text-xs text-[#D1D5DB]" aria-live="polite">
              <span className="font-semibold text-white">{selectedIds.length} selected</span>
              {selectionHint && <span className="text-[#A1A1AA]"> · {selectionHint}</span>}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  setSelectedIds([])
                  setCreateError(null)
                }}
                disabled={selectedIds.length === 0 || isCreating}
                className="px-3.5 py-2 rounded-xl text-xs font-medium text-[#A1A1AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)] disabled:opacity-40 disabled:pointer-events-none transition-all duration-200"
              >
                Clear
              </button>
              <button
                onClick={handleCreateSet}
                disabled={selectedIds.length < MIN_MERGED || isCreating}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-[#8B5CF6] to-[#6D28D9] shadow-[0_0_20px_rgba(139,92,246,0.35)] hover:brightness-110 disabled:opacity-40 disabled:shadow-none disabled:cursor-not-allowed transition-all duration-200"
              >
                {isCreating ? <LoadingSpinner size={14} /> : <Layers size={14} />}
                <span>{isCreating ? 'Creating…' : 'Create merged set'}</span>
              </button>
            </div>
            {createError && (
              <p role="alert" className="w-full text-xs text-[#F87171]">{createError}</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
