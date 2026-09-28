import { NavLink } from 'react-router-dom'
import { Home, Library, Layers, Settings, FileText } from 'lucide-react'
import { useDocuments } from '../../context/DocumentContext'

export function Sidebar() {
  const { documents } = useDocuments()
  const recentDocs = [...documents].sort((a, b) => b.id - a.id).slice(0, 4)

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition-all duration-200 ${
      isActive
        ? 'bg-[rgba(59,130,246,0.12)] !text-[#93C5FD] font-semibold border border-[rgba(59,130,246,0.3)] shadow-[inset_0_0_12px_rgba(59,130,246,0.12)]'
        : '!text-[#8B93A7] hover:bg-[#12161F] hover:!text-[#F2F4F8] border border-transparent'
    }`

  return (
    <aside className="hidden md:flex flex-col w-[200px] flex-shrink-0 bg-[#070A11] border-r border-[#1C2233] h-screen sticky top-0 z-20 select-none">
      {/* Brand Header */}
      <div className="p-4 pb-3 flex items-center gap-2.5 border-b border-[#1C2233]/60">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8] flex items-center justify-center text-white font-bold text-[11px] shadow-[0_0_12px_rgba(59,130,246,0.35)] flex-shrink-0 tracking-tight">
          SB
        </div>
        <div className="min-w-0">
          <span className="font-bold text-sm text-[#F2F4F8] tracking-tight block truncate">
            SecondBrain
          </span>
        </div>
      </div>
      
      {/* Navigation Links */}
      <nav className="flex-1 px-2.5 py-3 flex flex-col gap-5 overflow-y-auto">
        <div className="flex flex-col gap-1">
          <NavLink to="/" className={navLinkClass} end>
            <Home size={16} />
            <span>Home</span>
          </NavLink>
          
          <NavLink to="/library" className={navLinkClass}>
            <Library size={16} />
            <span>Library</span>
          </NavLink>
          
          <NavLink to="/flashcards" className={navLinkClass}>
            <Layers size={16} />
            <span>Flashcards</span>
          </NavLink>
        </div>

        {/* Recent Materials Section */}
        {recentDocs.length > 0 && (
          <div className="flex flex-col gap-1 pt-3 border-t border-[#1C2233]">
            <h3 className="px-3 text-[10px] font-mono font-semibold text-[#545C70] uppercase tracking-wider mb-1">
              Recent
            </h3>
            {recentDocs.map(doc => (
              <NavLink
                key={doc.id}
                to={`/library/${doc.id}/summary`}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-[#8B93A7] hover:bg-[#12161F] hover:text-[#F2F4F8] transition-all duration-200 group border border-transparent"
                title={doc.filename}
              >
                <FileText size={13} className="text-[#545C70] group-hover:text-[#93C5FD] transition-colors flex-shrink-0" />
                <span className="truncate">{doc.filename}</span>
              </NavLink>
            ))}
          </div>
        )}
      </nav>
      
      {/* Settings Footer */}
      <div className="p-2.5 mt-auto border-t border-[#1C2233]">
        <NavLink to="/settings" className={navLinkClass}>
          <Settings size={16} />
          <span>Settings</span>
        </NavLink>
      </div>
    </aside>
  )
}
