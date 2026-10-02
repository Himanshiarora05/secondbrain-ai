import { useEffect, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Video, UploadCloud, ArrowRight, Globe, CheckCircle2, XCircle, MinusCircle, X } from 'lucide-react'
import {
  uploadPDF,
  uploadPPTX,
  uploadDOCX,
  uploadImages,
  uploadYouTube,
  uploadWebsite,
  getDocuments,
  DuplicateSourceError,
} from '../../api/client'
import type { DocumentItem, MergedSet, UploadResult } from '../../types'
import { LoadingSpinner } from '../ui/LoadingSpinner'
import { MergePrompt } from './MergePrompt'

interface UploadZoneProps {
  // `keepOpen` is true when results or a merge prompt stay on screen after the
  // upload, so the caller shouldn't close the upload area.
  onUploadSuccess: (info?: { keepOpen: boolean }) => void
  // A merged set was created from the merge prompt (the Library refreshes its sets).
  onMergedSetCreated?: (set: MergedSet) => void
}

// Same wording as the backend (upload.py); python-pptx/python-docx can't read the old binary formats.
const LEGACY_PPT_MESSAGE =
  "Old PowerPoint files (.ppt) aren't supported. Open the file in PowerPoint (or Google Slides / LibreOffice), choose File → Save As → .pptx, and upload that."
const LEGACY_DOC_MESSAGE =
  "Old Word files (.doc) aren't supported. Open the file in Word (or Google Docs / LibreOffice), choose File → Save As → .docx, and upload that."

// Same limit as MAX_OCR_PAGES in the backend (ocr_service.py): each image is one OCR call.
const MAX_IMAGES = 20

type FileKind = 'pdf' | 'pptx' | 'docx' | 'images'

function isImage(file: File): boolean {
  return /\.(jpe?g|png)$/i.test(file.name) || file.type === 'image/jpeg' || file.type === 'image/png'
}

// Which upload endpoint a (non-image) file goes to, or why it can't be uploaded.
function classifyFile(file: File): { kind: FileKind } | { error: string } {
  const filename = file.name.toLowerCase()
  if (filename.endsWith('.ppt')) return { error: LEGACY_PPT_MESSAGE }
  if (filename.endsWith('.doc')) return { error: LEGACY_DOC_MESSAGE }
  if (filename.endsWith('.pdf') || file.type === 'application/pdf') return { kind: 'pdf' }
  if (filename.endsWith('.pptx')) return { kind: 'pptx' }
  if (filename.endsWith('.docx')) return { kind: 'docx' }
  return { error: 'Unsupported file type. Please upload a PDF, PowerPoint (.pptx), Word (.docx) or image (JPG, PNG) file.' }
}

// One document to create: a single file, or every image picked together
// (one document, each image a page, in the order picked).
type UploadUnit = { name: string; files: File[] } & ({ kind: FileKind } | { error: string })

function planUploads(files: File[]): UploadUnit[] {
  const images = files.filter(isImage)
  const units: UploadUnit[] = []
  for (const file of files) {
    if (!isImage(file)) {
      units.push({ name: file.name, files: [file], ...classifyFile(file) })
    } else if (file === images[0]) {
      // The images go where the first one was picked.
      const name = images.length === 1 ? file.name : `${images.length} images (one document)`
      units.push(
        images.length > MAX_IMAGES
          ? { name, files: images, error: `Text recognition is limited to ${MAX_IMAGES} images per upload. Pick ${MAX_IMAGES} or fewer.` }
          : { name, files: images, kind: 'images' },
      )
    }
  }
  return units
}

function uploadUnit(kind: FileKind, files: File[]): Promise<UploadResult> {
  switch (kind) {
    case 'images':
      return uploadImages(files)
    case 'pptx':
      return uploadPPTX(files[0])
    case 'docx':
      return uploadDOCX(files[0])
    default:
      return uploadPDF(files[0])
  }
}

// One document of a multi-file upload.
interface BatchItem {
  name: string
  status: 'waiting' | 'uploading' | 'done' | 'failed' | 'skipped'
  message?: string
  documentId?: number
}

const NON_HTTP_SCHEME =/^(javascript|data|mailto|file|ftp|about|blob|vbscript|tel):/i

