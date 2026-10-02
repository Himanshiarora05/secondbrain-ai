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
  // Where in the source the match is: "02:05" (YouTube), "p. 12" / "pp. 12–13" (PDF), else null.
  location?: string | null
}

export interface SearchResult {
  query: string
  answer: string
  top_matches: SourceMatch[]
}

// ─── Documents ───

export type SourceType = 'pdf' | 'pptx' | 'docx' | 'youtube' | 'website' | 'image'

export interface DocumentItem {
  id: number
  file_id: string
  filename: string
  total_chunks: number
  // Characters of extracted text; documents over the merged-set limit can't be merged.
  char_count?: number
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

// SM-2 review state, on every card the API returns.
export interface CardSchedule {
  ease: number
  interval_days: number
  repetitions: number
  // YYYY-MM-DD; null until the card is first rated.
  due_date: string | null
  last_reviewed_at: string | null
}

export interface Flashcard extends Partial<CardSchedule> {
  id: number
  question: string
  answer: string
  // Where the card came from: "02:05", a page title, or "Slide 4". Null for PDF/Word
  // cards and for cards generated before citations existed.
  source_label?: string | null
  // Link for source_label (video moment or web page); null for slides.
  source_url?: string | null
}

// ─── Spaced repetition ───

export type ReviewGrade = 'again' | 'good' | 'easy'
// A document's own deck, or a merged set's deck.
export type CardKind = 'document' | 'merged'

export interface ReviewResult extends CardSchedule {
  kind: CardKind
  id: number
}

export interface DueCard extends Omit<Flashcard, keyof CardSchedule>, CardSchedule {
  kind: CardKind
  deck_id: number
  deck_name: string
  deck_source_type: SourceType | 'merged'
}

export interface DueCardsResponse {
  today: string
  // review_count scheduled cards + new_count new ones (today's share of the daily new-card limit).
  count: number
  review_count: number
  new_count: number
  // New cards held back by the limit until another day.
  new_waiting: number
  new_limit: number
  new_left_today: number
  cards: DueCard[]
}

export interface FlashcardsResponse {
  document_id: number
  flashcards: Flashcard[]
}

// ─── Merged sets (several documents studied together) ───

export interface MergedSetDocument {
  id: number
  filename: string
  source_type: SourceType
  source_url?: string | null
}

export interface MergedSet {
  id: number
  name: string
  created_at: string | null
  updated_at: string | null
  // Current members in set order; a deleted document drops out of this list.
  documents: MergedSetDocument[]
  has_summary: boolean
  flashcard_count: number
  // Generated before one of its documents was deleted.
  summary_stale: boolean
  flashcards_stale: boolean
}

export interface CreateMergedSetResult {
  // False when a set with exactly these documents already existed and was reopened.
  created: boolean
  merged_set: MergedSet
}

export interface MergedSummary {
  set_id: number
  // Starts with a code-built "Sources" list; citations look like "(1: p. 12)" or "[3: 02:05](url)".
  summary: string
  created_at: string | null
  stale: boolean
}

export interface MergedFlashcard extends Flashcard {
  // The source the card came from; null once that document is deleted.
  document_id: number | null
}

export interface MergedFlashcardsResponse {
  set_id: number
  flashcards: MergedFlashcard[]
  stale: boolean
}

// ─── Quizzes (a document's or a merged set's) ───

export interface QuizQuestion {
  id: number
  question: string
  // Always 4, in the order shown.
  options: string[]
  correct_index: number
  explanation: string
  // Like flashcards: "p. 12", "Slide 4", "02:05" (+ link); merged quizzes name the source.
  source_label: string | null
  source_url: string | null
  // Merged quizzes: the source document, null once it's deleted.
  document_id: number | null
}

export interface Quiz {
  id: number
  created_at: string | null
  questions: QuizQuestion[]
  // Merged quizzes: a source document was deleted after the quiz was made.
  stale: boolean
}

export interface QuizAttempt {
  id: number
  quiz_id: number
  score: number
  total: number
  // One per question: the chosen option's index, or null if skipped.
  answers: (number | null)[]
  created_at: string | null
}

export interface QuizState {
  document_id: number | null
  set_id: number | null
  // The newest quiz; null until one is generated.
  quiz: Quiz | null
  // Recent attempts at any of this document's (or set's) quizzes, newest first.
  attempts: QuizAttempt[]
}

export interface QuizAttemptResult extends QuizState {
  attempt: QuizAttempt
}

// ─── Accounts ───

export interface AuthUser {
  id: number
  email: string
}
