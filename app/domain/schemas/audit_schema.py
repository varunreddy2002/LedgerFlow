from pydantic import BaseModel


class CsvIngestionResult(BaseModel):
    """new_values payload for an EXTRACTED audit event on a CSV document."""

    bank_transactions_created: int
    duplicates_skipped: int
    total_rows: int


class PdfIngestionResult(BaseModel):
    """new_values payload for an EXTRACTED audit event on a PDF invoice/bill."""

    document_type: str   # "invoice" | "vendor_bill"
    party_resolved: bool
    line_item_count: int
    status: str           # the resulting InvoiceBillStatus


class ReconciliationResult(BaseModel):
    """new_values payload for a RECONCILED audit event — a batch of
    NEW bank_transactions matched against DRAFT invoices/bills before
    categorization ever ran on them."""

    reconciled_count: int
    bank_transactions_scanned: int


class CategorizationResult(BaseModel):
    """new_values payload for a CLASSIFIED audit event on a batch of
    bank_transactions run through the accounting_rules engine and, for
    whatever's left unmatched, the AI fallback."""

    rule_matched: int
    ai_suggested: int
    review_required: int
    total_bank_transactions: int
