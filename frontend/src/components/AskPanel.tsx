import { useState, type FormEvent } from 'react'

import { ApiError, askAssistant } from '../lib/api.ts'
import type {
  AssistantAnswer,
  AssistantGroup,
  DocumentQuery,
  DocumentSummary,
} from '../lib/types.ts'

interface AskPanelProps {
  selectedId: string | null
  onOpen: (id: string) => void
}

const EXAMPLES = [
  'Which pending invoices are blocked, and why?',
  'How much did we approve per GL account in July?',
  'Which documents needed the AI fallback?',
  'Are there any duplicates?',
] as const

/** Spell out the filter the model chose, so the reviewer can check the search itself. */
function describeQuery(query: DocumentQuery): string[] {
  if (query.intent === 'unsupported') {
    return ['not a question about stored reviews']
  }

  const parts: string[] = []
  if (query.statuses.length > 0) parts.push(`status: ${query.statuses.join(' or ')}`)
  if (query.document_types.length > 0) parts.push(`type: ${query.document_types.join(' or ')}`)
  if (query.vendor_text) parts.push(`supplier contains “${query.vendor_text}”`)
  if (query.date_from !== null || query.date_to !== null) {
    parts.push(`date: ${query.date_from ?? 'any'} to ${query.date_to ?? 'any'}`)
  }
  if (query.gl_account_codes.length > 0) parts.push(`GL: ${query.gl_account_codes.join(', ')}`)
  if (query.min_total !== null) parts.push(`total ≥ ${query.min_total}`)
  if (query.max_total !== null) parts.push(`total ≤ ${query.max_total}`)
  if (query.has_errors !== null) parts.push(query.has_errors ? 'has errors' : 'no errors')
  if (query.issue_codes.length > 0) parts.push(`issue: ${query.issue_codes.join(', ')}`)
  if (query.is_duplicate !== null) {
    parts.push(query.is_duplicate ? 'duplicates only' : 'duplicates excluded')
  }
  if (query.used_llm_fallback !== null) {
    parts.push(query.used_llm_fallback ? 'filled by AI fallback' : 'no AI fallback')
  }
  if (query.aggregate !== 'list') {
    parts.push(
      query.group_by === 'none'
        ? query.aggregate
        : `${query.aggregate} by ${query.group_by.replaceAll('_', ' ')}`,
    )
  }
  return parts.length === 0 ? ['all stored documents'] : parts
}

function describeDocument(document: DocumentSummary): string {
  const total = document.total_amount === null
    ? null
    : [document.total_amount, document.currency].filter((part) => part !== null).join(' ')
  const parts = [document.vendor_name, document.invoice_number, document.document_date, total]
    .filter((part): part is string => part !== null)
  return parts.length === 0 ? 'No supplier details extracted' : parts.join(' · ')
}

function GroupTable({ groups }: { groups: AssistantGroup[] }) {
  return (
    <div>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-3 py-2">Group</th>
              <th className="px-3 py-2">Documents</th>
              <th className="px-3 py-2">Total</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <tr key={`${group.label}-${group.currency ?? 'none'}`} className="border-t border-line">
                <td className="px-3 py-2">{group.label}</td>
                <td className="px-3 py-2">
                  {group.document_count}
                  {group.documents_without_total > 0 && (
                    <span className="text-muted"> ({group.documents_without_total} without a total)</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {group.total_amount === null
                    ? '—'
                    : `${group.total_amount} ${group.currency ?? ''}`.trim()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">
        Counts and totals are computed from stored values, not by the model.
      </p>
    </div>
  )
}

export default function AskPanel({ selectedId, onOpen }: AskPanelProps) {
  const [question, setQuestion] = useState('')
  const [isAsking, setIsAsking] = useState(false)
  const [result, setResult] = useState<AssistantAnswer | null>(null)
  const [failure, setFailure] = useState<{ code: string; message: string } | null>(null)
  const cited = new Set(result?.cited_document_ids ?? [])

  async function ask(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    const trimmed = question.trim()
    if (trimmed === '' || isAsking) {
      return
    }
    setIsAsking(true)
    setFailure(null)
    try {
      setResult(await askAssistant(trimmed))
    } catch (error) {
      setResult(null)
      setFailure(
        error instanceof ApiError
          ? { code: error.code, message: error.message }
          : { code: 'internal_error', message: 'Unexpected client error.' },
      )
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
        Ask the review history
      </h2>

      <form onSubmit={(event) => void ask(event)} className="flex flex-wrap gap-3">
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          maxLength={500}
          placeholder="Ask about stored invoices and receipts"
          aria-label="Question about stored reviews"
          className="min-w-0 flex-1 rounded-lg border border-line bg-raised px-3 py-2 outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
        />
        <button
          type="submit"
          disabled={question.trim() === '' || isAsking}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isAsking ? 'Asking…' : 'Ask'}
        </button>
      </form>

      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => setQuestion(example)}
            disabled={isAsking}
            className="rounded-full border border-line bg-raised px-3 py-1 text-xs text-muted hover:bg-surface disabled:opacity-50"
          >
            {example}
          </button>
        ))}
      </div>

      {failure !== null && (
        <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">
          <span className="font-medium">{failure.code}</span>
          <span className="block">{failure.message}</span>
        </p>
      )}

      {result !== null && (
        <div className="grid gap-4 rounded-2xl border border-line bg-raised p-5">
          <p className="whitespace-pre-line">{result.answer}</p>

          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Searched for</p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {describeQuery(result.query).map((part) => (
                <li key={part} className="rounded-full border border-line bg-surface px-3 py-1 text-xs">
                  {part}
                </li>
              ))}
            </ul>
          </div>

          {result.groups.length > 0 && <GroupTable groups={result.groups} />}

          {result.documents.length > 0 && (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                {result.documents.length < result.match_count
                  ? `Newest ${result.documents.length} of ${result.match_count} matching documents`
                  : `${result.match_count} matching ${result.match_count === 1 ? 'document' : 'documents'}`}
              </p>
              <ul className="mt-2 flex flex-col gap-2">
                {result.documents.map((document) => (
                  <li key={document.id}>
                    <button
                      type="button"
                      onClick={() => onOpen(document.id)}
                      className={`w-full rounded-xl border px-4 py-3 text-left transition-colors hover:bg-surface ${
                        document.id === selectedId ? 'border-accent bg-accent/5' : 'border-line'
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="truncate font-medium">{document.original_filename}</span>
                        <span className="flex flex-wrap gap-2">
                          {cited.has(document.id) && (
                            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-xs text-accent">
                              cited
                            </span>
                          )}
                          <span className="rounded-full bg-surface px-2 py-0.5 text-xs text-muted">
                            {document.status}
                          </span>
                        </span>
                      </div>
                      <p className="mt-1 text-sm text-muted">{describeDocument(document)}</p>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
