import { useRef, useState } from 'react'

import { ACCEPTED_MIME_TYPES, MAX_UPLOAD_BYTES } from '../lib/api.ts'

interface UploadPanelProps {
  isProcessing: boolean
  onProcess: (file: File) => void
  title?: string
  actionLabel?: string
}

function describeSize(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

/** Reject what the backend would reject anyway, before spending a request. */
function findLocalProblem(file: File): string | null {
  if (file.size === 0) {
    return 'That file is empty.'
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `Document must be 4 MB or smaller. This one is ${describeSize(file.size)}.`
  }
  if (!ACCEPTED_MIME_TYPES.includes(file.type as (typeof ACCEPTED_MIME_TYPES)[number])) {
    return 'Document must be a PDF, PNG, or JPEG file.'
  }
  return null
}

export default function UploadPanel({
  isProcessing,
  onProcess,
  title = 'Drop an invoice or receipt here',
  actionLabel = 'Process document',
}: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  function select(candidate: File | undefined): void {
    if (candidate === undefined) {
      return
    }
    const localProblem = findLocalProblem(candidate)
    setProblem(localProblem)
    setFile(localProblem === null ? candidate : null)
  }

  return (
    <section className="flex flex-col gap-6">
      <div
        className={`rounded-2xl border-2 border-dashed p-10 text-center transition-colors ${
          isDragging ? 'border-accent bg-accent/5' : 'border-line bg-raised'
        }`}
        onDragOver={(event) => {
          event.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setIsDragging(false)
          select(event.dataTransfer.files[0])
        }}
      >
        <p className="text-lg font-medium">{title}</p>
        <p className="mt-1 text-sm text-muted">PDF, PNG, or JPEG. Up to 4 MB.</p>

        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept={ACCEPTED_MIME_TYPES.join(',')}
          onChange={(event) => {
            select(event.target.files?.[0])
            event.target.value = ''
          }}
        />

        <button
          type="button"
          className="mt-6 rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-surface"
          onClick={() => inputRef.current?.click()}
          disabled={isProcessing}
        >
          Select a file
        </button>
      </div>

      {problem !== null && (
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{problem}</p>
      )}

      {file !== null && (
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-line bg-raised px-4 py-3">
          <div className="min-w-0">
            <p className="truncate font-medium">{file.name}</p>
            <p className="text-sm text-muted">
              {file.type} · {describeSize(file.size)}
            </p>
          </div>
          <button
            type="button"
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            onClick={() => onProcess(file)}
            disabled={isProcessing}
          >
            {isProcessing ? 'Processing…' : actionLabel}
          </button>
        </div>
      )}
    </section>
  )
}
