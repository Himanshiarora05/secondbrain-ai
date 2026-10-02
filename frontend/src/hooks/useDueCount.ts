import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { DUE_CHANGED_EVENT, getDueCount } from '../api/client'

// Number of flashcards due today across every deck, or null until known (or
// if it can't be loaded). Refreshes when a card is rated or a deck changes
// (DUE_CHANGED_EVENT), on navigation, and when the tab regains focus (the
// date may have rolled over).
export function useDueCount(): number | null {
  const [count, setCount] = useState<number | null>(null)
  const { pathname } = useLocation()

  useEffect(() => {
    let active = true
    const refresh = () => {
      getDueCount()
        .then((n) => {
          if (active) setCount(n)
        })
        .catch(() => {})
    }
    refresh()
    window.addEventListener(DUE_CHANGED_EVENT, refresh)
    window.addEventListener('focus', refresh)
    return () => {
      active = false
      window.removeEventListener(DUE_CHANGED_EVENT, refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [pathname])

  return count
}
