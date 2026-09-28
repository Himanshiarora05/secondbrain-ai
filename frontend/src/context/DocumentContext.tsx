import { createContext, useContext, useState, useCallback } from 'react'
import type { ReactNode } from 'react'
import { getDocuments as fetchDocsApi } from '../api/client'
import type { DocumentItem } from '../types'

interface DocumentContextType {
  documents: DocumentItem[]
  isLoading: boolean
  error: string | null
  setInitialDocuments: (docs: DocumentItem[]) => void
  refreshDocuments: () => Promise<DocumentItem[]>
}

const DocumentContext = createContext<DocumentContextType | null>(null)

export function DocumentProvider({ children }: { children: ReactNode }) {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const setInitialDocuments = useCallback((docs: DocumentItem[]) => {
    setDocuments(docs)
    setIsLoading(false)
  }, [])

  const refreshDocuments = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const docs = await fetchDocsApi()
      setDocuments(docs)
      return docs
    } catch (err: any) {
      const msg = err?.message || 'Failed to fetch documents'
      setError(msg)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  return (
    <DocumentContext.Provider
      value={{
        documents,
        isLoading,
        error,
        setInitialDocuments,
        refreshDocuments,
      }}
    >
      {children}
    </DocumentContext.Provider>
  )
}

export function useDocuments() {
  const context = useContext(DocumentContext)
  if (!context) {
    throw new Error('useDocuments must be used within a DocumentProvider')
  }
  return context
}
