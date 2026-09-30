import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { useDocuments } from '../../context/DocumentContext'
import { LoadingSpinner } from '../ui/LoadingSpinner'

// Pages inside this need a signed-in user; others are sent to /login and
// brought back to where they were going afterwards.
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const { setInitialDocuments } = useDocuments()
  const location = useLocation()

  // Signed out (logout, or a 401 from any request): drop the previous
  // account's documents so nothing of theirs stays on screen.
  useEffect(() => {
    if (user === null) setInitialDocuments([])
  }, [user, setInitialDocuments])

  if (user === undefined) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-[#05070C]" aria-label="Checking your session">
        <LoadingSpinner size={36} className="text-[#3B82F6]" />
      </div>
    )
  }
  if (user === null) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  return <>{children}</>
}
