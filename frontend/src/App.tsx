import { Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { HomePage } from './pages/HomePage'
import { LibraryPage } from './pages/LibraryPage'
import { SummaryPage } from './pages/SummaryPage'
import { FlashcardPage } from './pages/FlashcardPage'
import { FlashcardsHubPage } from './pages/FlashcardsHubPage'
import { SettingsPage } from './pages/SettingsPage'
import { AuthPage } from './pages/AuthPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { AuthProvider } from './context/AuthContext'
import { DocumentProvider } from './context/DocumentContext'
import { RequireAuth } from './components/auth/RequireAuth'
import { SplashScreen } from './components/common/SplashScreen'

function App() {
  return (
    <AuthProvider>
      <DocumentProvider>
        <Routes>
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/signup" element={<AuthPage mode="signup" />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
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
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </DocumentProvider>
    </AuthProvider>
  )
}

export default App
