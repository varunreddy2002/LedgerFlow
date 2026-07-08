import type { DocumentStatus, ReviewStatus, TransactionType } from '../../types'

const reviewStatusStyles: Record<ReviewStatus, string> = {
  uncategorized:  'bg-gray-100 text-gray-600 ring-gray-200',
  needs_review:   'bg-amber-50 text-amber-800 ring-amber-200',
  auto_approved:  'bg-green-50 text-green-800 ring-green-200',
  user_approved:  'bg-green-50 text-green-800 ring-green-200',
  user_corrected: 'bg-blue-50 text-blue-800 ring-blue-200',
  ignored:        'bg-gray-100 text-gray-600 ring-gray-200',
}

const reviewStatusLabels: Record<ReviewStatus, string> = {
  uncategorized:  'Uncategorized',
  needs_review:   'Needs review',
  auto_approved:  'Auto approved',
  user_approved:  'Approved',
  user_corrected: 'Corrected',
  ignored:        'Ignored',
}

const docStatusStyles: Record<DocumentStatus, string> = {
  uploaded:   'bg-gray-100 text-gray-600 ring-gray-200',
  processing: 'bg-blue-50 text-blue-800 ring-blue-200',
  processed:  'bg-green-50 text-green-800 ring-green-200',
  failed:     'bg-red-50 text-red-800 ring-red-200',
}

const docStatusLabels: Record<DocumentStatus, string> = {
  uploaded:   'Uploaded',
  processing: 'Processing',
  processed:  'Processed',
  failed:     'Failed',
}

const txTypeStyles: Record<TransactionType, string> = {
  debit:       'bg-red-50 text-red-700 ring-red-200',
  credit:      'bg-green-50 text-green-700 ring-green-200',
  payable:     'bg-amber-50 text-amber-700 ring-amber-200',
  receivable:  'bg-blue-50 text-blue-700 ring-blue-200',
}

const txTypeLabels: Record<TransactionType, string> = {
  debit:      'Debit',
  credit:     'Credit',
  payable:    'Payable',
  receivable: 'Receivable',
}

const base = 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ring-1 ring-inset'

export function ReviewBadge({ status }: { status: ReviewStatus }) {
  return <span className={`${base} ${reviewStatusStyles[status]}`}>{reviewStatusLabels[status]}</span>
}

export function DocStatusBadge({ status }: { status: DocumentStatus }) {
  return <span className={`${base} ${docStatusStyles[status]}`}>{docStatusLabels[status]}</span>
}

export function AmountBadge({ transType, amount }: { transType: TransactionType; amount: string }) {
  const sign = transType === 'credit' || transType === 'receivable' ? '+' : '−'
  const cls  = transType === 'credit' || transType === 'receivable' ? 'text-green-700 font-medium' : 'text-red-700 font-medium'
  return <span className={cls}>{sign}${Number(amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
}

export function TxTypeBadge({ type }: { type: TransactionType }) {
  return <span className={`${base} ${txTypeStyles[type]}`}>{txTypeLabels[type]}</span>
}
