import { Suspense } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { LoadingSpinner } from '../ui/LoadingSpinner'

export function AppLayout() {
  return (
    <div className="flex h-screen w-full min-h-screen bg-[var(--bg-base)] overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 h-full overflow-y-auto relative">
        <div className="flex-1 w-full px-6 md:px-10 lg:px-12 py-8 flex flex-col min-h-full">
          {/* Pages are lazy-loaded (App.tsx); the sidebar stays while one loads. */}
          <Suspense
            fallback={
              <div className="flex-1 flex items-center justify-center">
                <LoadingSpinner size={36} className="text-[#3B82F6]" />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </div>
      </main>
    </div>
  )
}
