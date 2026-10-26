import { useState } from 'react'

import {
  ApiError,
  assessClaim,
  extractClaimReceipt,
  interpretClaimAnswer,
  reassessClaim,
} from '../../lib/api.ts'
import type {
  AssessmentState,
  ClaimAnswers,
  ClaimCitation,
  ClaimResponse,
  ClaimSlot,
  ExtractResponse,
  NextQuestion,
  ReceiptFacts,
} from '../../lib/types.ts'
import UploadPanel from '../UploadPanel.tsx'
import ClaimOutcome from './ClaimOutcome.tsx'
import { money } from './format.ts'
import PolicyPageDialog from './PolicyPageDialog.tsx'
import ReceiptFactsCard from './ReceiptFactsCard.tsx'

interface Turn {
  from: 'assistant' | 'student'
  text: string
  note?: string
}

interface Failure {
  code: string
  message: string
}

interface Attempt {
  answers: ClaimAnswers
  state: AssessmentState | null
}

/** Answers that change which policy text is searched need a fresh reading, not a re-check. */
const RETRIEVAL_SLOTS: ReadonlySet<ClaimSlot> = new Set([
  'insurer',
  'product',
  'service_date',
  'service_description',
])

const MAX_AMOUNT = 100_000

/** The student's local date, which the browser's UTC date can trail in Australia. */
function today(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function toFailure(error: unknown): Failure {
  return error instanceof ApiError
    ? { code: error.code, message: error.message }
    : { code: 'internal_error', message: 'Unexpected client error.' }
}

/** Record one answer where the server expects it; a new insurer clears the product. */
function withAnswer(answers: ClaimAnswers, question: NextQuestion, value: string): ClaimAnswers {
  const line = String(question.line_index ?? 0)
  switch (question.slot) {
    case 'insurer':
      return { ...answers, insurer_id: value, product_id: null }
    case 'product':
      return { ...answers, product_id: value }
    case 'cover_start_date':
      return { ...answers, cover_start_date: value }
    case 'has_referral':
      return { ...answers, has_referral: value === 'yes' }
    case 'service_date':
      return { ...answers, service_dates: { ...answers.service_dates, [line]: value } }
    case 'service_description':
      return {
        ...answers,
        service_descriptions: { ...answers.service_descriptions, [line]: value },
      }
    case 'benefits_used':
      return { ...answers, benefits_used: { ...answers.benefits_used, [line]: value } }
    case 'amount_paid':
      return { ...answers, amounts_paid: { ...answers.amounts_paid, [line]: value } }
  }
}

function display(question: NextQuestion, value: string): string {
  const option = question.options.find((candidate) => candidate.value === value)
  if (option !== undefined) return option.label
  return question.input === 'amount' ? money(value) : value
}

interface AnswerControlsProps {
  question: NextQuestion
  disabled: boolean
  onPick: (value: string) => void
  onType: (text: string) => void
}

/** Quick replies in the exact format the question needs, plus a box for a typed reply. */
function AnswerControls({ question, disabled, onPick, onType }: AnswerControlsProps) {
  const [picked, setPicked] = useState('')
  const [typed, setTyped] = useState('')
  const amount = Number(picked)
  const pickedValid = picked !== '' && (
    question.input === 'date'
      ? picked <= today()
      : Number.isFinite(amount) && amount >= 0 && amount <= MAX_AMOUNT
  )

  return (
    <div className="grid gap-3">
      {question.options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {question.options.map((option) => (
            <button
              key={option.value}
              type="button"
              disabled={disabled}
              onClick={() => onPick(option.value)}
              className="rounded-full border border-accent/40 bg-raised px-4 py-1.5 text-sm font-medium text-accent hover:bg-accent/5 disabled:opacity-50"
            >
              {option.label}
            </button>
          ))}
        </div>
      )}

      {(question.input === 'date' || question.input === 'amount') && (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (pickedValid) onPick(question.input === 'amount' ? amount.toFixed(2) : picked)
          }}
        >
          <input
            type={question.input === 'date' ? 'date' : 'number'}
            value={picked}
            onChange={(event) => setPicked(event.target.value)}
            max={question.input === 'date' ? today() : MAX_AMOUNT}
            min={question.input === 'date' ? undefined : 0}
            step={question.input === 'date' ? undefined : '0.01'}
            aria-label={question.prompt}
            className="rounded-lg border border-line bg-raised px-3 py-2 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
          <button
            type="submit"
            disabled={disabled || !pickedValid}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send
          </button>
        </form>
      )}

      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (typed.trim() !== '') onType(typed.trim())
        }}
      >
        <input
          type="text"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          maxLength={question.input === 'text' ? 200 : 300}
          placeholder={question.input === 'text' ? 'Describe the service' : 'Or type your answer'}
          aria-label={question.input === 'text' ? question.prompt : 'Typed answer'}
          className="min-w-0 flex-1 rounded-lg border border-line bg-raised px-3 py-2 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
        />
        <button
          type="submit"
          disabled={disabled || typed.trim() === ''}
          className="rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-surface disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  )
}

/**
 * The guided claim check. Everything the student uploads or answers lives only in this
 * component's state; the server is stateless and keeps nothing about them.
 */
