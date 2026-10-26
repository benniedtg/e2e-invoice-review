/** Application-facing mirrors of the backend HTTP contract. */

/** Pydantic serializes `Decimal` as a JSON string. */
export type DecimalString = string

export interface ExtractedField<Value> {
  value: Value
  content: string | null
  confidence: number | null
}

export interface Money {
  amount: DecimalString
  currency_code: string | null
  currency_symbol: string | null
}

export type ClassificationType = 'invoice' | 'receipt' | 'other'

export interface DocumentClassification {
  document_type: ClassificationType
  reason: string
}

export interface GeneralLedgerClassification {
  account_code: string
  account_name: string
  reason: string
}

export interface GeneralLedgerAccount {
  code: string
  name: string
}

export interface CorrectionEmailDraft {
  recipient_name: string
  subject: string
  body: string
}

export type ValidationSeverity = 'error' | 'warning'

export type ValidationIssueCode =
  | 'vendor_name_required'
  | 'vendor_vat_id_required'
  | 'vendor_vat_id_invalid'
  | 'customer_name_required'
  | 'customer_name_mismatch'
  | 'customer_vat_id_required'
  | 'customer_vat_id_invalid'
  | 'customer_vat_id_mismatch'
  | 'invoice_number_required'
  | 'invoice_date_required'
  | 'invoice_total_required'
  | 'invoice_total_non_positive'
  | 'currency_required'
  | 'due_date_before_invoice_date'
  | 'invoice_total_mismatch'
  | 'purchase_order_missing'
  | 'merchant_name_required'
  | 'transaction_date_required'
  | 'receipt_currency_required'
  | 'receipt_total_required'
  | 'receipt_total_non_positive'
  | 'receipt_vat_required'
  | 'receipt_total_mismatch'
  | 'low_confidence'
  | 'duplicate_invoice'
  | 'duplicate_file_content'

export interface ValidationIssue {
  code: ValidationIssueCode
  severity: ValidationSeverity
  field: string
  message: string
  expected: DecimalString | null
  actual: DecimalString | null
}

export interface ValidationReport {
  issues: ValidationIssue[]
  is_valid: boolean
}

export interface InvoicePaymentDetail {
  iban: ExtractedField<string> | null
  swift: ExtractedField<string> | null
  bank_account_number: ExtractedField<string> | null
}

export interface InvoiceTaxDetail {
  amount: ExtractedField<Money> | null
  rate: ExtractedField<string> | null
}

export interface InvoiceItem {
  description: ExtractedField<string> | null
  quantity: ExtractedField<DecimalString> | null
  unit_price: ExtractedField<Money> | null
  amount: ExtractedField<Money> | null
  product_code: ExtractedField<string> | null
  tax: ExtractedField<Money> | null
  tax_rate: ExtractedField<string> | null
  unit: ExtractedField<string> | null
  date: ExtractedField<string> | null
}

export interface InvoiceDocument {
  document_type: 'invoice'
  document_confidence: number | null
  vendor_name: ExtractedField<string> | null
  vendor_address: ExtractedField<string> | null
  vendor_vat_id: ExtractedField<string> | null
  customer_name: ExtractedField<string> | null
  customer_address: ExtractedField<string> | null
  customer_vat_id: ExtractedField<string> | null
  invoice_number: ExtractedField<string> | null
  invoice_date: ExtractedField<string> | null
  due_date: ExtractedField<string> | null
  purchase_order: ExtractedField<string> | null
  payment_term: ExtractedField<string> | null
  currency: ExtractedField<string> | null
  subtotal: ExtractedField<Money> | null
  total_discount: ExtractedField<Money> | null
  total_tax: ExtractedField<Money> | null
  invoice_total: ExtractedField<Money> | null
  amount_due: ExtractedField<Money> | null
  payment_details: InvoicePaymentDetail[]
  tax_details: InvoiceTaxDetail[]
  items: InvoiceItem[]
}

export interface ReceiptPayment {
  method: ExtractedField<string> | null
  amount: ExtractedField<Money> | null
}

export interface ReceiptTaxDetail {
  amount: ExtractedField<Money> | null
  rate: ExtractedField<DecimalString> | null
  net_amount: ExtractedField<Money> | null
  description: ExtractedField<string> | null
}

export interface ReceiptItem {
  description: ExtractedField<string> | null
  quantity: ExtractedField<DecimalString> | null
  price: ExtractedField<Money> | null
  total_price: ExtractedField<Money> | null
  product_code: ExtractedField<string> | null
  quantity_unit: ExtractedField<string> | null
}

