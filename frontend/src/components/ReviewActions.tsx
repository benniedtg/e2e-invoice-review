import { useRef, useState } from 'react'

import ConfirmDialog from './ConfirmDialog.tsx'
import CorrectionEmailDialog from './CorrectionEmailDialog.tsx'
import { ApiError, decideDocument, draftCorrectionEmail } from '../lib/api.ts'
import type {
  CorrectionEmailDraft,
  DocumentResponse,
} from '../lib/types.ts'

interface ReviewActionsProps {
  document: DocumentResponse
  onChanged: (document: DocumentResponse) => void
}

interface ReviewActionAvailability {
  canApprove: boolean
  canReject: boolean
  canDraft: boolean
  errorCount: number
  missingGl: boolean
  isFinal: boolean
}

function reviewActionAvailability(
  document: DocumentResponse,
): ReviewActionAvailability {
  const validation = document.result.validation
  const completedFinancial = document.result.status === 'completed'
    && document.result.document !== null
    && validation !== null
  const errorCount = validation?.issues.filter(
    (issue) => issue.severity === 'error',
  ).length ?? 0
  const isPendingFinancial = document.status === 'pending' && completedFinancial
  const missingGl = document.selected_gl_code === null

  return {
    canApprove: isPendingFinancial && errorCount === 0 && !missingGl,
    canReject: isPendingFinancial,
    canDraft: completedFinancial
      && document.supplier_action_required
      && (document.status === 'pending' || document.status === 'rejected'),
    errorCount,
    missingGl,
    isFinal: document.status === 'approved' || document.status === 'rejected',
  }
}

function failureFrom(error: unknown): { code: string; message: string } {
  return error instanceof ApiError
    ? { code: error.code, message: error.message }
    : { code: 'internal_error', message: 'Unexpected client error.' }
}

export default function ReviewActions({ document, onChanged }: ReviewActionsProps) {
  const availability = reviewActionAvailability(document)
  const decisionBusyRef = useRef(false)
  const draftingRef = useRef(false)
  const [confirmDecision, setConfirmDecision] = useState<'approved' | 'rejected' | null>(null)
  const [isDeciding, setIsDeciding] = useState(false)
  const [isDrafting, setIsDrafting] = useState(false)
  const [draft, setDraft] = useState<CorrectionEmailDraft | null>(null)
  const [failure, setFailure] = useState<{ code: string; message: string } | null>(null)

  async function decide(decision: 'approved' | 'rejected'): Promise<void> {
    if (decisionBusyRef.current) return
    decisionBusyRef.current = true
    setIsDeciding(true)
    setFailure(null)
    try {
      onChanged(await decideDocument(document.id, decision))
    } catch (error) {
      setFailure(failureFrom(error))
      throw error
    } finally {
      decisionBusyRef.current = false
      setIsDeciding(false)
    }
  }

  async function createDraft(): Promise<void> {
    if (draftingRef.current || !availability.canDraft) return
    draftingRef.current = true
    setIsDrafting(true)
    setFailure(null)
    try {
      setDraft(await draftCorrectionEmail(document.id))
    } catch (error) {
      setFailure(failureFrom(error))
    } finally {
      draftingRef.current = false
      setIsDrafting(false)
    }
  }

  if (!availability.canReject && !availability.canDraft && !availability.isFinal) {
    return null
  }

  return (
    <section className="rounded-xl border border-line p-4">
      <h3 className="text-sm font-semibold">Review actions</h3>

      {availability.isFinal ? (
        <p className="mt-3 rounded-lg bg-surface px-4 py-3 text-sm">
          This review is {document.status} and read-only. Its decision is final.
        </p>
      ) : (
        <>
          {(availability.errorCount > 0 || availability.missingGl) && (
            <ul className="mt-3 grid gap-1 text-sm text-amber-900">
              {availability.errorCount > 0 && (
                <li>
                  Approval is blocked by {availability.errorCount} validation{' '}
                  {availability.errorCount === 1 ? 'error' : 'errors'}.
                </li>
              )}
              {availability.missingGl && (
                <li>Select and save a GL account before approval.</li>
              )}
            </ul>
          )}
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setConfirmDecision('approved')}
              disabled={!availability.canApprove || isDeciding || isDrafting}
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => setConfirmDecision('rejected')}
              disabled={!availability.canReject || isDeciding || isDrafting}
              className="rounded-lg bg-red-700 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              Reject
            </button>
          </div>
        </>
      )}

      {availability.canDraft && (
        <div className="mt-4 border-t border-line pt-4">
          <p className="text-sm text-muted">
            Create a copyable request from the current supplier-fixable issues.
          </p>
          <button
            type="button"
            onClick={() => void createDraft()}
            disabled={isDrafting || isDeciding}
            className="mt-3 rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-surface disabled:opacity-50"
          >
            {isDrafting ? 'Drafting…' : 'Draft correction email'}
          </button>
        </div>
      )}

      {failure !== null && (
        <p role="alert" className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">
          <span className="font-medium">{failure.code}</span>
          <span className="block">{failure.message}</span>
        </p>
      )}

      {confirmDecision !== null && (
        <ConfirmDialog
          title={confirmDecision === 'approved' ? 'Approve document?' : 'Reject document?'}
          description={
            <>
              <p>
                {confirmDecision === 'approved'
                  ? 'Approval is final and locks field, GL, and decision changes.'
                  : 'Rejection is final and locks field, GL, and decision changes.'}
              </p>
              {failure !== null && (
                <p role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-red-800">
                  <span className="font-medium">{failure.code}</span>
                  <span className="block">{failure.message}</span>
                </p>
              )}
            </>
          }
          confirmLabel={confirmDecision === 'approved' ? 'Approve' : 'Reject'}
          tone={confirmDecision === 'approved' ? 'primary' : 'danger'}
          onConfirm={() => decide(confirmDecision)}
          onClose={() => setConfirmDecision(null)}
        />
      )}

      {draft !== null && (
        <CorrectionEmailDialog draft={draft} onClose={() => setDraft(null)} />
      )}
    </section>
  )
}
