import type {
  DocumentCorrections,
  EditableFieldName,
  ExtractedField,
  InvoiceDocument,
  Money,
  NormalizedDocument,
  ReceiptDocument,
} from './types.ts'

export type ReviewInputKind = 'text' | 'date' | 'decimal'
export type ReviewFieldSection = 'Supplier' | 'Customer' | 'Document' | 'Amounts'
export type ReviewFormValues = Partial<Record<EditableFieldName, string>>

type DocumentReadKey =
  | 'vendor_name'
  | 'vendor_vat_id'
  | 'customer_name'
  | 'customer_vat_id'
  | 'invoice_number'
  | 'invoice_date'
  | 'due_date'
  | 'purchase_order'
  | 'currency'
  | 'subtotal'
  | 'total_discount'
  | 'total_tax'
  | 'invoice_total'
  | 'amount_due'
  | 'merchant_name'
  | 'transaction_date'
  | 'expense_category'
  | 'total'
  | 'tip'

export interface ReviewFieldDescriptor {
  correctionKey: EditableFieldName
  documentKey: DocumentReadKey
  label: string
  inputKind: ReviewInputKind
  section: ReviewFieldSection
}

export const invoiceFieldDescriptors: readonly ReviewFieldDescriptor[] = Object.freeze([
  { correctionKey: 'vendor_name', documentKey: 'vendor_name', label: 'Supplier name', inputKind: 'text', section: 'Supplier' },
  { correctionKey: 'vendor_vat_id', documentKey: 'vendor_vat_id', label: 'Supplier VAT ID', inputKind: 'text', section: 'Supplier' },
  { correctionKey: 'customer_name', documentKey: 'customer_name', label: 'Customer name', inputKind: 'text', section: 'Customer' },
  { correctionKey: 'customer_vat_id', documentKey: 'customer_vat_id', label: 'Customer VAT ID', inputKind: 'text', section: 'Customer' },
  { correctionKey: 'invoice_number', documentKey: 'invoice_number', label: 'Invoice number', inputKind: 'text', section: 'Document' },
  { correctionKey: 'invoice_date', documentKey: 'invoice_date', label: 'Invoice date', inputKind: 'date', section: 'Document' },
  { correctionKey: 'due_date', documentKey: 'due_date', label: 'Due date', inputKind: 'date', section: 'Document' },
  { correctionKey: 'purchase_order', documentKey: 'purchase_order', label: 'Purchase order', inputKind: 'text', section: 'Document' },
  { correctionKey: 'currency', documentKey: 'currency', label: 'Currency', inputKind: 'text', section: 'Document' },
  { correctionKey: 'subtotal', documentKey: 'subtotal', label: 'Subtotal', inputKind: 'decimal', section: 'Amounts' },
  { correctionKey: 'total_discount', documentKey: 'total_discount', label: 'Total discount', inputKind: 'decimal', section: 'Amounts' },
  { correctionKey: 'total_tax', documentKey: 'total_tax', label: 'VAT total', inputKind: 'decimal', section: 'Amounts' },
  { correctionKey: 'invoice_total', documentKey: 'invoice_total', label: 'Invoice total', inputKind: 'decimal', section: 'Amounts' },
  { correctionKey: 'amount_due', documentKey: 'amount_due', label: 'Amount due', inputKind: 'decimal', section: 'Amounts' },
])

export const receiptFieldDescriptors: readonly ReviewFieldDescriptor[] = Object.freeze([
  { correctionKey: 'merchant_name', documentKey: 'merchant_name', label: 'Merchant name', inputKind: 'text', section: 'Supplier' },
  { correctionKey: 'transaction_date', documentKey: 'transaction_date', label: 'Transaction date', inputKind: 'date', section: 'Document' },
  { correctionKey: 'expense_category', documentKey: 'expense_category', label: 'Expense category', inputKind: 'text', section: 'Document' },
  { correctionKey: 'currency', documentKey: 'currency', label: 'Currency', inputKind: 'text', section: 'Document' },
  { correctionKey: 'subtotal', documentKey: 'subtotal', label: 'Subtotal', inputKind: 'decimal', section: 'Amounts' },
  { correctionKey: 'total_tax', documentKey: 'total_tax', label: 'VAT total', inputKind: 'decimal', section: 'Amounts' },
  { correctionKey: 'receipt_total', documentKey: 'total', label: 'Receipt total', inputKind: 'decimal', section: 'Amounts' },
  { correctionKey: 'tip', documentKey: 'tip', label: 'Tip', inputKind: 'decimal', section: 'Amounts' },
])

export function descriptorsForDocument(
  document: NormalizedDocument,
): readonly ReviewFieldDescriptor[] {
  return document.document_type === 'invoice'
    ? invoiceFieldDescriptors
    : receiptFieldDescriptors
}

export function documentToFormValues(document: NormalizedDocument): ReviewFormValues {
  const values: ReviewFormValues = {}
  for (const descriptor of descriptorsForDocument(document)) {
    values[descriptor.correctionKey] = fieldString(
      readDocumentField(document, descriptor.documentKey),
    )
  }
  return values
}

export function buildCorrectionPatch(
  initial: ReviewFormValues,
  current: ReviewFormValues,
  descriptors: readonly ReviewFieldDescriptor[],
): DocumentCorrections {
  const patch: DocumentCorrections = {}
  for (const descriptor of descriptors) {
    const initialValue = initial[descriptor.correctionKey] ?? ''
    const currentValue = current[descriptor.correctionKey] ?? ''
    if (currentValue === initialValue) {
      continue
    }
    patch[descriptor.correctionKey] = currentValue === '' ? null : currentValue
  }
  return patch
}

export async function authoritativeValuesAfterSave(
  patch: DocumentCorrections,
  save: (patch: DocumentCorrections) => Promise<NormalizedDocument>,
): Promise<ReviewFormValues> {
  return documentToFormValues(await save(patch))
}

type ReviewField = ExtractedField<string> | ExtractedField<Money> | null

function fieldString(field: ReviewField): string {
  if (field === null) {
    return ''
  }
  return typeof field.value === 'string' ? field.value : field.value.amount
}

function readDocumentField(
  document: NormalizedDocument,
  key: DocumentReadKey,
): ReviewField {
  return document.document_type === 'invoice'
    ? readInvoiceField(document, key)
    : readReceiptField(document, key)
}

function readInvoiceField(document: InvoiceDocument, key: DocumentReadKey): ReviewField {
  switch (key) {
    case 'vendor_name': return document.vendor_name
    case 'vendor_vat_id': return document.vendor_vat_id
    case 'customer_name': return document.customer_name
    case 'customer_vat_id': return document.customer_vat_id
    case 'invoice_number': return document.invoice_number
    case 'invoice_date': return document.invoice_date
    case 'due_date': return document.due_date
    case 'purchase_order': return document.purchase_order
    case 'currency': return document.currency
    case 'subtotal': return document.subtotal
    case 'total_discount': return document.total_discount
    case 'total_tax': return document.total_tax
    case 'invoice_total': return document.invoice_total
    case 'amount_due': return document.amount_due
    default: return null
  }
}

function readReceiptField(document: ReceiptDocument, key: DocumentReadKey): ReviewField {
  switch (key) {
    case 'merchant_name': return document.merchant_name
    case 'transaction_date': return document.transaction_date
    case 'expense_category': return document.expense_category
    case 'currency': return document.currency
    case 'subtotal': return document.subtotal
    case 'total_tax': return document.total_tax
    case 'total': return document.total
    case 'tip': return document.tip
    default: return null
  }
}
