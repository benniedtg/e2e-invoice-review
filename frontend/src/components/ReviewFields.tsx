import { useMemo, useState } from 'react'

import { ApiError } from '../lib/api.ts'
import {
  authoritativeValuesAfterSave,
  buildCorrectionPatch,
  descriptorsForDocument,
  documentToFormValues,
  type ReviewFieldSection,
  type ReviewFormValues,
} from '../lib/review-fields.ts'
import type {
  DocumentCorrections,
  EditableFieldName,
  NormalizedDocument,
  ReviewStatus,
} from '../lib/types.ts'

interface ReviewFieldsProps {
  document: NormalizedDocument
  status: ReviewStatus
  onSave: (patch: DocumentCorrections) => Promise<NormalizedDocument>
}

const SECTIONS: readonly ReviewFieldSection[] = [
  'Supplier',
  'Customer',
  'Document',
  'Amounts',
]

interface SaveFailure {
  code: string
  message: string
}

export default function ReviewFields({ document, status, onSave }: ReviewFieldsProps) {
  const descriptors = useMemo(() => descriptorsForDocument(document), [document])
  const [initial, setInitial] = useState<ReviewFormValues>(() => documentToFormValues(document))
  const [values, setValues] = useState<ReviewFormValues>(() => documentToFormValues(document))
  const [isSaving, setIsSaving] = useState(false)
  const [failure, setFailure] = useState<SaveFailure | null>(null)
  const patch = useMemo(
    () => buildCorrectionPatch(initial, values, descriptors),
    [descriptors, initial, values],
  )
  const isDirty = Object.keys(patch).length > 0
  const isDecided = status !== 'pending'

  function change(name: EditableFieldName, value: string): void {
    setValues((current) => ({ ...current, [name]: value }))
    setFailure(null)
  }

  async function save(): Promise<void> {
    if (!isDirty || isDecided) {
      return
    }
    setIsSaving(true)
    setFailure(null)
    try {
      const authoritative = await authoritativeValuesAfterSave(patch, onSave)
      setInitial(authoritative)
      setValues(authoritative)
    } catch (error) {
      setFailure(
        error instanceof ApiError
          ? { code: error.code, message: error.message }
          : { code: 'internal_error', message: 'Unexpected client error.' },
      )
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-semibold">Review extracted fields</h3>
        {isDecided && <span className="text-xs text-muted">Locked after a decision</span>}
      </div>

      <div className="mt-4 grid gap-6">
        {SECTIONS.map((section) => {
          const fields = descriptors.filter((descriptor) => descriptor.section === section)
          if (fields.length === 0) {
            return null
          }
          return (
            <fieldset key={section} disabled={isDecided || isSaving}>
              <legend className="text-xs font-medium uppercase tracking-wide text-muted">
                {section}
              </legend>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                {fields.map((field) => (
                  <label key={field.correctionKey} className="grid gap-1 text-sm">
                    <span className="font-medium">{field.label}</span>
                    <input
                      type={field.inputKind === 'date' ? 'date' : 'text'}
                      inputMode={field.inputKind === 'decimal' ? 'decimal' : undefined}
                      value={values[field.correctionKey] ?? ''}
                      onChange={(event) => change(field.correctionKey, event.target.value)}
                      className="min-w-0 rounded-lg border border-line bg-raised px-3 py-2 outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:bg-surface disabled:text-muted"
                    />
                  </label>
                ))}
              </div>
            </fieldset>
          )
        })}
      </div>

      {failure !== null && (
        <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">
          <span className="font-medium">{failure.code}</span>
          <span className="block">{failure.message}</span>
        </p>
      )}

      <button
        type="button"
        onClick={() => void save()}
        disabled={!isDirty || isSaving || isDecided}
        className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isSaving ? 'Saving…' : 'Save corrections'}
      </button>
    </section>
  )
}
