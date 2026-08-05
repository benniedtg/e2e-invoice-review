import type { DocumentSummary } from '../lib/types.ts'

interface HistoryListProps {
  documents: DocumentSummary[]
  selectedId: string | null
  deletingId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}

const TIMESTAMP = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

function ResultBadge({ document }: { document: DocumentSummary }) {
  if (document.pipeline_status === 'unsupported') {
    return (
      <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-900">
        unsupported
      </span>
    )
  }
  if (document.is_valid === false) {
    return <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs text-red-700">invalid</span>
  }
  return (
    <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-800">valid</span>
  )
}

function DecisionBadge({ document }: { document: DocumentSummary }) {
  const tone = document.status === 'approved'
    ? 'bg-emerald-100 text-emerald-900'
    : document.status === 'rejected'
      ? 'bg-red-100 text-red-900'
      : 'bg-surface text-muted'
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs ${tone}`}>
      {document.status}
    </span>
  )
}

function describe(document: DocumentSummary): string {
  const parts = [document.vendor_name, document.invoice_number].filter(
    (part): part is string => part !== null,
  )
  return parts.length === 0 ? 'No supplier details extracted' : parts.join(' · ')
}

export default function HistoryList({
  documents,
  selectedId,
  deletingId,
  onSelect,
  onDelete,
}: HistoryListProps) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium uppercase tracking-wide text-muted">History</h2>

      {documents.length === 0 ? (
        <p className="text-sm text-muted">Nothing processed yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {documents.map((document) => (
            <li
              key={document.id}
              className={`flex overflow-hidden rounded-xl border transition-colors ${
                document.id === selectedId
                  ? 'border-accent bg-accent/5'
                  : 'border-line bg-raised'
              }`}
            >
              <button
                type="button"
                onClick={() => onSelect(document.id)}
                className="min-w-0 flex-1 px-4 py-3 text-left hover:bg-surface"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="truncate font-medium">{document.original_filename}</span>
                  <span className="flex flex-wrap gap-2">
                    <DecisionBadge document={document} />
                    <ResultBadge document={document} />
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
                  <span>{TIMESTAMP.format(new Date(document.created_at))}</span>
                  <span>·</span>
                  <span>{describe(document)}</span>
                  {document.duplicate_of_id !== null && (
                    <span className="text-red-700">duplicate</span>
                  )}
                </div>
              </button>
              <button
                type="button"
                aria-label={`Delete ${document.original_filename}`}
                onClick={(event) => {
                  event.stopPropagation()
                  onDelete(document.id)
                }}
                disabled={deletingId === document.id}
                className="shrink-0 border-l border-line px-4 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deletingId === document.id ? 'Deleting…' : 'Delete'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
