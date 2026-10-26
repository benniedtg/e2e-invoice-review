import type { Fact, ReceiptFacts, ReceiptIssue } from '../../lib/types.ts'
import { money as formatMoney } from './format.ts'

interface ReceiptFactsCardProps {
  facts: ReceiptFacts
  issues: ReceiptIssue[]
}

/** A clear value as printed; an unclear or absent one is flagged, never filled in. */
function FactValue({ fact, money = false }: { fact: Fact<string>; money?: boolean }) {
  if (fact.status === 'clear' && fact.value !== null) {
    return <span>{money ? formatMoney(fact.value) : fact.value}</span>
  }
  return (
    <span
      title={fact.note ?? undefined}
      className={`rounded px-1.5 py-0.5 text-xs font-medium ${
        fact.status === 'unclear' ? 'bg-amber-50 text-amber-900' : 'text-muted'
      }`}
    >
      {fact.status === 'unclear' ? 'Unclear' : '—'}
    </span>
  )
}

export default function ReceiptFactsCard({ facts, issues }: ReceiptFactsCardProps) {
  const unclearNotes = [
    facts.provider_name,
    facts.receipt_date,
    facts.total_paid,
    ...facts.lines.flatMap((line) => Object.values(line) as Fact<string>[]),
  ].filter((fact) => fact.status === 'unclear' && fact.note !== null)

  return (
    <section className="grid gap-4 rounded-2xl border border-line bg-raised p-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted">
          What the receipt shows
        </p>
        <p className="mt-1 font-medium">
          <FactValue fact={facts.provider_name} />
          {facts.provider_type.value !== null && (
            <span className="text-muted"> · {facts.provider_type.value}</span>
          )}
        </p>
        <p className="text-sm text-muted">
          Receipt date <FactValue fact={facts.receipt_date} /> · Total paid{' '}
          <FactValue fact={facts.total_paid} money />
        </p>
      </div>

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-3 py-2">Service</th>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Item</th>
              <th className="px-3 py-2">Charged</th>
              <th className="px-3 py-2">Paid</th>
            </tr>
          </thead>
          <tbody>
            {facts.lines.map((line, index) => (
              <tr key={index} className="border-t border-line">
                <td className="px-3 py-2"><FactValue fact={line.description} /></td>
                <td className="px-3 py-2"><FactValue fact={line.service_date} /></td>
                <td className="px-3 py-2"><FactValue fact={line.item_code} /></td>
                <td className="px-3 py-2"><FactValue fact={line.amount_charged} money /></td>
                <td className="px-3 py-2"><FactValue fact={line.amount_paid} money /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(unclearNotes.length > 0 || issues.length > 0) && (
        <ul className="grid gap-1 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {unclearNotes.map((fact, index) => (
            <li key={`note-${index}`}>{fact.note}</li>
          ))}
          {issues.map((issue, index) => (
            <li key={`issue-${index}`}>{issue.message}</li>
          ))}
        </ul>
      )}

      <p className="text-xs text-muted">
        Nothing from this receipt is stored. It stays in this browser tab until you start over.
      </p>
    </section>
  )
}
