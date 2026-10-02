import { FileText, Presentation, FileEdit, Video, Globe, Image as ImageIcon } from 'lucide-react'

export interface SourceBadge {
  icon: React.ReactNode
  label: string
  // Text, background and border classes for the small badge.
  style: string
  // Background for a larger icon tile.
  bgColor: string
}

// Icon, label and colours for a document's source type.
export function sourceBadge(type?: string | null, iconSize = 14): SourceBadge {
  switch (type) {
    case 'pptx':
      return {
        icon: <Presentation size={iconSize} className="text-[#FBBF24]" />,
        label: 'PPTX',
        style: 'text-[#FBBF24] bg-[rgba(251,191,36,0.2)] border border-[rgba(251,191,36,0.3)]',
        bgColor: 'bg-[rgba(251,191,36,0.15)]',
      }
    case 'docx':
      return {
        icon: <FileEdit size={iconSize} className="text-[#60A5FA]" />,
        label: 'DOCX',
        style: 'text-[#60A5FA] bg-[rgba(96,165,250,0.2)] border border-[rgba(96,165,250,0.3)]',
        bgColor: 'bg-[rgba(96,165,250,0.15)]',
      }
    case 'youtube':
      return {
        icon: <Video size={iconSize} className="text-[#F87171]" />,
        label: 'YOUTUBE',
        style: 'text-[#F87171] bg-[rgba(248,113,113,0.2)] border border-[rgba(248,113,113,0.3)]',
        bgColor: 'bg-[rgba(248,113,113,0.15)]',
      }
    case 'website':
      return {
        icon: <Globe size={iconSize} className="text-[#22D3EE]" />,
        label: 'WEB',
        style: 'text-[#22D3EE] bg-[rgba(34,211,238,0.2)] border border-[rgba(34,211,238,0.3)]',
        bgColor: 'bg-[rgba(34,211,238,0.15)]',
      }
    case 'image':
      return {
        icon: <ImageIcon size={iconSize} className="text-[#34D399]" />,
        label: 'IMAGE',
        style: 'text-[#34D399] bg-[rgba(52,211,153,0.2)] border border-[rgba(52,211,153,0.3)]',
        bgColor: 'bg-[rgba(52,211,153,0.15)]',
      }
    case 'pdf':
    default:
      return {
        icon: <FileText size={iconSize} className="text-[#FB7185]" />,
        label: 'PDF',
        style: 'text-[#FB7185] bg-[rgba(251,113,133,0.2)] border border-[rgba(251,113,133,0.3)]',
        bgColor: 'bg-[rgba(251,113,133,0.15)]',
      }
  }
}

// Style for a merged set, which mixes source types.
export const MERGED_BADGE_STYLE = 'text-[#C4B5FD] bg-[rgba(167,139,250,0.2)] border border-[rgba(167,139,250,0.3)]'
