import type { SearchResult, DocumentItem, UploadResult, HealthStatus, Summary, FlashcardsResponse, MergedSet, CreateMergedSetResult, MergedSummary, MergedFlashcardsResponse } from '../types'

const API_BASE_URL = '/api'

// Generation calls the AI and takes several seconds. If the same generation is
// requested again while it's running (React StrictMode runs page effects twice
// in dev, or a quick double click), share the running request instead of
// paying for a second one.
const inFlight = new Map<string, Promise<unknown>>()

function shareInFlight<T>(key: string, start: () => Promise<T>): Promise<T> {
  const running = inFlight.get(key)
  if (running) return running as Promise<T>
  const request = start().finally(() => inFlight.delete(key))
  inFlight.set(key, request)
  return request
}

export async function searchSecondBrain(
  query: string
): Promise<SearchResult> {
  const response = await fetch(
    `${API_BASE_URL}/v1/search?query=${encodeURIComponent(query)}`
  )

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(typeof errData.detail === 'string' ? errData.detail : `Search failed: ${response.status}`)
  }

  return response.json()
}

export async function uploadPDF(
  file: File
): Promise<UploadResult> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(
    `${API_BASE_URL}/v1/upload/pdf`,
    {
      method: 'POST',
      body: formData,
    }
  )

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(errData.detail || `Upload failed: ${response.status}`)
  }

  return response.json()
}

export async function uploadPPTX(
  file: File
): Promise<UploadResult> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(
    `${API_BASE_URL}/v1/upload/pptx`,
    {
      method: 'POST',
      body: formData,
    }
  )

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(errData.detail || `Upload failed: ${response.status}`)
  }

  return response.json()
}

export async function uploadDOCX(
  file: File
): Promise<UploadResult> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(
    `${API_BASE_URL}/v1/upload/docx`,
    {
      method: 'POST',
      body: formData,
    }
  )

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(errData.detail || `Upload failed: ${response.status}`)
  }

  return response.json()
}

export async function uploadYouTube(
  url: string
): Promise<UploadResult> {
  const response = await fetch(
    `${API_BASE_URL}/v1/upload/youtube`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url }),
    }
  )

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw importError(errData.detail, `YouTube import failed: ${response.status}`)
  }

  return response.json()
}

export async function uploadWebsite(
  url: string
): Promise<UploadResult> {
  const response = await fetch(
    `${API_BASE_URL}/v1/upload/website`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url }),
    }
  )

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw importError(errData.detail, `Website import failed: ${response.status}`)
  }

  return response.json()
}

// Link imports answer 409 with detail { message, document_id } when the page or
// video is already saved; every other error detail is a plain string.
function importError(detail: unknown, fallback: string): Error {
  if (detail && typeof detail === 'object' && 'document_id' in detail) {
    const d = detail as { message: string; document_id: number }
    return new DuplicateSourceError(d.message, d.document_id)
  }
  return new Error(typeof detail === 'string' && detail ? detail : fallback)
}

export class DuplicateSourceError extends Error {
  documentId: number

  constructor(message: string, documentId: number) {
    super(message)
    this.name = 'DuplicateSourceError'
    this.documentId = documentId
  }
}

export async function getDocuments(): Promise<DocumentItem[]> {
  if (typeof window !== 'undefined') {
    const urlParams = new URLSearchParams(window.location.search)
    const delayParam = urlParams.get('docs_delay_ms')
    const winDelay = (window as any).__SIMULATE_DOCS_DELAY_MS
    const delayMs = delayParam ? parseInt(delayParam, 10) : winDelay
    if (delayMs && delayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, delayMs))
    }
  }

  const response = await fetch(`${API_BASE_URL}/v1/documents`)

  if (!response.ok) {
    throw new Error(`Failed to fetch documents: ${response.status}`)
  }

  return response.json()
}

export async function deleteDocument(documentId: number): Promise<{ message: string; id: number }> {
  const response = await fetch(`${API_BASE_URL}/v1/documents/${documentId}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(errData.detail || `Failed to delete document: ${response.status}`)
  }

  return response.json()
}

export async function renameDocument(documentId: number, filename: string): Promise<{ id: number; filename: string }> {
  const response = await fetch(`${API_BASE_URL}/v1/documents/${documentId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ filename }),
  })

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(typeof errData.detail === 'string' ? errData.detail : `Failed to rename document: ${response.status}`)
  }

  return response.json()
}

