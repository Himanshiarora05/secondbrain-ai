import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function AppLayout() {
  return (
    <div className="flex h-screen w-full min-h-screen bg-[var(--bg-base)] overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 h-full overflow-y-auto relative">
        <div className="flex-1 w-full px-6 md:px-10 lg:px-12 py-8 flex flex-col min-h-full">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
