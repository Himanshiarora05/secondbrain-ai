import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  description: string
  action?: ReactNode
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] min-h-[300px] shadow-sm">
      <div className="w-16 h-16 rounded-full bg-[var(--bg-elevated)] flex items-center justify-center text-[var(--text-secondary)] mb-6 shadow-sm">
        {icon}
      </div>
      <h3 className="text-xl font-bold text-white mb-2">{title}</h3>
      <p className="text-[var(--text-secondary)] max-w-md mb-8">{description}</p>
      {action}
    </div>
  )
}
