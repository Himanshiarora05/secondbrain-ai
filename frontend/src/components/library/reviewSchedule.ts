import { localToday } from '../../api/client'
import type { CardSchedule, ReviewGrade } from '../../types'

// Keys 1 / 2 / 3 rate the card, in the order of the Again / Good / Easy buttons.
export const GRADE_KEYS: Record<string, ReviewGrade> = { '1': 'again', '2': 'good', '3': 'easy' }

function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((Date.parse(toIso) - Date.parse(fromIso)) / 86_400_000)
}

function inDays(days: number): string {
  if (days <= 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days < 60) return `in ${days} days`
  if (days < 730) return `in ${Math.round(days / 30)} months`
  return `in ${Math.round(days / 365)} years`
}

// "New", "Due today", "Due in 6 days": where a card stands in the schedule.
export function dueLabel(card: Partial<CardSchedule>): string {
  if (!card.due_date) return 'New'
  const days = daysBetween(localToday(), card.due_date)
  if (days < 0) return 'Overdue'
  return days === 0 ? 'Due today' : `Due ${inDays(days)}`
}

// After rating: "Next review tomorrow", "Next review in 6 days".
export function nextReviewText(card: Partial<CardSchedule>): string {
  if (!card.due_date) return ''
  return `Next review ${inDays(daysBetween(localToday(), card.due_date))}`
}
