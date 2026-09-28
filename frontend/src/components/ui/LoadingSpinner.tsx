import { Loader2 } from 'lucide-react'

export function LoadingSpinner({ size = 24, className = '' }: { size?: number, className?: string }) {
  return <Loader2 size={size} className={`animate-spin text-[var(--accent-primary)] ${className}`} />
}
