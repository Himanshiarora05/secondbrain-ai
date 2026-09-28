// ============================================
// SecondBrain AI — Shared TypeScript Types
// ============================================

// ─── Search ───

export interface SourceMatch {
  score: number
  content: string
  document: string
  youtube_timestamp_url?: string
  source_type?: SourceType
  source_url?: string
}

export interface SearchResult {
  query: string
  answer: string
  top_matches: SourceMatch[]
}

// ─── Documents ───

export type SourceType = 'pdf' | 'pptx' | 'docx' | 'youtube' | 'website'

export interface DocumentItem {
  id: number
  file_id: string
  filename: string
  total_chunks: number
  source_type?: SourceType
  source_url?: string
}

// ─── Upload ───

export interface UploadResult {
  file_id: string
  document_id?: number
  text_length: number
  total_chunks: number
  source_type?: string
  status: string
}

// ─── Chat ───

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceMatch[]
  timestamp: number
}

// ─── Health ───

export interface HealthStatus {
  status: string
  service: string
  version: string
}

// ─── Study (Summary & Flashcards) ───

export interface Summary {
  document_id: number
  summary: string
}

export interface Flashcard {
  id: number
  question: string
  answer: string
  // Where the card came from: "02:05", a page title, or "Slide 4". Null for PDF/Word
  // cards and for cards generated before citations existed.
  source_label?: string | null
  // Link for source_label (video moment or web page); null for slides.
  source_url?: string | null
}

export interface FlashcardsResponse {
  document_id: number
  flashcards: Flashcard[]
}
