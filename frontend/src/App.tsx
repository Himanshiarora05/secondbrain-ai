import { Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { HomePage } from './pages/HomePage'
import { LibraryPage } from './pages/LibraryPage'
import { SummaryPage } from './pages/SummaryPage'
import { FlashcardPage } from './pages/FlashcardPage'
import { FlashcardsHubPage } from './pages/FlashcardsHubPage'
import { SettingsPage } from './pages/SettingsPage'
import { DocumentProvider } from './context/DocumentContext'
import { SplashScreen } from './components/common/SplashScreen'

function App() {
  return (
    <DocumentProvider>
      <SplashScreen />
      <Routes>
        <Route path="/" element={<AppLayout />}>
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
  )
}

export default App