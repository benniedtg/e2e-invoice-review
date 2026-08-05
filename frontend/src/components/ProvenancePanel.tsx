import type {
  DocumentReconciliation,
  FieldSource,
} from '../lib/types.ts'

interface ProvenancePanelProps {
  reconciliation: DocumentReconciliation | null
  fieldSources: Record<string, FieldSource>
}

const SOURCE_LABELS: Record<FieldSource, string> = {
  document_intelligence: 'Document Intelligence',
  llm_fallback: 'Independent review fallback',
  human: 'Human correction',
}

function valueOrEmpty(value: string | null): string {
  return value ?? 'Not present'
}

export default function ProvenancePanel({
  reconciliation,
  fieldSources,
}: ProvenancePanelProps) {
  const entries = Object.entries(fieldSources).sort(([left], [right]) =>
    left.localeCompare(right),
  )
  const conflicts = reconciliation?.comparisons.filter(
    (comparison) => comparison.status === 'different',
  ) ?? []

  if (entries.length === 0 && reconciliation === null) {
    return null
  }

  return (
    <section className="rounded-xl border border-line bg-surface/60 p-4">
      <h3 className="text-sm font-semibold">Field provenance</h3>

      {entries.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {entries.map(([field, source]) => (
            <li key={field} className="rounded-full border border-line bg-raised px-3 py-1 text-xs">
              <span className="font-medium">{field.replaceAll('_', ' ')}</span>
              <span className="text-muted"> · {SOURCE_LABELS[source]}</span>
            </li>
          ))}
        </ul>
      )}

      {conflicts.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">
            Different readings
          </p>
          <ul className="mt-2 grid gap-2">
            {conflicts.map((comparison) => {
              const effectiveSource = fieldSources[comparison.field]
              const selection = effectiveSource === 'human'
                ? 'Your correction is selected.'
                : 'Document Intelligence remains selected.'

              return (
                <li key={comparison.field} className="rounded-lg border border-line bg-raised p-3 text-sm">
                  <p className="font-medium">{comparison.label}</p>
                  <dl className="mt-2 grid gap-2 sm:grid-cols-2">
                    <div>
                      <dt className="text-xs text-muted">Document Intelligence</dt>
                      <dd className="break-words">{valueOrEmpty(comparison.document_intelligence_value)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">Independent review</dt>
                      <dd className="break-words">{valueOrEmpty(comparison.llm_value)}</dd>
                    </div>
                  </dl>
                  <p className="mt-2 text-xs text-muted">{selection}</p>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {reconciliation !== null && reconciliation.fallback_fields.length > 0 && (
        <p className="mt-4 text-xs text-muted">
          Independent review filled: {reconciliation.fallback_fields.join(', ')}.
        </p>
      )}
    </section>
  )
}