export default function ClaimChat() {
  const [receipt, setReceipt] = useState<ExtractResponse | null>(null)
  const [answers, setAnswers] = useState<ClaimAnswers>({})
  const [response, setResponse] = useState<ClaimResponse | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [failure, setFailure] = useState<Failure | null>(null)
  const [failedAttempt, setFailedAttempt] = useState<Attempt | null>(null)
  const [citation, setCitation] = useState<ClaimCitation | null>(null)

  async function decide(
    facts: ReceiptFacts,
    next: ClaimAnswers,
    state: AssessmentState | null,
  ): Promise<void> {
    setBusy(next.product_id ? 'Checking your policy…' : 'Thinking…')
    setFailure(null)
    setFailedAttempt(null)
    try {
      let result: ClaimResponse
      try {
        result = state === null
          ? await assessClaim(facts, next)
          : await reassessClaim(facts, next, state)
      } catch (error) {
        // A changed receipt reading needs the full assessment again.
        if (!(error instanceof ApiError && error.code === 'stale_assessment')) throw error
        result = await assessClaim(facts, next)
      }
      setResponse(result)
      setTurns((current) => [...current, { from: 'assistant', text: result.message }])
    } catch (error) {
      setFailure(toFailure(error))
      setFailedAttempt({ answers: next, state })
    } finally {
      setBusy(null)
    }
  }

  async function read(file: File): Promise<void> {
    setBusy('Reading your receipt…')
    setFailure(null)
    let extracted: ExtractResponse
    try {
      extracted = await extractClaimReceipt(file)
    } catch (error) {
      setFailure(toFailure(error))
      setBusy(null)
      return
    }
    setReceipt(extracted)
    await decide(extracted.facts, {}, null)
  }

  async function answer(question: NextQuestion, value: string, typed?: string): Promise<void> {
    if (receipt === null || response === null) return
    const next = withAnswer(answers, question, value)
    setAnswers(next)
    setTurns((current) => [
      ...current,
      {
        from: 'student',
        text: typed ?? display(question, value),
        note: typed === undefined ? undefined : `Read as: ${display(question, value)}`,
      },
    ])
    await decide(receipt.facts, next, RETRIEVAL_SLOTS.has(question.slot) ? null : response.state)
  }

  async function answerTyped(question: NextQuestion, text: string): Promise<void> {
    if (question.input === 'text') {
      await answer(question, text)
      return
    }
    setBusy('Reading your answer…')
    setFailure(null)
    let value: string | null
    try {
      value = (await interpretClaimAnswer(question, text)).value
    } catch (error) {
      setFailure(toFailure(error))
      setBusy(null)
      return
    }
    setBusy(null)
    if (value === null) {
      setTurns((current) => [
        ...current,
        { from: 'student', text },
        { from: 'assistant', text: 'I could not match that to the question. Choose an option or try again.' },
      ])
      return
    }
    await answer(question, value, text)
  }

  async function changePolicy(): Promise<void> {
    if (receipt === null) return
    setAnswers({})
    setTurns((current) => [...current, { from: 'student', text: 'Change insurer or product' }])
    await decide(receipt.facts, {}, null)
  }

  function startOver(): void {
    setReceipt(null)
    setAnswers({})
    setResponse(null)
    setTurns([])
    setFailure(null)
    setFailedAttempt(null)
    setCitation(null)
  }

  const question = response?.stage === 'question' ? response.next_question : null

  return (
    <section className="flex flex-col gap-6">
      {receipt === null ? (
        <UploadPanel
          isProcessing={busy !== null}
          onProcess={(file) => void read(file)}
          title="Drop a health receipt here"
          actionLabel="Check my claim"
        />
      ) : (
        <ReceiptFactsCard facts={receipt.facts} issues={receipt.issues} />
      )}

      {turns.length > 0 && (
        <ol className="flex flex-col gap-3" aria-live="polite">
          {turns.map((turn, index) => (
            <li
              key={index}
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                turn.from === 'student'
                  ? 'self-end bg-accent text-white'
                  : 'self-start border border-line bg-raised'
              }`}
            >
              <p className="whitespace-pre-line">{turn.text}</p>
              {turn.note !== undefined && <p className="mt-1 text-xs opacity-80">{turn.note}</p>}
            </li>
          ))}
        </ol>
      )}

      {busy !== null && <p className="animate-pulse text-sm text-muted">{busy}</p>}

      {failure !== null && (
        <div role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">
          <p className="font-medium">{failure.code}</p>
          <p>{failure.message}</p>
          {receipt !== null && failedAttempt !== null && (
            <button
              type="button"
              onClick={() => void decide(receipt.facts, failedAttempt.answers, failedAttempt.state)}
              className="mt-2 rounded-lg border border-red-200 px-3 py-1 font-medium hover:bg-red-100"
            >
              Try again
            </button>
          )}
        </div>
      )}

      {question !== null && (
        <div className="grid gap-2">
          {!response?.message.includes(question.prompt) && (
            <p className="text-sm font-medium">{question.prompt}</p>
          )}
          <AnswerControls
            key={turns.length}
            question={question}
            disabled={busy !== null}
            onPick={(value) => void answer(question, value)}
            onType={(text) => void answerTyped(question, text)}
          />
        </div>
      )}

      {response !== null && response.lines.length > 0 && (
        <ClaimOutcome response={response} onCite={setCitation} />
      )}

      {receipt !== null && busy === null && (
        <div className="flex flex-wrap gap-3">
          {answers.insurer_id && (
            <button
              type="button"
              onClick={() => void changePolicy()}
              className="rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-raised"
            >
              Change insurer or product
            </button>
          )}
          <button
            type="button"
            onClick={startOver}
            className="rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-raised"
          >
            Check another receipt
          </button>
        </div>
      )}

      {citation !== null && (
        <PolicyPageDialog citation={citation} onClose={() => setCitation(null)} />
      )}
    </section>
  )
}
