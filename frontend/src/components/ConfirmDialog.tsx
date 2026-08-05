import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from 'react'

interface ConfirmDialogProps {
  title: string
  description: ReactNode
  confirmLabel: string
  tone: 'primary' | 'danger'
  onConfirm: () => Promise<void>
  onClose: () => void
}

export default function ConfirmDialog({
  title,
  description,
  confirmLabel,
  tone,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const busyRef = useRef(false)
  const [isBusy, setIsBusy] = useState(false)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog === null) return
    dialog.showModal()
    cancelRef.current?.focus()
    return () => {
      if (dialog.open) dialog.close()
    }
  }, [])

  async function confirm(): Promise<void> {
    if (busyRef.current) return
    busyRef.current = true
    setIsBusy(true)
    try {
      await onConfirm()
      onClose()
    } catch {
      // The parent owns the typed error; keep this dialog open and retryable.
    } finally {
      busyRef.current = false
      setIsBusy(false)
    }
  }

  function close(): void {
    if (!busyRef.current) onClose()
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      aria-busy={isBusy}
      onCancel={(event) => {
        event.preventDefault()
        close()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) close()
      }}
      className="m-auto w-[calc(100%-2rem)] max-w-md rounded-2xl border border-line bg-raised p-0 text-ink shadow-2xl backdrop:bg-ink/35"
    >
      <div className="p-6">
        <h2 id={titleId} className="text-lg font-semibold">{title}</h2>
        <div id={descriptionId} className="mt-2 text-sm leading-6 text-muted">
          {description}
        </div>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button
            ref={cancelRef}
            type="button"
            onClick={close}
            disabled={isBusy}
            className="rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-surface disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void confirm()}
            disabled={isBusy}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50 ${
              tone === 'danger' ? 'bg-red-700' : 'bg-accent'
            }`}
          >
            {isBusy ? `${confirmLabel}…` : confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  )
}