export interface ReceiptDocument {
  document_type: 'receipt'
  document_confidence: number | null
  merchant_name: ExtractedField<string> | null
  merchant_address: ExtractedField<string> | null
  merchant_phone: ExtractedField<string> | null
  transaction_date: ExtractedField<string> | null
  transaction_time: ExtractedField<string> | null
  expense_category: ExtractedField<string> | null
  country_region: ExtractedField<string> | null
  currency: ExtractedField<string> | null
  subtotal: ExtractedField<Money> | null
  total_tax: ExtractedField<Money> | null
  total: ExtractedField<Money> | null
  tip: ExtractedField<Money> | null
  payments: ReceiptPayment[]
  tax_details: ReceiptTaxDetail[]
  items: ReceiptItem[]
}

export type NormalizedDocument = InvoiceDocument | ReceiptDocument

export type IndependentExpenseCategory = 'fuel' | 'meals' | 'travel' | 'supplies' | 'other'

export interface IndependentDocumentReview {
  document_type: ClassificationType
  reason: string
  vendor_name: string | null
  vendor_vat_id: string | null
  customer_name: string | null
  customer_vat_id: string | null
  invoice_number: string | null
  invoice_date: string | null
  due_date: string | null
  purchase_order: string | null
  currency: string | null
  subtotal: DecimalString | null
  total_discount: DecimalString | null
  total_tax: DecimalString | null
  invoice_total: DecimalString | null
  amount_due: DecimalString | null
  merchant_name: string | null
  transaction_date: string | null
  expense_category: IndependentExpenseCategory | null
  receipt_total: DecimalString | null
  tip: DecimalString | null
}

export type FieldSource = 'document_intelligence' | 'llm_fallback' | 'human'

export type ComparisonStatus =
  | 'match'
  | 'different'
  | 'missing_in_llm'
  | 'missing_in_document_intelligence'
  | 'missing_in_both'

export interface FieldComparison {
  field: string
  label: string
  status: ComparisonStatus
  document_intelligence_value: string | null
  llm_value: string | null
  winning_source: FieldSource | null
}

export interface DocumentReconciliation {
  comparisons: FieldComparison[]
  fallback_fields: string[]
  conflict_fields: string[]
  field_sources: Record<string, FieldSource>
}

export type PipelineStatus = 'completed' | 'unsupported'

export interface PipelineResult {
  status: PipelineStatus
  classification: DocumentClassification
  independent_review: IndependentDocumentReview | null
  primary_document: NormalizedDocument | null
  reconciliation: DocumentReconciliation | null
  document: NormalizedDocument | null
  general_ledger: GeneralLedgerClassification | null
  validation: ValidationReport | null
}

export type ReviewStatus = 'pending' | 'approved' | 'rejected'

export type EditableFieldName =
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
  | 'receipt_total'
  | 'tip'

export type DocumentCorrections = Partial<Record<EditableFieldName, string | null>>

/** One history row from `GET /api/documents`. */
export interface DocumentSummary {
  id: string
  created_at: string
  original_filename: string
  status: ReviewStatus
  pipeline_status: PipelineStatus
  document_type: 'invoice' | 'receipt' | null
  vendor_name: string | null
  invoice_number: string | null
  document_date: string | null
  total_amount: DecimalString | null
  currency: string | null
  duplicate_of_id: string | null
  is_valid: boolean | null
}

/** Stage identifiers reported by the streaming endpoint, in pipeline order. */
export type StepId =
  | 'document_review'
  | 'primary_extraction'
  | 'reconciliation'
  | 'general_ledger'
  | 'validation'
  | 'storage'

export type StepPhase = 'started' | 'completed' | 'skipped'

export interface StepEvent {
  id: StepId
  phase: StepPhase
}

export interface DocumentResponse {
  id: string
  created_at: string
  original_filename: string
  content_type: string
  size_bytes: number
  status: ReviewStatus
  duplicate_of_id: string | null
  selected_gl_code: string | null
  field_overrides: DocumentCorrections
  field_sources: Record<string, FieldSource>
  reviewed_at: string | null
  supplier_action_required: boolean
  result: PipelineResult
}

export type QueryIntent = 'search' | 'unsupported'
export type QueryAggregate = 'list' | 'count' | 'total'
export type QueryGroup = 'none' | 'gl_account' | 'vendor' | 'status' | 'document_type'

/** The typed filter the model proposed for one question, after local validation. */
export interface DocumentQuery {
  intent: QueryIntent
  statuses: ReviewStatus[]
  document_types: ('invoice' | 'receipt')[]
  vendor_text: string | null
  date_from: string | null
  date_to: string | null
  gl_account_codes: string[]
  min_total: DecimalString | null
  max_total: DecimalString | null
  has_errors: boolean | null
  issue_codes: ValidationIssueCode[]
  is_duplicate: boolean | null
  used_llm_fallback: boolean | null
  aggregate: QueryAggregate
  group_by: QueryGroup
}

/** One count and total computed by the server, per group and currency. */
export interface AssistantGroup {
  label: string
  currency: string | null
  document_count: number
  total_amount: DecimalString | null
  documents_without_total: number
}

