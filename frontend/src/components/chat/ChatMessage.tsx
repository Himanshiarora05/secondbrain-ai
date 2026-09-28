import ReactMarkdown from 'react-markdown'
import { User, Copy, Check } from 'lucide-react'
import { useState } from 'react'
import type { ChatMessage as ChatMessageType } from '../../types'
import { SourceCard } from './SourceCard'

interface ChatMessageProps {
  message: ChatMessageType
}

export function ChatMessage({ message }: ChatMessageProps) {
  const [copied, setCopied] = useState(false)
  const isUser = message.role === 'user'

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (isUser) {
    return (
      <div className="flex w-full justify-end mb-6 animate-slide-in-up">
        <div className="flex gap-3 max-w-[85%] flex-row-reverse">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8] flex-shrink-0 flex items-center justify-center text-white text-xs font-semibold shadow-sm">
            <User size={15} />
          </div>
          <div className="bg-[var(--bg-elevated)] border border-[var(--border-primary)] rounded-2xl rounded-tr-sm p-4 text-[var(--text-primary)] shadow-sm">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex w-full justify-start mb-8 animate-slide-in-up">
      <div className="flex gap-4 max-w-full md:max-w-[85%]">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8] flex-shrink-0 flex items-center justify-center text-white font-bold text-xs mt-1 shadow-sm">
          SB
        </div>
        
        <div className="flex-1 overflow-hidden bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-2xl rounded-tl-sm p-5 shadow-sm relative group">
          <button 
            onClick={handleCopy}
            className="absolute top-3 right-3 p-1.5 rounded-md text-[var(--text-tertiary)] hover:text-white hover:bg-[var(--bg-elevated)] transition-colors opacity-0 group-hover:opacity-100"
            aria-label="Copy response"
          >
            {copied ? <Check size={16} className="text-[var(--success)]" /> : <Copy size={16} />}
          </button>

          <div className="prose prose-invert prose-p:leading-relaxed max-w-none text-[var(--text-primary)] text-sm md:text-base">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
          
          {message.sources && message.sources.length > 0 && (
            <div className="mt-6 pt-4 border-t border-[var(--border-primary)]">
              <h4 className="text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider mb-3">Sources</h4>
              <div className="flex flex-wrap gap-2">
                {message.sources.map((source, i) => (
                  <SourceCard key={i} source={source} index={i + 1} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
