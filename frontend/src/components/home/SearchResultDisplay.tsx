import ReactMarkdown from 'react-markdown'
import type { SearchResult } from '../../types'
import { FileText, Sparkles } from 'lucide-react'

interface SearchResultDisplayProps {
  result: SearchResult
}

export function SearchResultDisplay({ result }: SearchResultDisplayProps) {
  return (
    <div className="w-full mt-6 animate-slide-in-up">
      <div className="bg-[var(--bg-elevated)] border border-[var(--border-primary)] rounded-2xl overflow-hidden shadow-lg">
        
        <div className="p-6 border-b border-[var(--border-secondary)] bg-[var(--bg-secondary)] flex items-center gap-3">
          <Sparkles className="text-[var(--accent-primary)]" size={24} />
          <h3 className="text-xl font-bold text-white">AI Answer</h3>
        </div>
        
        <div className="p-8">
          <div className="prose prose-invert prose-p:leading-relaxed max-w-none mb-10 text-[var(--text-primary)]">
            <ReactMarkdown>{result.answer}</ReactMarkdown>
          </div>
          
          {result.top_matches && result.top_matches.length > 0 && (
            <div className="mt-8 pt-8 border-t border-[var(--border-secondary)]">
              <h4 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4">Sources</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {result.top_matches.map((match, i) => (
                  <div key={i} className="bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-xl p-4 flex flex-col gap-2 shadow-sm">
                    <div className="flex items-center gap-2 text-[var(--accent-primary)]">
                      <FileText size={16} />
                      <span className="text-sm font-medium truncate text-white" title={match.document}>{match.document}</span>
                    </div>
                    <p className="text-xs text-[var(--text-secondary)] line-clamp-3 italic">"{match.content}"</p>
                    <div className="mt-auto pt-2 flex justify-end">
                      <span className="text-[10px] text-[var(--text-muted)] font-mono">
                        {(match.score * 100).toFixed(0)}% match
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
