import { FileText, ExternalLink, Video, Globe } from 'lucide-react'
import type { SourceMatch } from '../../types'

interface SourceCardProps {
  source: SourceMatch
  index: number
}

export function SourceCard({ source, index }: SourceCardProps) {
  const isYouTube = Boolean(source.youtube_timestamp_url)
  const websiteUrl = source.source_type === 'website' ? source.source_url : undefined

  return (
    <div className="group relative flex items-center gap-2 bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-lg px-3 py-1.5 hover:border-[var(--accent-primary)] hover:bg-[var(--bg-hover)] transition-all">
      <span className="flex items-center justify-center w-4 h-4 rounded-full bg-[var(--accent-primary-muted)] text-[var(--accent-primary)] text-[10px] font-bold">
        {index}
      </span>
      {isYouTube ? (
        <Video size={14} className="text-red-400 flex-shrink-0" />
      ) : websiteUrl ? (
        <Globe size={14} className="text-cyan-400 flex-shrink-0" />
      ) : (
        <FileText size={14} className="text-[var(--text-secondary)] flex-shrink-0" />
      )}
      <span className="text-sm text-[var(--text-secondary)] group-hover:text-white truncate max-w-[140px]" title={source.document}>
        {source.document}
      </span>
      {source.location && (
        <span
          className="flex-shrink-0 text-[11px] font-mono text-[var(--text-secondary)] px-1.5 py-0.5 rounded bg-white/5 border border-white/10"
          title="Where in the source this match is"
        >
          {source.location}
        </span>
      )}

      {source.youtube_timestamp_url && (
        <a
          href={source.youtube_timestamp_url}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-1 inline-flex items-center gap-1 text-[11px] font-medium text-red-400 hover:text-red-300 hover:underline transition-colors px-1.5 py-0.5 rounded bg-red-500/10 border border-red-500/20"
          title="Jump to this part of the YouTube video"
          onClick={(e) => e.stopPropagation()}
        >
          <span>Jump to video</span>
          <ExternalLink size={11} />
        </a>
      )}

      {websiteUrl && (
        <a
          href={websiteUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-1 inline-flex items-center gap-1 text-[11px] font-medium text-cyan-400 hover:text-cyan-300 hover:underline transition-colors px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20"
          title={`Open the source page: ${websiteUrl}`}
          onClick={(e) => e.stopPropagation()}
        >
          <span>Open page</span>
          <ExternalLink size={11} />
        </a>
      )}

      {/* Tooltip */}
      <div className="absolute bottom-full left-0 mb-2 w-72 p-3 bg-[var(--bg-elevated)] border border-[var(--border-primary)] rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-[var(--z-tooltip)] pointer-events-none">
        <p className="text-xs text-[var(--text-secondary)] italic line-clamp-5">"{source.content}"</p>
        <div className="mt-2 flex items-center justify-between">
          {source.youtube_timestamp_url && (
            <span className="text-[10px] text-red-400 font-mono">Timestamped Video Clip</span>
          )}
          {websiteUrl && (
            <span className="text-[10px] text-cyan-400 font-mono">Web Page</span>
          )}
          <span className="text-[10px] text-[var(--accent-primary)] font-mono ml-auto">
            {(source.score * 100).toFixed(0)}% match
          </span>
        </div>
      </div>
    </div>
  )
}
