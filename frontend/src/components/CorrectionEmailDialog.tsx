import { useEffect, useId, useRef, useState } from 'react'

import type { CorrectionEmailDraft } from '../lib/types.ts'

interface CorrectionEmailDialogProps {
  draft: CorrectionEmailDraft
  onClose: () => void
}

function correctionEmailCopyText(draft: CorrectionEmailDraft): string {
  return `${draft.subject}\n\n${draft.body}`
}

export default function CorrectionEmailDialog({
  draft,
  onClose,
}: CorrectionEmailDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const copyingRef = useRef(false)
  const [copyState, setCopyState] = useState<'idle' | 'copying' | 'copied' | 'failed'>('idle')
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog === null) return
    dialog.showModal()
    closeRef.current?.focus()
    return () => {
      if (dialog.open) dialog.close()
    }
  }, [])

  async function copy(): Promise<void> {
    if (copyingRef.current) return
    copyingRef.current = true
    setCopyState('copying')
    try {
      await navigator.clipboard.writeText(correctionEmailCopyText(draft))
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    } finally {
      copyingRef.current = false
    }
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
      className="m-auto w-[calc(100%-2rem)] max-w-2xl rounded-2xl border border-line bg-raised p-0 text-ink shadow-2xl backdrop:bg-ink/35"
    >
      <div className="border-b border-line px-6 py-5">
        <h2 id={titleId} className="text-lg font-semibold">Supplier correction draft</h2>
        <p id={descriptionId} className="mt-1 text-sm text-muted">
          Copy this draft into your usual email tool. This application does not deliver or store
          the message.
        </p>
      </div>

      <div className="grid gap-4 p-6">
        <label className="grid gap-1 text-sm font-medium">
          Recipient name
          <input
            readOnly
            value={draft.recipient_name}
            className="rounded-lg border border-line bg-surface px-3 py-2 font-normal"
          />
        </label>
        <label className="grid gap-1 text-sm font-medium">
          Subject
          <input
            readOnly
            value={draft.subject}
            className="rounded-lg border border-line bg-surface px-3 py-2 font-normal"
          />
        </label>
        <label className="grid gap-1 text-sm font-medium">
          Message
          <textarea
            readOnly
            value={draft.body}
            rows={10}
            className="resize-y rounded-lg border border-line bg-surface px-3 py-2 font-normal leading-6"
          />
        </label>

        {copyState === 'copied' && (
          <p role="status" className="text-sm text-emerald-800">Draft copied.</p>
        )}
        {copyState === 'failed' && (
          <p role="alert" className="text-sm text-red-800">
            Clipboard access failed. Select the read-only text and copy it manually.
          </p>
        )}

        <div className="flex flex-wrap justify-end gap-3 border-t border-line pt-4">
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-surface"
          >
            Close
          </button>
          <button
            type="button"
            onClick={() => void copy()}
            disabled={copyState === 'copying'}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {copyState === 'copying' ? 'Copying…' : 'Copy'}
          </button>
        </div>
      </div>
    </dialog>
  )
}
