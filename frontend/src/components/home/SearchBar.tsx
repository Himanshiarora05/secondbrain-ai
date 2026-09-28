import { useState } from 'react'
import { Search, ArrowRight, Loader2 } from 'lucide-react'

interface SearchBarProps {
  onSearch: (query: string) => void
  isLoading: boolean
}

export function SearchBar({ onSearch, isLoading }: SearchBarProps) {
  const [query, setQuery] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim() && !isLoading) {
      onSearch(query.trim())
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full relative group">
      <div className="relative flex items-center bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-2xl shadow-lg focus-within:border-[var(--accent-primary)] focus-within:ring-2 focus-within:ring-[var(--accent-primary-muted)] transition-all overflow-hidden">
        <div className="pl-5 text-[var(--text-tertiary)] group-focus-within:text-[var(--accent-primary)] transition-colors">
          <Search size={20} />
        </div>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="What do you want to understand?"
          className="w-full bg-transparent border-none text-white text-lg px-4 py-5 focus:outline-none placeholder-[var(--text-tertiary)]"
          disabled={isLoading}
        />
        <div className="pr-3">
          <button
            type="submit"
            aria-label="Submit search"
            disabled={isLoading || !query.trim()}
            className="w-10 h-10 bg-[var(--bg-elevated)] group-focus-within:bg-[var(--accent-primary)] hover:bg-[var(--accent-primary-hover)] text-[var(--text-secondary)] group-focus-within:text-white rounded-xl flex items-center justify-center transition-all disabled:opacity-50 disabled:cursor-not-allowed border border-[var(--border-primary)] group-focus-within:border-transparent"
          >
            {isLoading ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <ArrowRight size={18} />
            )}
          </button>
        </div>
      </div>
    </form>
  )
}
