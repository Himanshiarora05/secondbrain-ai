import type { SearchResult, DocumentItem, UploadResult, HealthStatus, Summary, FlashcardsResponse } from '../types'

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
    throw new Error(`Search failed: ${response.status}`)
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
    throw new Error(errData.detail || `YouTube import failed: ${response.status}`)
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
    throw new Error(errData.detail || `Website import failed: ${response.status}`)
  }

  return response.json()
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