import { useState, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { ChatMessage as ChatMessageType } from '../types'
import { ChatMessage } from '../components/chat/ChatMessage'
import { ChatInput } from '../components/chat/ChatInput'
import { searchSecondBrain } from '../api/client'
import { Sparkles } from 'lucide-react'

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [searchParams, setSearchParams] = useSearchParams()

  // Load from session storage
  useEffect(() => {
    const saved = sessionStorage.getItem('secondbrain_chat_history')
    if (saved) {
      try {
        setMessages(JSON.parse(saved))
      } catch (e) {
        console.error('Failed to parse chat history', e)
      }
    }
  }, [])

  // Save to session storage
  useEffect(() => {
    if (messages.length > 0) {
      sessionStorage.setItem('secondbrain_chat_history', JSON.stringify(messages))
    }
  }, [messages])

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // Handle URL query
  useEffect(() => {
    const q = searchParams.get('q')
    if (q) {
      handleSendMessage(q)
      setSearchParams(new URLSearchParams()) // clear it
    }
  }, [searchParams])

  const handleSendMessage = async (content: string) => {
    const userMessage: ChatMessageType = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: Date.now()
    }
    
    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)
    
    try {
      const result = await searchSecondBrain(content)
      
      const aiMessage: ChatMessageType = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: result.answer,
        sources: result.top_matches,
        timestamp: Date.now()
      }
      
      setMessages(prev => [...prev, aiMessage])
    } catch (err) {
      const errorMessage: ChatMessageType = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: err instanceof Error ? `Error: ${err.message}` : 'Sorry, something went wrong while searching your library.',
        timestamp: Date.now()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const clearChat = () => {
    setMessages([])
    sessionStorage.removeItem('secondbrain_chat_history')
  }

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] relative animate-fade-in -mt-4">
      
      {/* Header */}
      <div className="flex justify-between items-center mb-6 px-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[var(--accent-primary-muted)] flex items-center justify-center text-[var(--accent-primary)]">
            <Sparkles size={20} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight leading-tight">AI Assistant</h1>
            <p className="text-[var(--text-tertiary)] text-xs">Search-powered · RAG active</p>
          </div>
        </div>
        {messages.length > 0 && (
          <button 
            onClick={clearChat}
            className="text-xs font-medium text-[var(--text-tertiary)] hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-[var(--bg-hover)]"
          >
            Clear chat
          </button>
        )}
      </div>

      <div className="flex-1 bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-2xl overflow-hidden flex flex-col relative shadow-lg">
        {messages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8] flex items-center justify-center text-white font-black text-xl mb-6 shadow-[0_0_20px_rgba(59,130,246,0.35)]">
              SB
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">How can I help you today?</h2>
            <p className="text-[var(--text-secondary)] max-w-md mx-auto text-sm">
              Ask questions about any of the documents indexed in your Knowledge Base. The AI will synthesize answers directly from your sources.
            </p>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6 md:p-8">
            <div className="max-w-4xl mx-auto flex flex-col">
              {messages.map(msg => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              
              {isLoading && (
                <div className="flex w-full justify-start mb-8 animate-fade-in">
                  <div className="flex gap-4 max-w-full md:max-w-[85%]">
                    <div className="w-10 h-10 rounded-xl bg-[var(--bg-active)] flex-shrink-0 flex items-center justify-center text-[var(--accent-primary)] mt-1 shadow-sm border border-[var(--border-primary)]">
                      <Sparkles size={20} className="animate-pulse" />
                    </div>
                    
                    <div className="flex-1 bg-[var(--bg-elevated)] border border-[var(--border-primary)] rounded-2xl rounded-tl-sm p-6 shadow-sm flex items-center gap-2">
                      <div className="flex space-x-1.5">
                        <div className="w-2 h-2 rounded-full bg-[var(--text-tertiary)] animate-bounce" style={{ animationDelay: '0ms' }}></div>
                        <div className="w-2 h-2 rounded-full bg-[var(--text-tertiary)] animate-bounce" style={{ animationDelay: '150ms' }}></div>
                        <div className="w-2 h-2 rounded-full bg-[var(--text-tertiary)] animate-bounce" style={{ animationDelay: '300ms' }}></div>
                      </div>
                      <span className="text-sm text-[var(--text-tertiary)] ml-2">Searching library...</span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}

        <div className="p-4 md:p-6 bg-[var(--bg-secondary)] border-t border-[var(--border-primary)] z-10">
          <div className="max-w-4xl mx-auto w-full">
            <ChatInput onSend={handleSendMessage} isLoading={isLoading} />
            <p className="text-center text-[10px] text-[var(--text-tertiary)] mt-3 tracking-wide">
              AI can make mistakes. Verify important information against the source documents.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
