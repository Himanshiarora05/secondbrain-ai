import { useEffect, useMemo, useState } from 'react'
import { useParams, useLocation, Link } from 'react-router-dom'
import {
  ArrowLeft,
  AlertCircle,
  CheckCircle2,
  XCircle,
  MinusCircle,
  ExternalLink,
  RefreshCw,
  RotateCcw,
  ListChecks,
  Layers,
  ChevronRight,
  Trophy,
} from 'lucide-react'
import { getDocuments, getMergedSet, getQuiz, generateQuiz, submitQuizAttempt } from '../api/client'
import type { QuizOwner } from '../api/client'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { sourceBadge, MERGED_BADGE_STYLE } from '../components/library/sourceBadge'
import { MergedSetMembers, MergedSetNotices } from '../components/library/MergedSetHeader'
import { StudyTabs } from '../components/library/StudyTabs'
import type { DocumentItem, MergedSet, Quiz, QuizAttempt, QuizQuestion, QuizState } from '../types'

const QUESTION_COUNT = 10
const LETTERS = ['A', 'B', 'C', 'D']
const OPTION_KEYS: Record<string, number> = { '1': 0, '2': 1, '3': 2, '4': 3, a: 0, b: 1, c: 2, d: 3 }

// The API's times are UTC without a zone.
function formatWhen(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(/(Z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : `${iso}Z`)
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function scoreMessage(score: number, total: number): string {
  const ratio = total ? score / total : 0
  if (ratio >= 0.9) return 'Excellent. You know this material well.'
  if (ratio >= 0.7) return 'Good work. Review the questions you missed.'
  if (ratio >= 0.5) return 'Getting there. The explanations below show what to revisit.'
  return 'Keep studying. Go over the cited parts of the material, then try again.'
}

function Citation({ question }: { question: QuizQuestion }) {
  if (!question.source_label) return null
  return question.source_url ? (
    <a
      href={question.source_url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 min-w-0 text-[11px] font-mono text-[#34D399] hover:text-[#6EE7B7] hover:underline transition-colors"
      title={`Open the source: ${question.source_url}`}
    >
      <span className="truncate">Source: {question.source_label}</span>
      <ExternalLink size={11} className="flex-shrink-0" />
    </a>
  ) : (
    <span className="text-[11px] font-mono text-[#34D399] truncate">Source: {question.source_label}</span>
  )
}

// With `merged`, the quiz is a merged set's (route /library/merged/:setId/quiz).
export function QuizPage({ merged = false }: { merged?: boolean }) {
  const params = useParams<{ documentId?: string; setId?: string }>()
  const rawId = merged ? params.setId : params.documentId
  const idNum = rawId ? parseInt(rawId, 10) : NaN
  const owner = useMemo<QuizOwner>(() => ({ kind: merged ? 'merged' : 'document', id: idNum }), [merged, idNum])
  const location = useLocation()
  const reopened = merged && Boolean((location.state as { reopened?: boolean } | null)?.reopened)

  const [document, setDocument] = useState<DocumentItem | null>(null)
  const [mergedSet, setMergedSet] = useState<MergedSet | null>(null)
  const [quiz, setQuiz] = useState<Quiz | null>(null)
  const [attempts, setAttempts] = useState<QuizAttempt[]>([])
  // Answers given so far, in question order (null = skipped).
  const [answers, setAnswers] = useState<(number | null)[]>([])
  const [index, setIndex] = useState(0)
  // The current question has been answered and its explanation is showing.
  const [revealed, setRevealed] = useState(false)
  const [done, setDone] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [savedAttemptId, setSavedAttemptId] = useState<number | null>(null)

  const startQuiz = (next: Quiz | null) => {
    setQuiz(next)
    setAnswers([])
    setIndex(0)
    setRevealed(false)
    setDone(false)
    setSaving(false)
    setSaveError(null)
    setSavedAttemptId(null)
  }

  const applyState = (state: QuizState) => {
    setAttempts(state.attempts)
    startQuiz(state.quiz)
  }

  useEffect(() => {
    if (isNaN(idNum)) {
      setError(merged ? 'Invalid merged set ID' : 'Invalid document ID')
      setIsLoading(false)
      return
    }
    let isMounted = true

    const load = async () => {
      setIsLoading(true)
      setError(null)
      try {
        if (merged) {
          const set = await getMergedSet(idNum)
          if (isMounted) setMergedSet(set)
        } else {
          const found = (await getDocuments()).find((d) => d.id === idNum)
          if (isMounted && found) setDocument(found)
        }
        const state = await getQuiz(owner)
        // Like summaries and flashcards: the first visit makes one.
        const ready = state.quiz ? state : await generateQuiz(owner, QUESTION_COUNT)
        if (isMounted) applyState(ready)
      } catch (err: any) {
        if (isMounted) setError(err.message || 'Failed to load the quiz')
      } finally {
        if (isMounted) setIsLoading(false)
      }
    }

    load()
    return () => {
      isMounted = false
    }
  }, [idNum, merged, owner])

  const questions = quiz?.questions ?? []
  const current = questions[index]
  const cannotRegenerate = merged && mergedSet !== null && mergedSet.documents.length < 2
  const score = answers.filter((a, i) => questions[i] && a === questions[i].correct_index).length
  const best = attempts.length ? Math.max(...attempts.map((a) => (a.total ? a.score / a.total : 0))) : null

  const saveAttempt = async (final: (number | null)[]) => {
    if (!quiz) return
    setSaving(true)
    setSaveError(null)
    try {
      const res = await submitQuizAttempt(owner, quiz.id, final)
      setAttempts(res.attempts)
      setSavedAttemptId(res.attempt.id)
    } catch (err: any) {
      setSaveError(err.message || 'Failed to save your score')
    } finally {
      setSaving(false)
    }
  }

  const advance = (list: (number | null)[]) => {
    if (index < questions.length - 1) {
      setIndex(index + 1)
      setRevealed(false)
    } else {
      setDone(true)
      saveAttempt(list)
    }
  }

  const choose = (option: number) => {
    if (!current || revealed) return
    setAnswers((prev) => [...prev.slice(0, index), option])
    setRevealed(true)
  }

  const skip = () => {
    if (!current || revealed) return
    const next = [...answers.slice(0, index), null]
    setAnswers(next)
    advance(next)
  }

  const handleNewQuiz = async () => {
    if (isNaN(idNum) || cannotRegenerate || isGenerating) return
    if (answers.length > 0 && !done && !window.confirm('Start a new quiz? Your answers so far won\'t be saved.')) return
    setIsGenerating(true)
    setError(null)
    try {
      applyState(await generateQuiz(owner, QUESTION_COUNT))
    } catch (err: any) {
      setError(err.message || 'Failed to generate the quiz')
    } finally {
      setIsGenerating(false)
    }
  }

  // Keys: 1-4 or A-D to answer, Enter / → for the next question.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isLoading || isGenerating || done || !current || e.ctrlKey || e.metaKey || e.altKey) return
      if (!revealed && OPTION_KEYS[e.key.toLowerCase()] !== undefined) {
        e.preventDefault()
        choose(OPTION_KEYS[e.key.toLowerCase()])
      } else if (revealed && (e.key === 'Enter' || e.key === 'ArrowRight')) {
        // preventDefault also stops Enter from clicking a focused button.
        e.preventDefault()
        advance(answers)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  })

  const badge = merged
    ? {
        icon: <Layers size={14} className="text-[#C4B5FD]" />,
        label: `MERGED · ${mergedSet?.documents.length ?? '…'} ${mergedSet?.documents.length === 1 ? 'SOURCE' : 'SOURCES'}`,
        style: MERGED_BADGE_STYLE,
      }
    : sourceBadge(document?.source_type || 'pdf')
  const title = merged ? mergedSet?.name ?? `Merged set #${idNum}` : document ? document.filename : `Document #${idNum}`
  const chosen = answers[index]

  return (
    <div className="flex flex-col w-full max-w-4xl mx-auto animate-fade-in pb-16 min-w-0">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/library"
          className="inline-flex items-center gap-2 text-xs font-medium text-[#A1A1AA] hover:text-white transition-all duration-200 px-3.5 py-2 rounded-xl bg-[rgba(255,255,255,0.03)] backdrop-blur-md border border-[rgba(255,255,255,0.08)] hover:border-[rgba(59,130,246,0.3)] hover:bg-[rgba(255,255,255,0.06)]"
        >
          <ArrowLeft size={14} />
          <span>Back to Library</span>
        </Link>
        {!isNaN(idNum) && <StudyTabs id={idNum} merged={merged} current="quiz" />}
      </div>

      {/* Header Panel */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-7 md:p-8 rounded-3xl bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] shadow-[0_8px_32px_rgba(0,0,0,0.5)] mb-8">
        <div className="flex items-start sm:items-center gap-4 min-w-0">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#3B82F6]/20 to-[#1D4ED8]/20 border border-[rgba(59,130,246,0.35)] text-[#93C5FD] flex items-center justify-center flex-shrink-0 shadow-[0_0_15px_rgba(59,130,246,0.2)]">
            <ListChecks size={22} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-[rgba(59,130,246,0.12)] text-[#93C5FD] font-mono font-medium border border-[rgba(59,130,246,0.25)]">
                Quiz
              </span>
              <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-md flex items-center gap-1.5 ${badge.style}`}>
                {badge.icon}
                <span>{badge.label}</span>
              </span>
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight truncate max-w-md" title={title}>
              {title}
            </h1>
            {mergedSet && <MergedSetMembers set={mergedSet} page="quiz" />}
            {quiz && !isLoading && (
              <p className="text-xs text-[#A1A1AA] mt-1 font-mono">
                {questions.length} multiple-choice questions
                {best !== null && (
                  <span className="text-[#34D399]">
                    {' '}· best {Math.round(best * 100)}% over {attempts.length} {attempts.length === 1 ? 'attempt' : 'attempts'}
                  </span>
                )}
              </p>
            )}
          </div>
        </div>

        {quiz && !isLoading && (
          <button
            onClick={handleNewQuiz}
            disabled={isGenerating || cannotRegenerate}
            className="flex items-center gap-1.5 px-4 py-2.5 text-xs font-semibold rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] hover:brightness-110 text-white transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] disabled:opacity-50 disabled:cursor-not-allowed sm:self-center self-start"
            title={cannotRegenerate ? 'A merged set needs at least 2 documents' : 'Generate 10 new questions with AI (past scores are kept)'}
          >
            <RefreshCw size={14} className={isGenerating ? 'animate-spin' : ''} />
            <span>{isGenerating ? 'Generating...' : 'New quiz'}</span>
          </button>
        )}
      </div>

      {mergedSet && quiz && !isLoading && (
        <MergedSetNotices set={mergedSet} what="quiz" stale={quiz.stale} reopened={reopened} />
      )}

      <div className="p-4 sm:p-8 md:p-10 rounded-3xl bg-[rgba(255,255,255,0.03)] backdrop-blur-xl border border-[rgba(255,255,255,0.08)] shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col min-h-[480px]">
        {isLoading || isGenerating ? (
          <div className="flex flex-col items-center justify-center py-20 text-center my-auto">
            <LoadingSpinner size={44} className="mb-4 text-[#3B82F6]" />
            <h3 className="text-base font-semibold text-white mb-1.5">Preparing Your Quiz</h3>
            <p className="text-xs text-[#A1A1AA] max-w-sm">
              {merged
                ? 'Writing questions from every document in the set, each citing its source. Large sets can take a minute...'
                : 'Writing multiple-choice questions from across the material, each citing where its answer comes from...'}
            </p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-12 text-center my-auto">
            <div className="w-14 h-14 rounded-full bg-[rgba(248,113,113,0.15)] flex items-center justify-center text-[#F87171] mb-4 border border-[rgba(248,113,113,0.25)] shadow-[0_0_20px_rgba(248,113,113,0.15)]">
              <AlertCircle size={28} />
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Couldn't Make the Quiz</h3>
            <p className="text-xs text-[#A1A1AA] max-w-md mb-6">{error}</p>
            {!cannotRegenerate && (
              <button
                onClick={handleNewQuiz}
                className="px-5 py-2.5 bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold rounded-xl transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110"
              >
                Try Again
              </button>
            )}
          </div>
        ) : !quiz || questions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center my-auto">
            <ListChecks size={36} className="text-[#5C5C6E] mb-3" />
            <h3 className="text-base font-semibold text-white mb-1">No Quiz Yet</h3>
            <p className="text-xs text-[#A1A1AA] max-w-sm mb-6">
              Generate {QUESTION_COUNT} multiple-choice questions to test yourself on this {merged ? 'merged set' : 'document'}.
            </p>
            {!cannotRegenerate && (
              <button
                onClick={handleNewQuiz}
                className="px-5 py-2.5 bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold rounded-xl transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110"
              >
                Generate Quiz
              </button>
            )}
          </div>
        ) : done ? (
          <QuizResults
            questions={questions}
            answers={answers}
            score={score}
            attempts={attempts}
            quizId={quiz.id}
            saving={saving}
            saveError={saveError}
            savedAttemptId={savedAttemptId}
            onRetrySave={() => saveAttempt(answers)}
            onRetake={() => startQuiz(quiz)}
            onNewQuiz={cannotRegenerate ? undefined : handleNewQuiz}
          />
        ) : (
          <div className="w-full flex flex-col">
            {/* Progress */}
            <div className="w-full mb-7 flex items-center justify-between gap-4 text-xs text-[#A1A1AA]">
              <span className="font-mono font-medium text-white whitespace-nowrap">
                Question {index + 1} of {questions.length}
              </span>
              <div className="flex-1 max-w-72 h-2.5 bg-[rgba(255,255,255,0.05)] rounded-full overflow-hidden border border-[rgba(255,255,255,0.08)]">
                <div
                  className="h-full bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] transition-all duration-300 rounded-full shadow-[0_0_12px_rgba(59,130,246,0.5)]"
                  style={{ width: `${((index + (revealed ? 1 : 0)) / questions.length) * 100}%` }}
                />
              </div>
              <span className="font-mono text-[11px] text-[#34D399] whitespace-nowrap">{score} correct</span>
            </div>

            <h2 className="text-lg sm:text-xl font-semibold text-white leading-relaxed tracking-tight mb-6">
              {current.question}
            </h2>

            <div className="flex flex-col gap-3" role="group" aria-label="Answer options">
              {current.options.map((option, i) => {
                const isRight = i === current.correct_index
                const isChosen = i === chosen
                const style = !revealed
                  ? 'border-[rgba(255,255,255,0.1)] bg-[rgba(255,255,255,0.03)] hover:border-[rgba(59,130,246,0.45)] hover:bg-[rgba(59,130,246,0.08)] text-[#E4E4E7]'
                  : isRight
                    ? 'border-[rgba(52,211,153,0.55)] bg-[rgba(52,211,153,0.12)] text-white'
                    : isChosen
                      ? 'border-[rgba(248,113,113,0.55)] bg-[rgba(248,113,113,0.12)] text-white'
                      : 'border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] text-[#71717A]'
                return (
                  <button
                    key={`${current.id}-${i}`}
                    onClick={() => choose(i)}
                    disabled={revealed}
                    className={`flex items-start gap-3 w-full text-left px-4 py-3.5 rounded-2xl border text-sm transition-all duration-200 disabled:cursor-default ${style}`}
                  >
                    <span
                      className={`flex-shrink-0 w-6 h-6 rounded-lg flex items-center justify-center text-[11px] font-mono font-bold border ${
                        revealed && isRight
                          ? 'border-[#34D399] text-[#34D399]'
                          : revealed && isChosen
                            ? 'border-[#F87171] text-[#F87171]'
                            : 'border-[rgba(255,255,255,0.15)] text-[#A1A1AA]'
                      }`}
                    >
                      {LETTERS[i]}
                    </span>
                    <span className="flex-1 min-w-0 leading-relaxed pt-0.5">{option}</span>
                    {revealed && isRight && <CheckCircle2 size={18} className="flex-shrink-0 text-[#34D399] mt-0.5" />}
                    {revealed && isChosen && !isRight && <XCircle size={18} className="flex-shrink-0 text-[#F87171] mt-0.5" />}
                  </button>
                )
              })}
            </div>

            <div className="mt-6 min-h-[120px]">
              {revealed ? (
                <div
                  role="status"
                  className={`p-4 rounded-2xl border ${
                    chosen === current.correct_index
                      ? 'bg-[rgba(52,211,153,0.08)] border-[rgba(52,211,153,0.3)]'
                      : 'bg-[rgba(248,113,113,0.08)] border-[rgba(248,113,113,0.3)]'
                  }`}
                >
                  <p className={`text-sm font-semibold mb-1.5 ${chosen === current.correct_index ? 'text-[#34D399]' : 'text-[#F87171]'}`}>
                    {chosen === current.correct_index ? 'Correct!' : `Not quite. The answer is ${LETTERS[current.correct_index]}.`}
                  </p>
                  {current.explanation && <p className="text-sm text-[#D4D4D8] leading-relaxed">{current.explanation}</p>}
                  <div className="mt-2.5 flex">
                    <Citation question={current} />
                  </div>
                </div>
              ) : (
                <p className="text-xs font-mono text-[#5C5C6E] text-center pt-4">
                  Pick an answer (keys 1–4 or A–D)
                </p>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 mt-4">
              {!revealed ? (
                <button
                  onClick={skip}
                  className="px-5 py-2.5 rounded-xl bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] text-[#A1A1AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.15)] transition-all duration-200 text-xs font-medium"
                  title="Skip this question (counts as wrong)"
                >
                  Skip
                </button>
              ) : (
                <button
                  onClick={() => advance(answers)}
                  className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] text-white text-xs font-semibold shadow-[0_0_20px_rgba(59,130,246,0.35)] hover:brightness-110 transition-all duration-200"
                  title="Enter"
                >
                  <span>{index < questions.length - 1 ? 'Next question' : 'See your score'}</span>
                  <ChevronRight size={15} />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

interface QuizResultsProps {
  questions: QuizQuestion[]
  answers: (number | null)[]
  score: number
  attempts: QuizAttempt[]
  quizId: number
  saving: boolean
  saveError: string | null
  savedAttemptId: number | null
  onRetrySave: () => void
  onRetake: () => void
  onNewQuiz?: () => void
}

function QuizResults({
  questions,
  answers,
  score,
  attempts,
  quizId,
  saving,
  saveError,
  savedAttemptId,
  onRetrySave,
  onRetake,
  onNewQuiz,
}: QuizResultsProps) {
  const total = questions.length
  const percent = total ? Math.round((score / total) * 100) : 0
  return (
    <div className="w-full flex flex-col">
      {/* Score */}
      <div className="flex flex-col items-center text-center pt-2 pb-8 border-b border-[rgba(255,255,255,0.08)]">
        <div className="w-14 h-14 rounded-full bg-[rgba(59,130,246,0.15)] border border-[rgba(59,130,246,0.3)] text-[#93C5FD] flex items-center justify-center mb-4">
          <Trophy size={26} />
        </div>
        <p className="text-4xl font-bold text-white tracking-tight">
          {score} <span className="text-[#71717A] text-2xl font-semibold">/ {total}</span>
        </p>
        <p className="text-sm font-mono text-[#93C5FD] mt-1">{percent}%</p>
        <p className="text-sm text-[#A1A1AA] mt-3 max-w-md">{scoreMessage(score, total)}</p>
        <p className={`text-xs font-mono mt-3 ${saveError ? 'text-[#F87171]' : 'text-[#71717A]'}`} role="status">
          {saving ? 'Saving your score...' : saveError ? (
            <>
              Couldn't save this attempt: {saveError}{' '}
              <button onClick={onRetrySave} className="underline hover:text-white">Retry</button>
            </>
          ) : savedAttemptId ? 'Score saved' : ''}
        </p>
        <div className="flex items-center gap-3 mt-6">
          <button
            onClick={onRetake}
            className="flex items-center gap-1.5 px-5 py-2.5 text-xs font-medium rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] text-[#D4D4D8] hover:text-white hover:bg-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.15)] transition-all duration-200"
          >
            <RotateCcw size={14} />
            <span>Retake this quiz</span>
          </button>
          {onNewQuiz && (
            <button
              onClick={onNewQuiz}
              className="flex items-center gap-1.5 px-5 py-2.5 text-xs font-semibold rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#1D4ED8] hover:brightness-110 text-white transition-all duration-200 shadow-[0_0_20px_rgba(59,130,246,0.35)]"
            >
              <RefreshCw size={14} />
              <span>New questions</span>
            </button>
          )}
        </div>
      </div>

      {/* Review */}
      <h3 className="text-sm font-semibold text-white mt-8 mb-4">Review your answers</h3>
      <ol className="flex flex-col gap-3">
        {questions.map((q, i) => {
          const chosen = answers[i] ?? null
          const right = chosen === q.correct_index
          return (
            <li
              key={q.id}
              className={`p-4 rounded-2xl border ${
                right ? 'border-[rgba(52,211,153,0.25)] bg-[rgba(52,211,153,0.05)]' : 'border-[rgba(248,113,113,0.25)] bg-[rgba(248,113,113,0.05)]'
              }`}
            >
              <div className="flex items-start gap-2.5">
                {right ? (
                  <CheckCircle2 size={17} className="flex-shrink-0 text-[#34D399] mt-0.5" aria-label="Correct" />
                ) : chosen === null ? (
                  <MinusCircle size={17} className="flex-shrink-0 text-[#A1A1AA] mt-0.5" aria-label="Skipped" />
                ) : (
                  <XCircle size={17} className="flex-shrink-0 text-[#F87171] mt-0.5" aria-label="Wrong" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-white leading-relaxed">
                    <span className="font-mono text-[#71717A] mr-1.5">{i + 1}.</span>
                    {q.question}
                  </p>
                  <div className="mt-2 flex flex-col gap-1 text-xs leading-relaxed">
                    {!right && (
                      <p className="text-[#FCA5A5]">
                        Your answer: {chosen === null ? 'skipped' : `${LETTERS[chosen]}. ${q.options[chosen]}`}
                      </p>
                    )}
                    <p className="text-[#6EE7B7]">
                      Correct answer: {LETTERS[q.correct_index]}. {q.options[q.correct_index]}
                    </p>
                    {q.explanation && <p className="text-[#A1A1AA]">{q.explanation}</p>}
                  </div>
                  <div className="mt-2 flex">
                    <Citation question={q} />
                  </div>
                </div>
              </div>
            </li>
          )
        })}
      </ol>

      {/* History */}
      {attempts.length > 0 && (
        <>
          <h3 className="text-sm font-semibold text-white mt-8 mb-3">Past attempts</h3>
          <ul className="flex flex-col divide-y divide-[rgba(255,255,255,0.06)] rounded-2xl border border-[rgba(255,255,255,0.08)] overflow-hidden">
            {attempts.map((a) => {
              const pct = a.total ? Math.round((a.score / a.total) * 100) : 0
              return (
                <li
                  key={a.id}
                  className={`flex items-center gap-4 px-4 py-2.5 text-xs ${a.id === savedAttemptId ? 'bg-[rgba(59,130,246,0.08)]' : ''}`}
                >
                  <span className="text-[#A1A1AA] font-mono whitespace-nowrap">{formatWhen(a.created_at)}</span>
                  <div className="flex-1 h-1.5 bg-[rgba(255,255,255,0.05)] rounded-full overflow-hidden min-w-[40px]">
                    <div className="h-full bg-[#3B82F6] rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="font-mono text-white whitespace-nowrap">
                    {a.score}/{a.total}
                  </span>
                  <span className="text-[#71717A] whitespace-nowrap hidden sm:inline">
                    {a.id === savedAttemptId ? 'just now' : a.quiz_id === quizId ? 'this quiz' : 'earlier quiz'}
                  </span>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </div>
  )
}
