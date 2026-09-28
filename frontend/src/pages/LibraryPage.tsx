import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDocuments, deleteDocument } from '../api/client'
import type { DocumentItem } from '../types'
import { UploadZone } from '../components/library/UploadZone'
import { DocumentCard } from '../components/library/DocumentCard'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { Library as LibraryIcon, Plus, Search, RefreshCw, LayoutGrid, List, Trash2 } from 'lucide-react'

export function LibraryPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [showUpload, setShowUpload] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards')

  const navigate = useNavigate()

  const fetchDocuments = async () => {
    setIsLoading(true)
    setError(null)
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
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete document')
    }
  }

  useEffect(() => {
    fetchDocuments()
  }, [])

  const handleUploadSuccess = () => {
    setShowUpload(false)
    fetchDocuments()
  }

  const filteredDocs = documents.filter((doc) =>
    doc.filename.toLowerCase().includes(searchQuery.toLowerCase())
  )

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
          <button
            onClick={fetchDocuments}
            disabled={isLoading}
            className="p-2.5 rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] text-[#A1A1AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)] hover:border-[rgba(59,130,246,0.3)] transition-all duration-200 disabled:opacity-50"
            aria-label="Refresh library"
            title="Refresh library"
          >
            <RefreshCw size={17} className={isLoading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => setShowUpload(!showUpload)}
            className="flex items-center gap-2 bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white px-5 py-2.5 rounded-xl text-xs font-semibold transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110"
          >
            {showUpload ? 'Cancel' : <><Plus size={16} /> Add Material</>}
          </button>
        </div>
      </div>

      {showUpload && (
        <div className="mb-10 animate-fade-in">
          <UploadZone onUploadSuccess={handleUploadSuccess} />
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
              placeholder="Filter by filename..."
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
                  <th className="px-6 py-4 font-semibold w-full">Document Name</th>
                  <th className="px-6 py-4 font-semibold whitespace-nowrap">Chunks</th>
                  <th className="px-6 py-4 font-semibold whitespace-nowrap">Status</th>
                  <th className="px-6 py-4 font-semibold whitespace-nowrap text-right">Study Tools</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgba(255,255,255,0.06)]">
                {filteredDocs.length > 0 ? (
                  filteredDocs.map((doc) => (
                    <tr
                      key={doc.id}
                      onClick={() => navigate(`/library/${doc.id}/summary`)}
                      className="group hover:bg-[rgba(255,255,255,0.05)] transition-colors duration-200 cursor-pointer"
                    >
                      <td className="px-6 py-4">
                        <span
                          className="font-medium text-sm text-white truncate max-w-[200px] md:max-w-[400px] block group-hover:text-[#93C5FD] transition-colors duration-200"
                          title={doc.filename}
                        >
                          {doc.filename}
                        </span>
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
    </div>
  )
}