// Friendly checks only; the backend makes every security decision (private addresses, redirects, size).
function validateWebsiteUrl(raw: string): { url: string } | { error: string } {
  const trimmed = raw.trim()
  if (!trimmed) return { error: 'Please enter a web page link.' }

  const candidate = !trimmed.includes('://') && !NON_HTTP_SCHEME.test(trimmed) ? `https://${trimmed}` : trimmed
  let parsed: URL
  try {
    parsed = new URL(candidate)
  } catch {
    return { error: "That doesn't look like a valid link. Example: https://example.com/article" }
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return { error: 'Only http:// and https:// links can be imported.' }
  }
  if (parsed.username || parsed.password) {
    return { error: "Links containing a username or password can't be imported." }
  }
  if (!parsed.hostname.includes('.') && !parsed.hostname.startsWith('[')) {
    return { error: 'Please enter a full web address, like https://example.com/article.' }
  }
  if (/(^|\.)(youtube\.com|youtube-nocookie\.com|youtu\.be)$/i.test(parsed.hostname)) {
    return { error: 'This is a YouTube link. Use the YouTube Video tab to import its transcript.' }
  }
  return { url: parsed.href }
}

export function UploadZone({ onUploadSuccess, onMergedSetCreated }: UploadZoneProps) {
  const [activeTab, setActiveTab] = useState<'file' | 'youtube' | 'website'>('file')
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  // A single upload of images: the progress text says they're being read (OCR is slower).
  const [readingImages, setReadingImages] = useState(false)
  const [youtubeUrl, setYoutubeUrl] = useState('')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  // Set when the error is "already in your library"; only shown while that error is.
  const [duplicate, setDuplicate] = useState<{ message: string; documentId: number } | null>(null)
  // Results of the last multi-file upload (null for single-file uploads).
  const [batch, setBatch] = useState<BatchItem[] | null>(null)
  // The merge prompt after an upload: the new document(s) and the library they can be merged with.
  const [mergeOffer, setMergeOffer] = useState<{ newIds: number[]; documents: DocumentItem[] } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const promptRef = useRef<HTMLDivElement>(null)
  const isUploadingRef = useRef(false)

  // When an upload finishes, bring the merge prompt (or a multi-file upload's
  // results) into view: below the drop area they're often under the fold.
  const batchFinished = batch !== null && !isUploading
  const promptShown = mergeOffer !== null && !isUploading
  useEffect(() => {
    const target = promptRef.current ?? resultsRef.current
    if (batchFinished || promptShown) target?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [batchFinished, promptShown])

  // After an upload: offer to merge the new document(s), if there's something
  // to merge (two new ones, or anything else in the library). Returns whether the prompt is shown.
  const offerMerge = async (ids: (number | undefined)[]): Promise<boolean> => {
    try {
      const documents = await getDocuments()
      const newIds = ids.filter((id): id is number => id !== undefined && documents.some((d) => d.id === id))
      if (newIds.length === 0 || (newIds.length < 2 && documents.length === newIds.length)) return false
      setMergeOffer({ newIds, documents })
      return true
    } catch {
      return false // the upload itself worked; there's just no prompt
    }
  }

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

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      await handleFiles(Array.from(e.dataTransfer.files))
    }
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isUploadingRef.current) return
    if (e.target.files && e.target.files.length > 0) {
      await handleFiles(Array.from(e.target.files))
    }
  }

  const handleFiles = async (files: File[]) => {
    setBatch(null)
    setMergeOffer(null)
    const units = planUploads(files)
    if (units.length === 1) {
      await handleFileUpload(units[0])
    } else {
      await handleBatchUpload(units)
    }
  }

  // Several documents: uploaded one after another (each is CPU-heavy on the
  // server). A failed or skipped one doesn't stop the rest.
  const handleBatchUpload = async (units: UploadUnit[]) => {
    if (isUploadingRef.current) return
    const items: BatchItem[] = units.map((u) =>
      'error' in u ? { name: u.name, status: 'skipped', message: u.error } : { name: u.name, status: 'waiting' },
    )
    const update = (i: number, patch: Partial<BatchItem>) => {
      items[i] = { ...items[i], ...patch }
      setBatch([...items])
    }

    isUploadingRef.current = true
    setError(null)
    setDuplicate(null)
    setIsUploading(true)
    setBatch([...items])

    try {
      for (let i = 0; i < units.length; i++) {
        const u = units[i]
        if ('error' in u) continue
        update(i, { status: 'uploading' })
        try {
          const res = await uploadUnit(u.kind, u.files)
          update(i, { status: 'done', documentId: res.document_id })
        } catch (err) {
          update(i, { status: 'failed', message: err instanceof Error ? err.message : 'Upload failed' })
        }
      }
      const uploaded = items.filter((it) => it.status === 'done').map((it) => it.documentId)
      if (uploaded.length > 0) {
        await offerMerge(uploaded)
        onUploadSuccess({ keepOpen: true }) // the per-file results stay on screen
      }
    } finally {
      isUploadingRef.current = false
      setIsUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleFileUpload = async (unit: UploadUnit) => {
    if (isUploadingRef.current) return

    if ('error' in unit) {
      setError(unit.error)
      return
    }

    isUploadingRef.current = true
    setError(null)
    setReadingImages(unit.kind === 'images')
    setIsUploading(true)

    try {
      const res = await uploadUnit(unit.kind, unit.files)
      onUploadSuccess({ keepOpen: await offerMerge([res.document_id]) })
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
    setMergeOffer(null)
    setIsUploading(true)

    try {
      const res = await uploadYouTube(youtubeUrl.trim())
      setYoutubeUrl('')
      onUploadSuccess({ keepOpen: await offerMerge([res.document_id]) })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import YouTube video')
      setDuplicate(err instanceof DuplicateSourceError ? { message: err.message, documentId: err.documentId } : null)
    } finally {
      isUploadingRef.current = false
      setIsUploading(false)
    }
  }

  const handleWebsiteSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (isUploadingRef.current) return

    const result = validateWebsiteUrl(websiteUrl)
    if ('error' in result) {
      setError(result.error)
      return
    }

    isUploadingRef.current = true
    setError(null)
    setMergeOffer(null)
    setIsUploading(true)

    try {
      const res = await uploadWebsite(result.url)
      setWebsiteUrl('')
      onUploadSuccess({ keepOpen: await offerMerge([res.document_id]) })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import web page')
      setDuplicate(err instanceof DuplicateSourceError ? { message: err.message, documentId: err.documentId } : null)
    } finally {
      isUploadingRef.current = false
      setIsUploading(false)
    }
  }

  return (
    <div className="bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] rounded-3xl p-4 sm:p-8 shadow-[0_8px_32px_rgba(0,0,0,0.5)] transition-all duration-200">
      {/* Mode Switcher */}
      <div className="flex items-center justify-center gap-2 mb-8 p-1.5 bg-[rgba(255,255,255,0.04)] rounded-2xl max-w-lg mx-auto border border-[rgba(255,255,255,0.08)]">
        <button
          type="button"
          onClick={() => { setActiveTab('file'); setError(null); }}
          className={`flex-1 flex items-center justify-center gap-1.5 sm:gap-2 py-2.5 px-2 sm:px-4 rounded-xl text-xs font-semibold transition-all duration-200 ${
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
          className={`flex-1 flex items-center justify-center gap-1.5 sm:gap-2 py-2.5 px-2 sm:px-4 rounded-xl text-xs font-semibold transition-all duration-200 ${
            activeTab === 'youtube'
              ? 'bg-gradient-to-r from-[#EF4444] to-[#DC2626] text-white shadow-[0_0_20px_rgba(239,68,68,0.35)]'
              : 'text-[#A1A1AA] hover:text-white'
          }`}
        >
          <Video size={16} />
          <span>YouTube Video</span>
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab('website'); setError(null); }}
          className={`flex-1 flex items-center justify-center gap-1.5 sm:gap-2 py-2.5 px-2 sm:px-4 rounded-xl text-xs font-semibold transition-all duration-200 ${
            activeTab === 'website'
              ? 'bg-gradient-to-r from-[#06B6D4] to-[#0891B2] text-white shadow-[0_0_20px_rgba(6,182,212,0.35)]'
              : 'text-[#A1A1AA] hover:text-white'
          }`}
        >
          <Globe size={16} />
          <span>Website link</span>
        </button>
      </div>

      {activeTab === 'file' ? (
        <>
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
          aria-label="Upload document (PDF, PowerPoint, Word, images)"
        >
          <input
            type="file"
            multiple
            className="hidden"
            accept=".pdf,.pptx,.docx,.jpg,.jpeg,.png,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/jpeg,image/png"
            onChange={handleFileChange}
            ref={fileInputRef}
            disabled={isUploading}
          />

          {isUploading && batch ? (
            <div className="flex flex-col items-center py-8 animate-fade-in" aria-live="polite">
              <LoadingSpinner size={40} className="mb-4 text-[#3B82F6]" />
              {(() => {
                const queue = batch.filter((it) => it.status !== 'skipped')
                const current = queue.findIndex((it) => it.status === 'uploading')
                return (
                  <>
                    <p className="text-white font-semibold text-base">
                      Uploading {Math.max(current, 0) + 1} of {queue.length}
                    </p>
                    <p className="text-xs text-[#A1A1AA] mt-1.5 max-w-full truncate px-4">
                      {current >= 0 ? queue[current].name : ''}
                    </p>
                  </>
                )
              })()}
            </div>
          ) : isUploading ? (
            <div className="flex flex-col items-center py-8 animate-fade-in">
              <LoadingSpinner size={40} className="mb-4 text-[#3B82F6]" />
              <p className="text-white font-semibold text-base">
                {readingImages ? 'Reading your images...' : 'Processing Document...'}
              </p>
              <p className="text-xs text-[#A1A1AA] mt-1.5">
                {readingImages
                  ? 'Recognising the text in each image with AI. This can take a minute.'
                  : 'Extracting text, creating chunks, and generating dense vector embeddings'}
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center py-6">
              <div className="w-14 h-14 rounded-2xl bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.08)] flex items-center justify-center text-[#93C5FD] mb-4 shadow-[0_0_20px_rgba(59,130,246,0.15)] group-hover:scale-105 transition-all duration-200">
                <Plus size={26} />
              </div>
              <h3 className="text-lg font-bold text-white mb-2 tracking-tight">Drop your study material here, or browse</h3>
              <p className="text-xs text-[#A1A1AA] mb-6 max-w-sm">
                Supported formats: PDF lecture notes, PowerPoint presentations, Word files, and photos or screenshots of notes. You can pick several files at once.
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
                <span className="px-3 py-1 text-xs font-bold uppercase tracking-wider rounded-lg bg-[rgba(52,211,153,0.2)] text-[#34D399] border border-[rgba(52,211,153,0.3)] shadow-sm">
                  JPG / PNG
                </span>
              </div>

              <p className="text-xs text-[#A1A1AA] mb-3 max-w-sm">
                Images picked together become one document, one page per image. Images and scanned PDF pages are
                read with AI text recognition, up to {MAX_IMAGES} pages per upload.
              </p>
              <p className="text-[11px] text-[#5C5C6E] font-mono">Maximum file size: 20 MB</p>
            </div>
          )}
        </div>

        {batch && !isUploading && (
          <div ref={resultsRef} className="mt-5 p-4 sm:p-5 rounded-2xl bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] animate-fade-in scroll-mt-6" role="region" aria-label="Upload results">
            <div className="flex items-start justify-between gap-3 mb-3">
              <p className="text-sm font-semibold text-white">
                {(() => {
                  const done = batch.filter((it) => it.status === 'done').length
                  const notDone = batch.length - done
                  return `${done} of ${batch.length} uploaded` + (notDone ? ` · ${notDone} not uploaded` : '')
                })()}
              </p>
              <button
                onClick={() => setBatch(null)}
                className="p-1 -m-1 rounded-lg text-[#71717A] hover:text-white hover:bg-[rgba(255,255,255,0.06)] transition-colors"
                aria-label="Dismiss upload results"
                title="Dismiss"
              >
                <X size={16} />
              </button>
            </div>
            <ul className="space-y-2">
              {batch.map((it, i) => (
                <li key={i} className="flex items-start gap-2.5 text-xs min-w-0">
                  {/* The icons are decorative; the status is also in text for screen readers. */}
                  {it.status === 'done' ? (
                    <CheckCircle2 size={15} className="text-[#34D399] flex-shrink-0 mt-px" aria-hidden="true" />
                  ) : it.status === 'skipped' ? (
                    <MinusCircle size={15} className="text-[#FBBF24] flex-shrink-0 mt-px" aria-hidden="true" />
                  ) : (
                    <XCircle size={15} className="text-[#F87171] flex-shrink-0 mt-px" aria-hidden="true" />
                  )}
                  <div className="min-w-0">
                    <p className="text-[#D1D5DB] truncate" title={it.name}>
                      <span className="sr-only">
                        {it.status === 'done' ? 'Uploaded: ' : it.status === 'skipped' ? 'Skipped: ' : 'Failed: '}
                      </span>
                      {it.name}
                    </p>
                    {it.message && (
                      <p className={it.status === 'skipped' ? 'text-[#FBBF24]' : 'text-[#F87171]'}>{it.message}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        </>
      ) : activeTab === 'website' ? (
        <form onSubmit={handleWebsiteSubmit} noValidate className="flex flex-col items-center p-8 text-center max-w-xl mx-auto">
          <div className="w-14 h-14 rounded-2xl bg-[rgba(34,211,238,0.15)] border border-[rgba(34,211,238,0.25)] flex items-center justify-center text-[#22D3EE] mb-4 shadow-[0_0_20px_rgba(34,211,238,0.15)]">
            <Globe size={26} />
          </div>
          <h3 className="text-lg font-bold text-white mb-2 tracking-tight">Import a Web Page</h3>
          <p className="text-xs text-[#A1A1AA] mb-8 leading-relaxed">
            Paste a link to an article or blog post. SecondBrain will read the main text, skip menus, ads and footers, and link your notes back to the page.
          </p>

          <div className="w-full flex flex-col sm:flex-row items-center gap-3">
            <input
              type="url"
              inputMode="url"
              value={websiteUrl}
              onChange={(e) => { setWebsiteUrl(e.target.value); if (error) setError(null) }}
              placeholder="https://example.com/article"
              disabled={isUploading}
              aria-label="Web page link"
              aria-invalid={Boolean(error)}
              className="w-full bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.1)] rounded-2xl px-5 py-3 text-sm text-white placeholder-[#5C5C6E] focus:outline-none focus:border-[#06B6D4] focus:ring-1 focus:ring-[#06B6D4] transition-all duration-200"
            />
            <button
              type="submit"
              disabled={isUploading || !websiteUrl.trim()}
              className="w-full sm:w-auto flex items-center justify-center gap-2 bg-gradient-to-r from-[#06B6D4] to-[#0891B2] text-white font-semibold px-6 py-3 rounded-2xl transition-all duration-200 disabled:opacity-40 whitespace-nowrap shadow-[0_0_20px_rgba(6,182,212,0.35)] hover:brightness-110 text-xs"
            >
              {isUploading ? (
                <>
                  <LoadingSpinner size={16} className="text-white" />
                  <span>Fetching page...</span>
                </>
              ) : (
                <>
                  <span>Import Page</span>
                  <ArrowRight size={14} />
                </>
              )}
            </button>
          </div>
          <p className="text-[11px] text-[#5C5C6E] font-mono mt-4">
            Public pages only · no logins or paywalls · maximum 5 MB
          </p>
        </form>
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

      {mergeOffer && !isUploading && (
        <div ref={promptRef} className="max-w-2xl mx-auto scroll-mt-6">
          <MergePrompt
            newIds={mergeOffer.newIds}
            documents={mergeOffer.documents}
            onDismiss={() => setMergeOffer(null)}
            onCreated={onMergedSetCreated}
          />
        </div>
      )}

      {error && (
        <div className="mt-5 p-4 bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.3)] text-[#F87171] rounded-2xl text-xs flex items-center gap-2 max-w-lg mx-auto animate-fade-in">
          <span>{error}</span>
          {duplicate && duplicate.message === error && (
            <Link
              to={`/library/${duplicate.documentId}/summary`}
              className="ml-auto flex-shrink-0 inline-flex items-center gap-1 font-semibold text-[#FCA5A5] hover:text-white underline underline-offset-2"
            >
              Open it
              <ArrowRight size={12} />
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
