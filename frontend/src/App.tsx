import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { HomePage } from './pages/HomePage'
import { LoadingSpinner } from './components/ui/LoadingSpinner'
import { AuthProvider } from './context/AuthContext'
import { DocumentProvider } from './context/DocumentContext'
import { RequireAuth } from './components/auth/RequireAuth'
import { SplashScreen } from './components/common/SplashScreen'

// Every page but Home loads on first visit, so the start-up bundle stays small
// (vite.config.ts splits React itself into its own chunk). Pages inside the app
// wait in AppLayout's Suspense, sidebar intact; the public pages use PageFallback.
const LibraryPage = lazy(() => import('./pages/LibraryPage').then((m) => ({ default: m.LibraryPage })))
const SummaryPage = lazy(() => import('./pages/SummaryPage').then((m) => ({ default: m.SummaryPage })))
const FlashcardPage = lazy(() => import('./pages/FlashcardPage').then((m) => ({ default: m.FlashcardPage })))
const FlashcardsHubPage = lazy(() => import('./pages/FlashcardsHubPage').then((m) => ({ default: m.FlashcardsHubPage })))
const DueTodayPage = lazy(() => import('./pages/DueTodayPage').then((m) => ({ default: m.DueTodayPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const AuthPage = lazy(() => import('./pages/AuthPage').then((m) => ({ default: m.AuthPage })))
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage').then((m) => ({ default: m.ForgotPasswordPage })))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage').then((m) => ({ default: m.ResetPasswordPage })))

function PageFallback() {
  return (
    <div className="flex-1 flex items-center justify-center min-h-screen bg-[var(--bg-base)]">
      <LoadingSpinner size={36} className="text-[#3B82F6]" />
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <DocumentProvider>
        <Routes>
          <Route path="/login" element={<Suspense fallback={<PageFallback />}><AuthPage mode="login" /></Suspense>} />
          <Route path="/signup" element={<Suspense fallback={<PageFallback />}><AuthPage mode="signup" /></Suspense>} />
          <Route path="/forgot-password" element={<Suspense fallback={<PageFallback />}><ForgotPasswordPage /></Suspense>} />
          <Route path="/reset-password" element={<Suspense fallback={<PageFallback />}><ResetPasswordPage /></Suspense>} />
          <Route
            path="/"
            element={
              // The splash loads the signed-in user's documents, so it lives behind the check.
              <RequireAuth>
                <SplashScreen />
                <AppLayout />
              </RequireAuth>
            }
          >
            <Route index element={<HomePage />} />
            <Route path="library" element={<LibraryPage />} />
            <Route path="library/:documentId/summary" element={<SummaryPage />} />
            <Route path="library/:documentId/flashcards" element={<FlashcardPage />} />
            <Route path="library/merged/:setId/summary" element={<SummaryPage merged />} />
            <Route path="library/merged/:setId/flashcards" element={<FlashcardPage merged />} />
            <Route path="flashcards" element={<FlashcardsHubPage />} />
            <Route path="review" element={<DueTodayPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </DocumentProvider>
    </AuthProvider>
  )
}

export default App