/** One answer from `POST /api/assistant/ask` with the evidence behind it. */
export interface AssistantAnswer {
  answer: string
  cited_document_ids: string[]
  query: DocumentQuery
  match_count: number
  documents: DocumentSummary[]
  groups: AssistantGroup[]
}

/** How clearly one printed receipt field could be read. Unclear fields carry no value. */
export type FieldStatus = 'clear' | 'unclear' | 'absent'

export interface Fact<Value> {
  value: Value | null
  status: FieldStatus
  note: string | null
}

export interface ServiceLineFacts {
  description: Fact<string>
  service_date: Fact<string>
  item_code: Fact<string>
  amount_charged: Fact<DecimalString>
  amount_paid: Fact<DecimalString>
}

/** Stage 1 of a claim check: facts printed on one health receipt. */
export interface ReceiptFacts {
  is_health_receipt: boolean
  reason: string
  provider_name: Fact<string>
  provider_type: Fact<string>
  provider_number: Fact<string>
  receipt_date: Fact<string>
  total_charged: Fact<DecimalString>
  total_paid: Fact<DecimalString>
  lines: ServiceLineFacts[]
}

export interface ReceiptIssue {
  code: string
  line_index: number | null
  field: string | null
  message: string
}

export interface ExtractResponse {
  facts: ReceiptFacts
  issues: ReceiptIssue[]
}

export type ClaimSlot =
  | 'insurer'
  | 'product'
  | 'service_date'
  | 'service_description'
  | 'cover_start_date'
  | 'has_referral'
  | 'benefits_used'
  | 'amount_paid'

/** Every answer the student has given, held only in the browser. */
export interface ClaimAnswers {
  insurer_id?: string | null
  product_id?: string | null
  cover_start_date?: string | null
  has_referral?: boolean | null
  service_dates?: Record<string, string>
  service_descriptions?: Record<string, string>
  amounts_paid?: Record<string, DecimalString>
  benefits_used?: Record<string, DecimalString>
}

export type AnswerInput = 'choice' | 'date' | 'amount' | 'yes_no' | 'text'

export interface QuestionOption {
  value: string
  label: string
}

export interface NextQuestion {
  slot: ClaimSlot
  line_index: number | null
  prompt: string
  input: AnswerInput
  options: QuestionOption[]
}

export interface ClaimCitation {
  document_id: string
  document_title: string
  section_number: string | null
  section_title: string | null
  page: number
  quote: string
}

export type ConditionKind =
  | 'coverage'
  | 'exclusion'
  | 'waiting_period'
  | 'pre_existing_waiting_period'
  | 'benefit_rate'
  | 'per_service_limit'
  | 'annual_limit'
  | 'referral_required'
  | 'provider_requirement'
  | 'claim_time_limit'
  | 'claim_document'

export interface ClaimCondition {
  kind: ConditionKind
  applies: boolean
  chunk_id: number
  citation: ClaimCitation
}

export type ConditionState = 'satisfied' | 'not_satisfied' | 'unknown' | 'information'

export interface ConditionResult {
  condition: ClaimCondition
  state: ConditionState
  explanation: string
}

export type ClaimOutcome =
  | 'appears_eligible'
  | 'appears_excluded'
  | 'appears_not_eligible'
  | 'more_information_needed'

export interface BenefitEstimate {
  amount: DecimalString | null
  steps: string[]
  note: string | null
}

export interface ClaimLineResult {
  line_index: number
  description: string | null
  amount_paid: DecimalString | null
  outcome: ClaimOutcome
  reasons: string[]
  needs: ClaimSlot[]
  conditions: ConditionResult[]
  estimate: BenefitEstimate | null
}

export interface ClaimStep {
  text: string
  citation: ClaimCitation | null
}

export interface PolicyContext {
  insurer: string
  product: string
  editions: { document_id: string; title: string; effective_basis: string }[]
}

/** The verified reading of a receipt, returned unchanged so new answers need no model call. */
export type AssessmentState = { product_id: string } & Record<string, unknown>

/** One chat turn: the next question, or a supported result. */
export interface ClaimResponse {
  stage: 'question' | 'result'
  message: string
  next_question: NextQuestion | null
  lines: ClaimLineResult[]
  claim_steps: ClaimStep[]
  policy: PolicyContext | null
  state: AssessmentState | null
}

/** Stable failure identifiers from `backend/app/api/errors.py`. */
export type ErrorCode =
  | 'payload_too_large'
  | 'unsupported_media_type'
  | 'empty_document'
  | 'document_not_found'
  | 'invalid_request'
  | 'review_conflict'
  | 'invalid_review_input'
  | 'configuration_error'
  | 'provider_error'
  | 'invalid_gl_suggestion'
  | 'invalid_assistant_output'
  | 'not_a_health_receipt'
  | 'knowledge_base_missing'
  | 'stale_assessment'
  | 'pipeline_error'
  | 'internal_error'
  | 'network_error'
