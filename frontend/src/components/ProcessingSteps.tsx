import type { StepId, StepPhase } from '../lib/types.ts'

interface ProcessingStepsProps {
  filename: string
  phases: Partial<Record<StepId, StepPhase>>
}

const STEPS: { id: StepId; label: string }[] = [
  { id: 'document_review', label: 'Read document independently' },
  { id: 'primary_extraction', label: 'Extract primary fields' },
  { id: 'reconciliation', label: 'Merge and compare readings' },
  { id: 'general_ledger', label: 'Categorize to ledger' },
  { id: 'validation', label: 'Validate finance policy' },
  { id: 'storage', label: 'Store and check duplicates' },
]

function Spinner() {
  return (
    <svg className="size-4 animate-spin text-accent" viewBox="0 0 16 16" aria-hidden="true">
      <circle
        cx="8"
        cy="8"
        r="6"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="2"
      />
      <path
        d="M8 2a6 6 0 0 1 6 6"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}

function Marker({ phase }: { phase: StepPhase | undefined }) {
  if (phase === 'started') {
    return <Spinner />
  }
  if (phase === 'completed') {
    return <span className="text-sm text-emerald-600">✓</span>
  }
  if (phase === 'skipped') {
    return <span className="text-sm text-muted">–</span>
  }
  return <span className="size-2 rounded-full bg-line" />
}

function toneFor(phase: StepPhase | undefined): string {
  if (phase === 'started') {
    return 'font-medium'
  }
  if (phase === undefined || phase === 'skipped') {
    return 'text-muted'
  }
  return ''
}

export default function ProcessingSteps({ filename, phases }: ProcessingStepsProps) {
  return (
    <section className="rounded-2xl border border-line bg-raised p-6">
      <p className="truncate font-medium">{filename}</p>

      <ol className="mt-4 flex flex-col gap-3">
        {STEPS.map((step) => {
          const phase = phases[step.id]
          return (
            <li key={step.id} className={`flex items-center gap-3 text-sm ${toneFor(phase)}`}>
              <span className="flex size-4 items-center justify-center">
                <Marker phase={phase} />
              </span>
              <span>{step.label}</span>
              {phase === 'skipped' && <span className="text-xs text-muted">not applicable</span>}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
