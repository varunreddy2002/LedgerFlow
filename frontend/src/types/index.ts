export type DocumentStatus =
  | 'uploaded'
  | 'processing'
  | 'categorizing'
  | 'processed'
  | 'failed'
  | 'duplicate_file'
  | 'pending_ocr'
  | 'needs_review'

export type SourceType =
  | 'bank_statement'
  | 'credit_card_statement'
  | 'receipt'
  | 'invoice'
  | 'vendor_bill'
  | 'payout_report'
  | 'unknown'

export type Direction = 'inflow' | 'outflow'

export type TransactionType =
  | 'revenue'
  | 'expense'
  | 'transfer'
  | 'owner_draw'
  | 'owner_contribution'
  | 'loan_payment'
  | 'refund'
  | 'tax_payment'
  | 'tax_collected'
  | 'unknown'

export type ReviewStatus =
  | 'auto_approved'
  | 'needs_review'
  | 'user_approved'
  | 'user_corrected'
  | 'ignored'

export interface Business {
  id: number
  name: string
  business_type: string | null
  currency: string
  created_at: string
  updated_at: string
}

export interface BusinessCreate {
  name: string
  business_type?: string
  currency?: string
}

export interface Document {
  id: number
  business_id: number
  original_filename: string
  stored_filename: string
  file_type: string | null
  file_size: number | null
  source_type: SourceType
  status: DocumentStatus
  uploaded_at: string
  processed_at: string | null
  invoice_number: string | null
  invoice_date: string | null
  due_date: string | null
}

export interface ParseErrorDetail {
  row_number: number
  reason: string
  raw_value: string
}

export interface UploadResponse {
  document: Document
  is_duplicate_file: boolean
  duplicate_document_id: number | null
  message: string
  rows_imported: number
  rows_skipped: number
  duplicate_transactions: number
  parse_errors: ParseErrorDetail[]
}

export interface Transaction {
  id: number
  business_id: number
  document_id: number | null
  account_id: number | null
  transaction_date: string
  posted_date: string | null
  description_raw: string | null
  description_clean: string | null
  merchant_name: string | null
  amount: string
  direction: Direction
  category_id: number | null
  transaction_type: TransactionType
  confidence_score: number | null
  review_status: ReviewStatus
  is_excluded_from_pnl: boolean
  exclusion_reason: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface TransactionUpdate {
  category_id?: number | null
  transaction_type?: TransactionType
  review_status?: ReviewStatus
  is_excluded_from_pnl?: boolean
  exclusion_reason?: string | null
  notes?: string | null
}

export interface TransactionSummary {
  total_count: number
  total_inflow: number
  total_outflow: number
  net: number
  needs_review_count: number
  by_review_status: Record<string, number>
}

export interface TransactionFilters {
  review_status?: ReviewStatus
  direction?: Direction
  transaction_type?: TransactionType
  start_date?: string
  end_date?: string
  limit?: number
  offset?: number
}
