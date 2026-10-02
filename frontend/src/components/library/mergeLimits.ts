import type { DocumentItem } from '../../types'

// Same limits as the backend (app/routes/merged_sets.py), which also caps the
// total text (MERGED_MAX_CHARS, default 300,000 characters) and explains when a
// selection is over either limit.
export const MIN_MERGED = 2
export const MAX_MERGED = 8
// The most text one document in a merged set can have: the default of
// MERGED_MAX_DOC_CHARS. If .env changes it, the backend's message still applies.
export const MAX_MERGED_DOC_CHARS = 100_000

export function tooLongToMerge(doc: DocumentItem): boolean {
  return (doc.char_count ?? 0) > MAX_MERGED_DOC_CHARS
}

// Short note shown on a document that can't be picked.
export function tooLongNote(doc: DocumentItem): string {
  return `Too long to merge: ${(doc.char_count ?? 0).toLocaleString()} characters (at most ${MAX_MERGED_DOC_CHARS.toLocaleString()})`
}
