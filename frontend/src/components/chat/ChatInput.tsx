import { useState, useRef, useEffect } from 'react'
import { ArrowUp, Loader2 } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string) => void
  isLoading: boolean
}

export function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [input])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleSubmit = () => {
    if (input.trim() && !isLoading) {
      onSend(input.trim())
      setInput('')
    }
  }

  return (
    <div className="relative bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-2xl p-2 shadow-lg focus-within:border-[var(--accent-primary)] focus-within:ring-1 focus-within:ring-[var(--accent-primary)] transition-all">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Message SecondBrain..."
        className="w-full max-h-[200px] bg-transparent border-none text-white resize-none px-4 py-3 focus:outline-none placeholder-[var(--text-tertiary)]"
        rows={1}
        disabled={isLoading}
      />
      <div className="absolute right-3 bottom-3">
        <button
          onClick={handleSubmit}
          disabled={!input.trim() || isLoading}
          className="p-2 bg-[var(--accent-primary)] hover:bg-[var(--accent-primary-hover)] text-white rounded-xl disabled:opacity-50 disabled:bg-[var(--bg-elevated)] disabled:text-[var(--text-tertiary)] transition-colors"
          aria-label="Send message"
        >
          {isLoading ? <Loader2 className="animate-spin" size={20} /> : <ArrowUp size={20} />}
        </button>
      </div>
    </div>
  )
}
