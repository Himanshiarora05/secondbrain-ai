import { useState, useRef } from 'react'
import { Plus, Video, UploadCloud, ArrowRight } from 'lucide-react'
import { uploadPDF, uploadPPTX, uploadDOCX, uploadYouTube } from '../../api/client'
import { LoadingSpinner } from '../ui/LoadingSpinner'

interface UploadZoneProps {
  onUploadSuccess: () => void
}

export function UploadZone({ onUploadSuccess }: UploadZoneProps) {
  const [activeTab, setActiveTab] = useState<'file' | 'youtube'>('file')
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [youtubeUrl, setYoutubeUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const isUploadingRef = useRef(false)

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') setIsDragging(true)
    else if (e.type === 'dragleave') setIsDragging(false)
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)

    if (isUploadingRef.current) return

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await handleFileUpload(e.dataTransfer.files[0])
    }
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isUploadingRef.current) return
    if (e.target.files && e.target.files[0]) {
      await handleFileUpload(e.target.files[0])
    }
  }

  const handleFileUpload = async (file: File) => {
    if (isUploadingRef.current) return

    const filename = file.name.toLowerCase()
    const isPDF = filename.endsWith('.pdf') || file.type === 'application/pdf'
    const isPPTX = filename.endsWith('.pptx') || filename.endsWith('.ppt')
    const isDOCX = filename.endsWith('.docx') || filename.endsWith('.doc')

    if (!isPDF && !isPPTX && !isDOCX) {
      setError('Unsupported file type. Please upload a PDF, PowerPoint (.pptx), or Word (.docx) document.')
      return
    }

    isUploadingRef.current = true
    setError(null)
    setIsUploading(true)

    try {
      if (isPDF) {
        await uploadPDF(file)
      } else if (isPPTX) {
        await uploadPPTX(file)
      } else if (isDOCX) {
        await uploadDOCX(file)
      }
      onUploadSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      isUploadingRef.current = false
      setIsUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleYouTubeSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (isUploadingRef.current) return

    if (!youtubeUrl.trim()) {
      setError('Please enter a valid YouTube video URL.')
      return
    }

    isUploadingRef.current = true
    setError(null)
    setIsUploading(true)

    try {
      await uploadYouTube(youtubeUrl.trim())
      setYoutubeUrl('')
      onUploadSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import YouTube video')
    } finally {
      isUploadingRef.current = false
      setIsUploading(false)
    }
  }

  return (
    <div className="bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] rounded-3xl p-8 shadow-[0_8px_32px_rgba(0,0,0,0.5)] transition-all duration-200">
      {/* Mode Switcher */}
      <div className="flex items-center justify-center gap-2 mb-8 p-1.5 bg-[rgba(255,255,255,0.04)] rounded-2xl max-w-sm mx-auto border border-[rgba(255,255,255,0.08)]">
        <button
          type="button"
          onClick={() => { setActiveTab('file'); setError(null); }}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-semibold transition-all duration-200 ${
            activeTab === 'file'
              ? 'bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white shadow-[0_0_20px_rgba(59,130,246,0.35)]'
              : 'text-[#A1A1AA] hover:text-white'
          }`}
        >
          <UploadCloud size={16} />
          <span>Upload Document</span>
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab('youtube'); setError(null); }}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-semibold transition-all duration-200 ${
            activeTab === 'youtube'
              ? 'bg-gradient-to-r from-[#EF4444] to-[#DC2626] text-white shadow-[0_0_20px_rgba(239,68,68,0.35)]'
              : 'text-[#A1A1AA] hover:text-white'
          }`}
        >
          <Video size={16} />
          <span>YouTube Video</span>
        </button>
      </div>

      {activeTab === 'file' ? (
        <div
          className={`relative flex flex-col items-center justify-center p-10 text-center rounded-2xl border-2 border-dashed transition-all duration-200 cursor-pointer ${
            isDragging
              ? 'border-[#3B82F6] bg-[rgba(59,130,246,0.08)] scale-[1.01]'
              : 'border-[rgba(255,255,255,0.1)] bg-[rgba(255,255,255,0.015)] hover:border-[rgba(59,130,246,0.4)] hover:bg-[rgba(59,130,246,0.03)] hover:shadow-[0_0_24px_rgba(59,130,246,0.08)]'
          }`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => !isUploading && fileInputRef.current?.click()}
          role="button"
          tabIndex={isUploading ? -1 : 0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              if (!isUploading) fileInputRef.current?.click()
            }
          }}
          aria-label="Upload document (PDF, PowerPoint, Word)"
        >
          <input
            type="file"
            className="hidden"
            accept=".pdf,.pptx,.ppt,.docx,.doc,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={handleFileChange}
            ref={fileInputRef}
            disabled={isUploading}
          />

          {isUploading ? (
            <div className="flex flex-col items-center py-8 animate-fade-in">
              <LoadingSpinner size={40} className="mb-4 text-[#3B82F6]" />
              <p className="text-white font-semibold text-base">Processing Document...</p>
              <p className="text-xs text-[#A1A1AA] mt-1.5">
                Extracting text, creating chunks, and generating dense vector embeddings
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center py-6">
              <div className="w-14 h-14 rounded-2xl bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.08)] flex items-center justify-center text-[#93C5FD] mb-4 shadow-[0_0_20px_rgba(59,130,246,0.15)] group-hover:scale-105 transition-all duration-200">
                <Plus size={26} />
              </div>
              <h3 className="text-lg font-bold text-white mb-2 tracking-tight">Drop your study material here, or browse</h3>
              <p className="text-xs text-[#A1A1AA] mb-6 max-w-sm">
                Supported formats: PDF lecture notes, PowerPoint presentations, and Word files
              </p>

              <div className="flex flex-wrap items-center justify-center gap-2.5 mb-4">
                <span className="px-3 py-1 text-xs font-bold uppercase tracking-wider rounded-lg bg-[rgba(251,113,133,0.2)] text-[#FB7185] border border-[rgba(251,113,133,0.3)] shadow-sm">
                  PDF
                </span>
                <span className="px-3 py-1 text-xs font-bold uppercase tracking-wider rounded-lg bg-[rgba(251,191,36,0.2)] text-[#FBBF24] border border-[rgba(251,191,36,0.3)] shadow-sm">
                  PPTX
                </span>
                <span className="px-3 py-1 text-xs font-bold uppercase tracking-wider rounded-lg bg-[rgba(96,165,250,0.2)] text-[#60A5FA] border border-[rgba(96,165,250,0.3)] shadow-sm">
                  DOCX
                </span>
              </div>

              <p className="text-[11px] text-[#5C5C6E] font-mono">Maximum file size: 20 MB</p>
            </div>
          )}
        </div>
      ) : (
        <form onSubmit={handleYouTubeSubmit} className="flex flex-col items-center p-8 text-center max-w-xl mx-auto">
          <div className="w-14 h-14 rounded-2xl bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.25)] flex items-center justify-center text-[#F87171] mb-4 shadow-[0_0_20px_rgba(248,113,113,0.15)]">
            <Video size={26} />
          </div>
          <h3 className="text-lg font-bold text-white mb-2 tracking-tight">Import YouTube Video</h3>
          <p className="text-xs text-[#A1A1AA] mb-8 leading-relaxed">
            Paste a link to any YouTube video with captions. SecondBrain will ingest the transcript and generate timestamped study clips.
          </p>

          <div className="w-full flex flex-col sm:flex-row items-center gap-3">
            <input
              type="text"
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=... or https://youtu.be/..."
              disabled={isUploading}
              className="w-full bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.1)] rounded-2xl px-5 py-3 text-sm text-white placeholder-[#5C5C6E] focus:outline-none focus:border-[#EF4444] focus:ring-1 focus:ring-[#EF4444] transition-all duration-200"
            />
            <button
              type="submit"
              disabled={isUploading || !youtubeUrl.trim()}
              className="w-full sm:w-auto flex items-center justify-center gap-2 bg-gradient-to-r from-[#EF4444] to-[#DC2626] text-white font-semibold px-6 py-3 rounded-2xl transition-all duration-200 disabled:opacity-40 whitespace-nowrap shadow-[0_0_20px_rgba(239,68,68,0.35)] hover:brightness-110 text-xs"
            >
              {isUploading ? (
                <>
                  <LoadingSpinner size={16} className="text-white" />
                  <span>Importing...</span>
                </>
              ) : (
                <>
                  <span>Import Video</span>
                  <ArrowRight size={14} />
                </>
              )}
            </button>
          </div>
        </form>
      )}

      {error && (
        <div className="mt-5 p-4 bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.3)] text-[#F87171] rounded-2xl text-xs flex items-center gap-2 max-w-lg mx-auto animate-fade-in">
          <span>{error}</span>
        </div>
      )}
    </div>
  )
}
