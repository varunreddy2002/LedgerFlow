export type DocumentStatus =
  | 'uploaded'
  | 'processing'
  | 'processed'
  | 'failed'

export type SourceType =
  | 'bank_statement'
  | 'credit_card'
  | 'invoice'
  | 'vendor_bill'

export type TransactionType =
  | 'debit'
  | 'credit'
  | 'payable'
  | 'receivable'

export type ReviewStatus =
  | 'uncategorized'
  | 'needs_review'
  | 'auto_approved'
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
  filename: string
  source: SourceType
  status: DocumentStatus
  uploaded_at: string
  processed_at: string | null
}

export interface UploadResponse {
  status: DocumentStatus
}

export interface Transaction {
  id: number
  document_id: number | null
  date: string
  due_date: string | null
  description: string | null
  amount: string
  trans_type: TransactionType
  category_id: number | null
  category_name: string | null
  vendor_id: number | null
  vendor_name: string | null
  customer_id: number | null
  customer_name: string | null
  review_status: ReviewStatus
}

export interface TransactionUpdate {
  category_id?: number | null
  vendor_id?: number | null
  customer_id?: number | null
  review_status?: ReviewStatus
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
  transaction_type?: TransactionType
  category_id?: number
  start_date?: string
  end_date?: string
  limit?: number
  offset?: number
}
