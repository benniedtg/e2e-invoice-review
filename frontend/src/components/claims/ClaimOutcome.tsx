import type {
  ClaimCitation,
  ClaimLineResult,
  ClaimOutcome as Outcome,
  ClaimResponse,
  ConditionKind,
  ConditionState,
} from '../../lib/types.ts'
import { describeCitation, money } from './format.ts'

interface ClaimOutcomeProps {
  response: ClaimResponse
  onCite: (citation: ClaimCitation) => void
}

const OUTCOMES: Record<Outcome, { label: string; tone: string }> = {
  appears_eligible: { label: 'Appears eligible', tone: 'bg-emerald-100 text-emerald-900' },
  appears_excluded: { label: 'Appears excluded', tone: 'bg-red-100 text-red-900' },
  appears_not_eligible: { label: 'Appears not eligible', tone: 'bg-red-100 text-red-900' },
  more_information_needed: { label: 'More information needed', tone: 'bg-amber-50 text-amber-900' },
}

const KINDS: Record<ConditionKind, string> = {
  coverage: 'Coverage',
  exclusion: 'Exclusion',
  waiting_period: 'Waiting period',
  pre_existing_waiting_period: 'Pre-existing condition wait',
  benefit_rate: 'Benefit rate',
  per_service_limit: 'Per-service limit',
  annual_limit: 'Annual limit',
  referral_required: 'Referral',
  provider_requirement: 'Provider',
  claim_time_limit: 'Claim time limit',
  claim_document: 'Claim document',
}

const STATES: Record<ConditionState, { label: string; tone: string }> = {
  satisfied: { label: 'Met', tone: 'text-emerald-800' },
  not_satisfied: { label: 'Not met', tone: 'text-red-800' },
  unknown: { label: 'Unknown', tone: 'text-amber-900' },
  information: { label: 'Note', tone: 'text-muted' },
}

function CiteButton({ citation, onCite }: { citation: ClaimCitation; onCite: ClaimOutcomeProps['onCite'] }) {
  return (
    <button
      type="button"
      onClick={() => onCite(citation)}
      className="text-xs font-medium text-accent underline-offset-2 hover:underline"
    >
      {describeCitation(citation)}
    </button>
  )
}

function LineCard({ line, onCite }: { line: ClaimLineResult; onCite: ClaimOutcomeProps['onCite'] }) {
  const outcome = OUTCOMES[line.outcome]
  return (
    <article className="grid gap-3 rounded-xl border border-line p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium">
          {line.description ?? `Line ${line.line_index + 1}`}
          {line.amount_paid !== null && <span className="text-muted"> · paid {money(line.amount_paid)}</span>}
        </p>
        <span className={`rounded-full px-3 py-1 text-xs font-medium ${outcome.tone}`}>
          {outcome.label}
        </span>
      </div>

      {line.reasons.length > 0 && (
        <ul className="list-disc pl-5 text-sm">
          {line.reasons.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}

      {line.estimate !== null && (
        <div className="rounded-lg bg-surface px-3 py-2 text-sm">
          <p className="font-medium">
            {line.estimate.amount === null
              ? 'No estimate'
              : `Estimated benefit: ${money(line.estimate.amount)}`}
          </p>
          {line.estimate.steps.length > 0 && (
            <ol className="mt-1 list-decimal pl-5 text-muted">
              {line.estimate.steps.map((step) => <li key={step}>{step}</li>)}
            </ol>
          )}
          {line.estimate.note !== null && <p className="mt-1 text-muted">{line.estimate.note}</p>}
        </div>
      )}

      {line.conditions.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted">
            Policy conditions checked ({line.conditions.length})
          </summary>
          <ul className="mt-2 grid gap-2">
            {line.conditions.map((result, index) => (
              <li key={index} className="rounded-lg border border-line px-3 py-2">
                <p>
                  <span className="font-medium">{KINDS[result.condition.kind]}</span>
                  <span className={`ml-2 text-xs font-medium ${STATES[result.state].tone}`}>
                    {STATES[result.state].label}
                  </span>
                </p>
                <p className="text-muted">{result.explanation}</p>
                <CiteButton citation={result.condition.citation} onCite={onCite} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  )
}

/** Stage 6: each line's supported outcome, its arithmetic, and the passages behind it. */
export default function ClaimOutcome({ response, onCite }: ClaimOutcomeProps) {
  return (
    <section className="grid gap-4 rounded-2xl border border-line bg-raised p-5">
      {response.policy !== null && (
        <div className="text-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Checked against</p>
          <p className="mt-1 font-medium">{response.policy.insurer} · {response.policy.product}</p>
          <ul className="text-muted">
            {response.policy.editions.map((edition) => (
              <li key={edition.document_id}>{edition.title} ({edition.effective_basis})</li>
            ))}
          </ul>
        </div>
      )}

      {response.lines.map((line) => (
        <LineCard key={line.line_index} line={line} onCite={onCite} />
      ))}

      {response.claim_steps.length > 0 && (
        <div className="text-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">How to claim</p>
          <ul className="mt-2 grid gap-2">
            {response.claim_steps.map((step) => (
              <li key={step.text}>
                {step.text}
                {step.citation !== null && (
                  <span className="ml-2"><CiteButton citation={step.citation} onCite={onCite} /></span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
