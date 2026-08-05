import DocumentPreview from './DocumentPreview.tsx'
import GeneralLedgerControl from './GeneralLedgerControl.tsx'
import ProvenancePanel from './ProvenancePanel.tsx'
import ReviewActions from './ReviewActions.tsx'
import ReviewFields from './ReviewFields.tsx'
import { ApiError, saveCorrections } from '../lib/api.ts'
import type {
  DocumentCorrections,
  DocumentResponse,
  ExtractedField,
  InvoiceDocument,
  Money,
  NormalizedDocument,
  ReceiptDocument,
  ValidationReport,
} from '../lib/types.ts'

interface DocumentSummaryProps {
  document: DocumentResponse
  onDocumentChanged: (document: DocumentResponse) => void
}

const EMPTY = '—'

function text(field: ExtractedField<string> | null): string {
  return field?.value ?? EMPTY
}

function money(field: ExtractedField<Money> | null): string {
  if (field === null) return EMPTY
  const unit = field.value.currency_code ?? field.value.currency_symbol
  return unit === null ? field.value.amount : `${field.value.amount} ${unit}`
}

function ValidationPanel({ validation }: { validation: ValidationReport }) {
  if (validation.issues.length === 0) {
    return (
      <p className="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
        No validation issues.
      </p>
    )
  }

  return (
    <section>
      <h3 className="text-sm font-semibold">Validation</h3>
      <ul className="mt-2 flex flex-col gap-2">
        {validation.issues.map((issue) => (
          <li
            key={`${issue.code}-${issue.field}`}
            className={`rounded-lg px-4 py-3 text-sm ${
              issue.severity === 'error'
                ? 'bg-red-50 text-red-800'
                : 'bg-amber-50 text-amber-900'
            }`}
          >
            <span className="font-medium">
              {issue.severity} · {issue.field}
            </span>
            <span className="block">{issue.message}</span>
            {issue.expected !== null && issue.actual !== null && (
              <span className="block text-xs">
                expected {issue.expected}, found {issue.actual}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function InvoiceDetails({ document }: { document: InvoiceDocument }) {
  return (
    <section className="grid gap-4">
      <h3 className="text-sm font-semibold">Invoice details</h3>

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-3 py-2">Description</th>
              <th className="px-3 py-2">Product</th>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Quantity</th>
              <th className="px-3 py-2">Unit price</th>
              <th className="px-3 py-2">Tax</th>
              <th className="px-3 py-2">Amount</th>
            </tr>
          </thead>
          <tbody>
            {document.items.length === 0 ? (
              <tr><td colSpan={7} className="px-3 py-3 text-muted">No line items extracted.</td></tr>
            ) : document.items.map((item, index) => (
              <tr key={`${item.description?.value ?? 'item'}-${index}`} className="border-t border-line">
                <td className="px-3 py-2">{text(item.description)}</td>
                <td className="px-3 py-2">{text(item.product_code)}</td>
                <td className="px-3 py-2">{text(item.date)}</td>
                <td className="px-3 py-2">
                  {text(item.quantity)}{item.unit === null ? '' : ` ${item.unit.value}`}
                </td>
                <td className="px-3 py-2">{money(item.unit_price)}</td>
                <td className="px-3 py-2">
                  {money(item.tax)}{item.tax_rate === null ? '' : ` at ${item.tax_rate.value}`}
                </td>
                <td className="px-3 py-2">{money(item.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-line p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Tax details</p>
          {document.tax_details.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No tax detail extracted.</p>
          ) : document.tax_details.map((tax, index) => (
            <p key={index} className="mt-2 text-sm">
              {money(tax.amount)}{tax.rate === null ? '' : ` at ${tax.rate.value}`}
            </p>
          ))}
        </div>
        <div className="rounded-xl border border-line p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Payment details</p>
          {document.payment_details.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No payment detail extracted.</p>
          ) : document.payment_details.map((payment, index) => (
            <dl key={index} className="mt-2 grid grid-cols-[auto_1fr] gap-x-2 text-sm">
              <dt className="text-muted">IBAN</dt><dd className="break-all">{text(payment.iban)}</dd>
              <dt className="text-muted">SWIFT</dt><dd>{text(payment.swift)}</dd>
              <dt className="text-muted">Account</dt><dd className="break-all">{text(payment.bank_account_number)}</dd>
            </dl>
          ))}
        </div>
      </div>
    </section>
  )
}

function ReceiptDetails({ document }: { document: ReceiptDocument }) {
  return (
    <section className="grid gap-4">
      <h3 className="text-sm font-semibold">Receipt details</h3>

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-3 py-2">Description</th>
              <th className="px-3 py-2">Product</th>
              <th className="px-3 py-2">Quantity</th>
              <th className="px-3 py-2">Price</th>
              <th className="px-3 py-2">Total</th>
            </tr>
          </thead>
          <tbody>
            {document.items.length === 0 ? (
              <tr><td colSpan={5} className="px-3 py-3 text-muted">No line items extracted.</td></tr>
            ) : document.items.map((item, index) => (
              <tr key={`${item.description?.value ?? 'item'}-${index}`} className="border-t border-line">
                <td className="px-3 py-2">{text(item.description)}</td>
                <td className="px-3 py-2">{text(item.product_code)}</td>
                <td className="px-3 py-2">
                  {text(item.quantity)}
                  {item.quantity_unit === null ? '' : ` ${item.quantity_unit.value}`}
                </td>
                <td className="px-3 py-2">{money(item.price)}</td>
                <td className="px-3 py-2">{money(item.total_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-line p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Tax details</p>
          {document.tax_details.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No tax detail extracted.</p>
          ) : document.tax_details.map((tax, index) => (
            <p key={index} className="mt-2 text-sm">
              {tax.description?.value ?? 'Tax'}: {money(tax.amount)}
              {tax.rate === null ? '' : ` at ${tax.rate.value}`}
              {tax.net_amount === null ? '' : ` · net ${money(tax.net_amount)}`}
            </p>
          ))}
        </div>
        <div className="rounded-xl border border-line p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Payments</p>
          {document.payments.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No payment detail extracted.</p>
          ) : document.payments.map((payment, index) => (
            <p key={index} className="mt-2 text-sm">
              {text(payment.method)} · {money(payment.amount)}
            </p>
          ))}
        </div>
      </div>
    </section>
  )
}

function StatusBadge({ document }: { document: DocumentResponse }) {
  const tone = document.status === 'approved'
    ? 'bg-emerald-50 text-emerald-800'
    : document.status === 'rejected'
      ? 'bg-red-50 text-red-800'
      : 'bg-amber-50 text-amber-900'
  return (
    <span className={`rounded-full px-3 py-1 text-xs uppercase tracking-wide ${tone}`}>
      {document.status}
    </span>
  )
}

export default function DocumentSummary({
  document,
  onDocumentChanged,
}: DocumentSummaryProps) {
  const { result } = document

  async function updateFields(patch: DocumentCorrections): Promise<NormalizedDocument> {
    const saved = await saveCorrections(document.id, patch)
    if (saved.result.document === null) {
      throw new ApiError(
        'pipeline_error',
        'The server returned no effective financial document after saving corrections.',
      )
    }
    onDocumentChanged(saved)
    return saved.result.document
  }

  return (
    <section className="grid gap-6">
      <header className="rounded-2xl border border-line bg-raised p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold">{document.original_filename}</h2>
            <p className="mt-1 text-sm text-muted">{result.classification.reason}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge document={document} />
            <span className="rounded-full border border-line px-3 py-1 text-xs uppercase tracking-wide text-muted">
              {result.status} · {result.classification.document_type}
            </span>
          </div>
        </div>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(24rem,1fr)]">
        <div className="min-w-0 rounded-2xl border border-line bg-raised p-4 lg:sticky lg:top-4">
          <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">Source</p>
          <DocumentPreview document={document} />
        </div>

        <div className="min-w-0 grid gap-6 rounded-2xl border border-line bg-raised p-5">
          {result.document === null ? (
            <p className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900">
              This document was not recognized as an invoice or a receipt, so no fields were extracted.
            </p>
          ) : (
            <>
              <ReviewFields
                key={`${document.id}-${JSON.stringify(document.field_overrides)}`}
                document={result.document}
                status={document.status}
                onSave={updateFields}
              />
              <ProvenancePanel
                reconciliation={result.reconciliation}
                fieldSources={document.field_sources}
              />
              <GeneralLedgerControl
                key={`${document.id}-${document.selected_gl_code ?? 'unselected'}`}
                document={document}
                onSaved={onDocumentChanged}
              />
              {result.validation !== null && <ValidationPanel validation={result.validation} />}
              <ReviewActions
                key={document.id}
                document={document}
                onChanged={onDocumentChanged}
              />
              {result.document.document_type === 'invoice'
                ? <InvoiceDetails document={result.document} />
                : <ReceiptDetails document={result.document} />}
            </>
          )}
        </div>
      </div>
    </section>
  )
}
