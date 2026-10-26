import { useEffect, useRef, useState } from 'react'
// The legacy build polyfills newer JavaScript the default build assumes, so a
// browser a version or two behind still renders instead of throwing.
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist/legacy/build/pdf.mjs'
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'

import { sourceDocumentUrl } from '../lib/api.ts'
import type { DocumentResponse } from '../lib/types.ts'

// The bundled worker keeps page rendering off the main thread without a CDN.
GlobalWorkerOptions.workerSrc = workerUrl

const RENDER_SCALE = 2
/** Draw above the displayed size so a scanned page stays readable. */

interface DocumentPreviewProps {
  document: DocumentResponse
}

/**
 * Draw every page onto a canvas instead of embedding the file.
 *
 * A browser set to download PDFs rather than open them turns an `<iframe>`
 * into a save prompt and leaves the reviewer with an empty panel, so the
 * source is rasterized here and never handed to the browser's PDF viewer.
 * With `page`, only that page is drawn, for example the page a citation quotes.
 */
export function PdfPreview({ url, page }: { url: string; page?: number }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (container === null) {
      return
    }

    let cancelled = false
    const task = getDocument({ url })

    async function draw(target: HTMLDivElement): Promise<void> {
      const pdf = await task.promise
      const first = page ?? 1
      const last = Math.min(page ?? pdf.numPages, pdf.numPages)
      for (let number = first; number <= last; number += 1) {
        const pdfPage = await pdf.getPage(number)
        if (cancelled) {
          return
        }
        const viewport = pdfPage.getViewport({ scale: RENDER_SCALE })
        const canvas = window.document.createElement('canvas')
        canvas.width = viewport.width
        canvas.height = viewport.height
        canvas.className = 'w-full rounded-lg border border-line bg-white'
        target.append(canvas)
        await pdfPage.render({ canvas, viewport }).promise
      }
    }

    setFailure(null)
    draw(container).catch((error: unknown) => {
      if (!cancelled) {
        setFailure(error instanceof Error ? `${error.name}: ${error.message}` : String(error))
      }
    })

    return () => {
      cancelled = true
      container.replaceChildren()
      void task.destroy()
    }
  }, [url, page])

  return (
    <>
      {failure !== null && (
        <p className="mb-3 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <span className="font-medium">This source could not be drawn here.</span>
          <span className="block break-words">{failure}</span>
        </p>
      )}
      <div ref={containerRef} className="grid max-h-[70vh] gap-3 overflow-y-auto" />
    </>
  )
}

export default function DocumentPreview({ document }: DocumentPreviewProps) {
  const sourceUrl = sourceDocumentUrl(document.id)

  if (document.content_type === 'image/png' || document.content_type === 'image/jpeg') {
    return (
      <img
        src={sourceUrl}
        alt={`Source document: ${document.original_filename}`}
        className="mx-auto max-h-[70vh] w-auto rounded-lg object-contain"
      />
    )
  }

  if (document.content_type === 'application/pdf') {
    return <PdfPreview url={sourceUrl} />
  }

  return (
    <p className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900">
      Preview is unavailable for this document type.
    </p>
  )
}
