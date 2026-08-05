from app.invoices import ValidationIssue, ValidationIssueCode

SUPPLIER_FIXABLE_CODES = frozenset({
  ValidationIssueCode.VENDOR_NAME_REQUIRED,
  ValidationIssueCode.VENDOR_VAT_ID_REQUIRED,
  ValidationIssueCode.VENDOR_VAT_ID_INVALID,
  ValidationIssueCode.CUSTOMER_NAME_REQUIRED,
  ValidationIssueCode.CUSTOMER_NAME_MISMATCH,
  ValidationIssueCode.CUSTOMER_VAT_ID_REQUIRED,
  ValidationIssueCode.CUSTOMER_VAT_ID_INVALID,
  ValidationIssueCode.CUSTOMER_VAT_ID_MISMATCH,
  ValidationIssueCode.INVOICE_NUMBER_REQUIRED,
  ValidationIssueCode.INVOICE_DATE_REQUIRED,
  ValidationIssueCode.INVOICE_TOTAL_REQUIRED,
  ValidationIssueCode.INVOICE_TOTAL_NON_POSITIVE,
  ValidationIssueCode.CURRENCY_REQUIRED,
  ValidationIssueCode.DUE_DATE_BEFORE_INVOICE_DATE,
  ValidationIssueCode.INVOICE_TOTAL_MISMATCH,
  ValidationIssueCode.PURCHASE_ORDER_MISSING,
  ValidationIssueCode.MERCHANT_NAME_REQUIRED,
  ValidationIssueCode.TRANSACTION_DATE_REQUIRED,
  ValidationIssueCode.RECEIPT_CURRENCY_REQUIRED,
  ValidationIssueCode.RECEIPT_TOTAL_REQUIRED,
  ValidationIssueCode.RECEIPT_TOTAL_NON_POSITIVE,
  ValidationIssueCode.RECEIPT_VAT_REQUIRED,
  ValidationIssueCode.RECEIPT_TOTAL_MISMATCH,
})


def supplier_fixable_issues(
  issues: tuple[ValidationIssue, ...],
) -> tuple[ValidationIssue, ...]:
  """Keep supplier-correctable issues in their original order and identity."""
  return tuple(issue for issue in issues if issue.code in SUPPLIER_FIXABLE_CODES)
