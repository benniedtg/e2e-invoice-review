import { useEffect, useId, useRef } from 'react'

import { policyDocumentUrl } from '../../lib/api.ts'
import type { ClaimCitation } from '../../lib/types.ts'
import { PdfPreview } from '../DocumentPreview.tsx'
import { describeCitation } from './format.ts'

interface PolicyPageDialogProps {
  citation: ClaimCitation
  onClose: () => void
}

/** Show the quoted passage beside the policy page it came from, so it can be checked. */
export default function PolicyPageDialog({ citation, onClose }: PolicyPageDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog === null) return
    dialog.showModal()
    return () => {
      if (dialog.open) dialog.close()
    }
  }, [])

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
      className="m-auto w-[calc(100%-2rem)] max-w-3xl rounded-2xl border border-line bg-raised p-0 text-ink shadow-2xl backdrop:bg-ink/35"
    >
      <div className="grid gap-4 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id={titleId} className="text-lg font-semibold">{citation.document_title}</h2>
            <p className="text-sm text-muted">{describeCitation(citation)}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-line px-3 py-1 text-sm font-medium hover:bg-surface"
          >
            Close
          </button>
        </div>
        <blockquote className="border-l-4 border-accent/40 bg-surface px-4 py-3 text-sm">
          {citation.quote}
        </blockquote>
        <PdfPreview url={policyDocumentUrl(citation.document_id)} page={citation.page} />
      </div>
    </dialog>
  )
}
