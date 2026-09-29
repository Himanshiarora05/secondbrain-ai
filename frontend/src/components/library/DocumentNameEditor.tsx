import { useEffect, useRef, useState } from 'react'

interface DocumentNameEditorProps {
  initialName: string
  onSave: (name: string) => Promise<void>
  onDone: () => void
  className?: string
}

// Inline name field: Enter or clicking away saves, Escape cancels. A failed
// save keeps the field open with the server's message under it.
export function DocumentNameEditor({ initialName, onSave, onDone, className = '' }: DocumentNameEditorProps) {
  const [name, setName] = useState(initialName)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  // Refs, not state: disabling the field while saving (or unmounting it) fires a
  // blur, which must not start a second save before React re-renders.
  const cancelled = useRef(false)
  const saving = useRef(false)

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    input.focus()
    // Select the name without its extension, like a file manager does.
    const dot = initialName.lastIndexOf('.')
    input.setSelectionRange(0, dot > 0 ? dot : initialName.length)
  }, [initialName])

  const save = async () => {
    if (cancelled.current || saving.current) return
    const trimmed = name.trim()
    if (!trimmed || trimmed === initialName) {
      cancelled.current = true
      onDone()
      return
    }
    saving.current = true
    setIsSaving(true)
    setError(null)
    try {
      await onSave(trimmed)
      cancelled.current = true
      onDone()
    } catch (err) {
      saving.current = false
      setError(err instanceof Error ? err.message : 'Failed to rename document')
      setIsSaving(false)
      // Refocus once the field is enabled again.
      setTimeout(() => inputRef.current?.focus())
    }
  }

  return (
    <div className={`min-w-0 ${className}`} onClick={(e) => e.stopPropagation()}>
      <input
        ref={inputRef}
        type="text"
        value={name}
        maxLength={255}
        disabled={isSaving}
        onChange={(e) => {
          setName(e.target.value)
          setError(null)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            save()
          } else if (e.key === 'Escape') {
            e.preventDefault()
            cancelled.current = true
            onDone()
          }
        }}
        onBlur={save}
        aria-label="Document name"
        aria-invalid={error ? true : undefined}
        className={`w-full bg-[rgba(255,255,255,0.05)] border rounded-lg px-2.5 py-1 text-sm font-semibold text-white focus:outline-none transition-all duration-200 disabled:opacity-60 ${
          error
            ? 'border-[rgba(239,68,68,0.5)]'
            : 'border-[rgba(59,130,246,0.4)] focus:shadow-[0_0_16px_rgba(59,130,246,0.15)]'
        }`}
      />
      {error ? (
        <p className="mt-1 text-xs text-[#F87171]" role="alert">{error}</p>
      ) : (
        <p className="mt-1 text-[11px] text-[#5C5C6E]">{isSaving ? 'Saving…' : 'Enter to save · Esc to cancel'}</p>
      )}
    </div>
  )
}
