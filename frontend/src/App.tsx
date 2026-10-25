import { useCallback, useEffect, useRef, useState } from 'react'

import AskPanel from './components/AskPanel.tsx'
import ConfirmDialog from './components/ConfirmDialog.tsx'
import DocumentSummaryCard from './components/DocumentSummary.tsx'
import HistoryList from './components/HistoryList.tsx'
import ProcessingSteps from './components/ProcessingSteps.tsx'
import UploadPanel from './components/UploadPanel.tsx'
import {
  ApiError,
  deleteDocument,
  fetchDocument,
  listDocuments,
  streamDocument,
} from './lib/api.ts'
import type {
  DocumentResponse,
  DocumentSummary,
  ErrorCode,
  StepId,
  StepPhase,
} from './lib/types.ts'

type Phase =
  | { name: 'idle' }
  | { name: 'processing'; filename: string; phases: Partial<Record<StepId, StepPhase>> }
  | { name: 'failed'; code: ErrorCode; message: string }
  | { name: 'done'; document: DocumentResponse }

function toFailure(error: unknown): Phase {
  if (error instanceof ApiError) {
    return { name: 'failed', code: error.code, message: error.message }
  }
  return { name: 'failed', code: 'internal_error', message: 'Unexpected client error.' }
}

export default function App() {
  const [phase, setPhase] = useState<Phase>({ name: 'idle' })
  const [history, setHistory] = useState<DocumentSummary[]>([])
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [deletionTarget, setDeletionTarget] = useState<DocumentSummary | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deletionFailure, setDeletionFailure] = useState<{
    code: string
    message: string
  } | null>(null)
  const deletionBusyRef = useRef(false)

  const refreshHistory = useCallback(
    () =>
      listDocuments().then(
        (documents) => {
          setHistory(documents)
          setHistoryError(null)
        },
        (error: unknown) => {
          setHistoryError(
            error instanceof ApiError ? error.message : 'Could not load the review history.',
          )
        },
      ),
    [],
  )

  useEffect(() => {
    void refreshHistory()
  }, [refreshHistory])

  async function run(file: File): Promise<void> {
    setPhase({ name: 'processing', filename: file.name, phases: {} })

    try {
      const document = await streamDocument(file, (event) => {
        setPhase((current) =>
          current.name === 'processing'
            ? { ...current, phases: { ...current.phases, [event.id]: event.phase } }
            : current,
        )
      })
      setPhase({ name: 'done', document })
    } catch (error) {
      setPhase(toFailure(error))
    } finally {
      // The pipeline can fail after the record was stored, so refresh either way.
      void refreshHistory()
    }
  }

  async function reopen(id: string): Promise<void> {
    try {
      setPhase({ name: 'done', document: await fetchDocument(id) })
    } catch (error) {
      setPhase(toFailure(error))
    }
  }

  function documentChanged(document: DocumentResponse): void {
    setPhase({ name: 'done', document })
    void refreshHistory()
  }

  function requestDeletion(id: string): void {
    const target = history.find((document) => document.id === id)
    if (target === undefined) return
    setDeletionFailure(null)
    setDeletionTarget(target)
  }

  async function confirmDeletion(): Promise<void> {
    if (deletionTarget === null || deletionBusyRef.current) return
    const target = deletionTarget
    deletionBusyRef.current = true
    setDeletingId(target.id)
    setDeletionFailure(null)
    try {
      await deleteDocument(target.id)
      await refreshHistory()
      setHistory((current) => current.filter((document) => document.id !== target.id))
      setPhase((current) =>
        current.name === 'done' && current.document.id === target.id
          ? { name: 'idle' }
          : current,
      )
    } catch (error) {
      setDeletionFailure(
        error instanceof ApiError
          ? { code: error.code, message: error.message }
          : { code: 'internal_error', message: 'Unexpected client error.' },
      )
      throw error
    } finally {
      deletionBusyRef.current = false
      setDeletingId(null)
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-7xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8">
      <header>
        <h1 className="text-3xl font-semibold">Invoice Review</h1>
        <p className="mt-2 text-muted">
          Upload one invoice or receipt. It is classified, extracted, categorized against the
          Northstar ledger, and validated.
        </p>
      </header>

      {phase.name === 'processing' && (
        <ProcessingSteps filename={phase.filename} phases={phase.phases} />
      )}

      {phase.name === 'done' && (
        <>
          <DocumentSummaryCard
            document={phase.document}
            onDocumentChanged={documentChanged}
          />
          <button
            type="button"
            className="self-start rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-raised"
            onClick={() => setPhase({ name: 'idle' })}
          >
            Process another document
          </button>
        </>
      )}

      {(phase.name === 'idle' || phase.name === 'failed') && (
        <UploadPanel isProcessing={false} onProcess={run} />
      )}

      {phase.name === 'failed' && (
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">
          <span className="font-medium">{phase.code}</span>
          <span className="block">{phase.message}</span>
        </p>
      )}

      <AskPanel
        selectedId={phase.name === 'done' ? phase.document.id : null}
        onOpen={reopen}
      />

      <HistoryList
        documents={history}
        selectedId={phase.name === 'done' ? phase.document.id : null}
        deletingId={deletingId}
        onSelect={reopen}
        onDelete={requestDeletion}
      />

      {historyError !== null && (
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">{historyError}</p>
      )}

      {deletionTarget !== null && (
        <ConfirmDialog
          title="Delete document?"
          description={
            <>
              <p>
                Delete <span className="font-medium text-ink">{deletionTarget.original_filename}</span>?
                This permanently removes the review and stored source from this application.
              </p>
              {deletionFailure !== null && (
                <p role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-red-800">
                  <span className="font-medium">{deletionFailure.code}</span>
                  <span className="block">{deletionFailure.message}</span>
                </p>
              )}
            </>
          }
          confirmLabel="Delete"
          tone="danger"
          onConfirm={confirmDeletion}
          onClose={() => {
            setDeletionTarget(null)
            setDeletionFailure(null)
          }}
        />
      )}
    </main>
  )
}
