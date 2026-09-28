import { useEffect, useState } from 'react'
import { getDocuments } from '../../api/client'
import { useDocuments } from '../../context/DocumentContext'

// Module-level flag so the splash screen only ever triggers once per full page load / refresh
let hasShownSplash = false

if (typeof window !== 'undefined') {
  (window as any).__resetSplash = () => {
    hasShownSplash = false
  }
}

export function SplashScreen() {
  const { setInitialDocuments } = useDocuments()
  // Decided once per mount: skip the splash if it was already shown in this page load.
  const [alreadyShown] = useState(() => {
    const forced = typeof window !== 'undefined' && window.location.search.includes('force_splash=true')
    return hasShownSplash && !forced
  })
  const [stage, setStage] = useState<'visible' | 'fading-out' | 'hidden'>(alreadyShown ? 'hidden' : 'visible')

  // Every run of this effect starts its own fade-out. React StrictMode (dev) mounts,
  // cleans up and re-runs effects; a "run only once" guard here left the splash
  // up forever, because the only gate that ran was the one its cleanup cancelled.
  useEffect(() => {
    if (alreadyShown) return
    hasShownSplash = true

    let isSubscribed = true
    const minDelayPromise = new Promise((resolve) => setTimeout(resolve, 1200))
    const maxTimeoutPromise = new Promise((resolve) => setTimeout(resolve, 5000))

    // Real fetch for documents needed by Home and Sidebar
    const realFetchPromise = getDocuments()
      .then((docs) => {
        if (isSubscribed) {
          setInitialDocuments(docs)
        }
        return docs
      })
      .catch((err) => {
        console.warn('SplashScreen initial fetch failed (backend might be down/slow):', err)
        return null
      })

    // Wait until (realFetch AND minDelay) have both finished, or fallback to maxTimeout (5s)
    const completionGate = Promise.race([
      Promise.all([realFetchPromise, minDelayPromise]),
      maxTimeoutPromise,
    ])

    completionGate.then(() => {
      if (!isSubscribed) return
      // Start fade-out transition (~450ms)
      setStage('fading-out')
      setTimeout(() => {
        if (isSubscribed) {
          setStage('hidden')
        }
      }, 450)
    })

    return () => {
      isSubscribed = false
    }
  }, [alreadyShown, setInitialDocuments])

  if (stage === 'hidden') {
    return null
  }

  return (
    <div
      id="splash-screen"
      aria-label="Loading SecondBrain AI"
      aria-live="polite"
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#05070C] select-none transition-opacity duration-450 ease-out ${
        stage === 'fading-out' ? 'opacity-0 pointer-events-none' : 'opacity-100'
      }`}
    >
      <div className="flex flex-col items-center">
        {/* Centered Logo Mark: rounded-square gradient box with SB initials */}
        <div
          id="splash-logo-box"
          className="w-20 h-20 rounded-3xl bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8] flex items-center justify-center text-white font-black text-3xl tracking-tight animate-splash-logo shadow-[0_0_35px_rgba(59,130,246,0.4)]"
        >
          SB
        </div>

        {/* Wordmark: Fades in with gradient text treatment */}
        <div className="mt-6 flex flex-col items-center animate-splash-wordmark">
          <h1
            className="text-3xl font-bold tracking-tight"
            style={{
              background: 'linear-gradient(135deg, #93C5FD 0%, #3B82F6 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            SecondBrain
          </h1>

          <div className="mt-3 flex items-center gap-2 text-xs font-mono text-[#8B93A7]">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#3B82F6] animate-pulse" />
            <span>loading your library...</span>
          </div>
        </div>
      </div>
    </div>
  )
}
