import { useState } from 'react'
import type { ReactNode } from 'react'
import { Eye, EyeOff } from 'lucide-react'

// Page frame shared by login, sign-up and the password reset pages.
export function AuthShell({ title, subtitle, children, footer }: {
  title: string
  subtitle: string
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#05070C] px-4 py-10">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="flex flex-col items-center mb-8 text-center">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8] flex items-center justify-center text-white font-black text-xl tracking-tight shadow-[0_0_30px_rgba(59,130,246,0.35)]">
            SB
          </div>
          <h1 className="mt-5 text-2xl font-bold text-white tracking-tight">{title}</h1>
          <p className="mt-1.5 text-sm text-[#A1A1AA]">{subtitle}</p>
        </div>
        <div className="p-6 sm:p-7 rounded-3xl bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
          {children}
        </div>
        {footer && <div className="mt-6 text-center text-xs text-[#A1A1AA]">{footer}</div>}
      </div>
    </div>
  )
}

export const authInputClass =
  'w-full bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.1)] rounded-xl px-4 py-3 text-sm text-white placeholder-[#5C5C6E] focus:outline-none focus:border-[rgba(59,130,246,0.5)] focus:shadow-[0_0_20px_rgba(59,130,246,0.12)] transition-all duration-200'

export const authButtonClass =
  'w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200'

export const authLinkClass = 'font-semibold text-[#93C5FD] hover:text-[#BFDBFE] underline underline-offset-2'

// Password field with a show/hide button.
export function PasswordField({ id, label, value, onChange, autoComplete, hint, labelAside }: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  autoComplete: 'current-password' | 'new-password'
  hint?: string
  labelAside?: ReactNode
}) {
  const [visible, setVisible] = useState(false)
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label htmlFor={id} className="block text-xs font-medium text-[#D1D5DB]">{label}</label>
        {labelAside}
      </div>
      <div className="relative">
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          autoComplete={autoComplete}
          required
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`${authInputClass} pr-11`}
          aria-describedby={hint ? `${id}-hint` : undefined}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute inset-y-0 right-0 px-3.5 flex items-center text-[#71717A] hover:text-white transition-colors"
          aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
        >
          {visible ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
      {hint && <p id={`${id}-hint`} className="mt-1.5 text-[11px] text-[#71717A]">{hint}</p>}
    </div>
  )
}