export async function healthCheck(): Promise<HealthStatus> {
  const response = await fetch(`${API_BASE_URL}/v1/health`)

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`)
  }

  return response.json()
}

export async function getSummary(documentId: number): Promise<Summary> {
  const response = await fetch(`${API_BASE_URL}/v1/documents/${documentId}/summary`)

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Summary not found')
    }
    throw new Error(`Failed to fetch summary: ${response.status}`)
  }

  return response.json()
}

export function generateSummary(
  documentId: number,
  regenerate = false
): Promise<Summary> {
  return shareInFlight(`summary:${documentId}:${regenerate}`, () => requestSummary(documentId, regenerate))
}

async function requestSummary(documentId: number, regenerate: boolean): Promise<Summary> {
  const response = await fetch(
    `${API_BASE_URL}/v1/documents/${documentId}/summary?regenerate=${regenerate}`,
    {
      method: 'POST',
    }
  )

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(errData.detail || `Failed to generate summary: ${response.status}`)
  }

  return response.json()
}

export async function getFlashcards(documentId: number): Promise<FlashcardsResponse> {
  const response = await fetch(`${API_BASE_URL}/v1/documents/${documentId}/flashcards`)

  if (!response.ok) {
    throw new Error(`Failed to fetch flashcards: ${response.status}`)
  }

  return response.json()
}

export function generateFlashcards(
  documentId: number,
  count = 10
): Promise<FlashcardsResponse> {
  return shareInFlight(`flashcards:${documentId}:${count}`, () => requestFlashcards(documentId, count))
}

async function requestFlashcards(documentId: number, count: number): Promise<FlashcardsResponse> {
  const response = await fetch(
    `${API_BASE_URL}/v1/documents/${documentId}/flashcards?count=${count}`,
    {
      method: 'POST',
    }
  )

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(errData.detail || `Failed to generate flashcards: ${response.status}`)
  }

  return response.json()
}
// ─── Merged sets ───

async function detailError(response: Response, fallback: string): Promise<Error> {
  const errData = await response.json().catch(() => ({}))
  return new Error(typeof errData.detail === 'string' && errData.detail ? errData.detail : `${fallback}: ${response.status}`)
}

export async function listMergedSets(): Promise<MergedSet[]> {
  const response = await fetch(`${API_BASE_URL}/v1/merged-sets`)
  if (!response.ok) throw await detailError(response, 'Failed to load merged sets')
  return response.json()
}

export async function getMergedSet(setId: number): Promise<MergedSet> {
  const response = await fetch(`${API_BASE_URL}/v1/merged-sets/${setId}`)
  if (!response.ok) throw await detailError(response, 'Failed to load merged set')
  return response.json()
}

export async function createMergedSet(documentIds: number[], name?: string): Promise<CreateMergedSetResult> {
  const response = await fetch(`${API_BASE_URL}/v1/merged-sets`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ document_ids: documentIds, ...(name ? { name } : {}) }),
  })
  if (!response.ok) throw await detailError(response, 'Failed to create merged set')
  return response.json()
}

export async function renameMergedSet(setId: number, name: string): Promise<MergedSet> {
  const response = await fetch(`${API_BASE_URL}/v1/merged-sets/${setId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name }),
  })
  if (!response.ok) throw await detailError(response, 'Failed to rename merged set')
  return response.json()
}

export async function deleteMergedSet(setId: number): Promise<{ message: string; id: number }> {
  const response = await fetch(`${API_BASE_URL}/v1/merged-sets/${setId}`, { method: 'DELETE' })
  if (!response.ok) throw await detailError(response, 'Failed to delete merged set')
  return response.json()
}

export async function getMergedSummary(setId: number): Promise<MergedSummary> {
  const response = await fetch(`${API_BASE_URL}/v1/merged-sets/${setId}/summary`)
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Summary not found')
    }
    throw await detailError(response, 'Failed to fetch merged summary')
  }
  return response.json()
}

export function generateMergedSummary(setId: number, regenerate = false): Promise<MergedSummary> {
  return shareInFlight(`merged-summary:${setId}:${regenerate}`, async () => {
    const response = await fetch(`${API_BASE_URL}/v1/merged-sets/${setId}/summary?regenerate=${regenerate}`, {
      method: 'POST',
    })
    if (!response.ok) throw await detailError(response, 'Failed to generate merged summary')
    return response.json()
  })
}

export async function getMergedFlashcards(setId: number): Promise<MergedFlashcardsResponse> {
  const response = await fetch(`${API_BASE_URL}/v1/merged-sets/${setId}/flashcards`)
  if (!response.ok) throw await detailError(response, 'Failed to fetch merged flashcards')
  return response.json()
}

export function generateMergedFlashcards(setId: number, count = 10): Promise<MergedFlashcardsResponse> {
  return shareInFlight(`merged-flashcards:${setId}:${count}`, async () => {
    const response = await fetch(`${API_BASE_URL}/v1/merged-sets/${setId}/flashcards?count=${count}`, {
      method: 'POST',
    })
    if (!response.ok) throw await detailError(response, 'Failed to generate merged flashcards')
    return response.json()
  })
}
