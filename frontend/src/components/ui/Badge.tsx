import type { DocumentStatus, ReviewStatus, Direction, TransactionType } from '../../types'

const reviewStatusStyles: Record<ReviewStatus, string> = {
  needs_review:   'bg-amber-50 text-amber-800 ring-amber-200',
  auto_approved:  'bg-green-50 text-green-800 ring-green-200',
  user_approved:  'bg-green-50 text-green-800 ring-green-200',
  user_corrected: 'bg-blue-50 text-blue-800 ring-blue-200',
  ignored:        'bg-gray-100 text-gray-600 ring-gray-200',
}

const reviewStatusLabels: Record<ReviewStatus, string> = {
  needs_review:   'Needs review',
  auto_approved:  'Auto approved',
  user_approved:  'Approved',
  user_corrected: 'Corrected',
  ignored:        'Ignored',
}

const docStatusStyles: Record<DocumentStatus, string> = {
  uploaded:       'bg-gray-100 text-gray-600 ring-gray-200',
  processing:     'bg-blue-50 text-blue-800 ring-blue-200',
  categorizing:   'bg-blue-50 text-blue-800 ring-blue-200',
  processed:      'bg-green-50 text-green-800 ring-green-200',
  failed:         'bg-red-50 text-red-800 ring-red-200',
  duplicate_file: 'bg-gray-100 text-gray-600 ring-gray-200',
  pending_ocr:    'bg-amber-50 text-amber-800 ring-amber-200',
  needs_review:   'bg-amber-50 text-amber-800 ring-amber-200',
}

const docStatusLabels: Record<DocumentStatus, string> = {
  uploaded:       'Uploaded',
  processing:     'Processing',
  categorizing:   'Categorizing',
  processed:      'Processed',
  failed:         'Failed',
  duplicate_file: 'Duplicate',
  pending_ocr:    'Pending OCR',
  needs_review:   'Needs review',
}

const txTypeLabels: Record<TransactionType, string> = {
  revenue:            'Revenue',
  expense:            'Expense',
  transfer:           'Transfer',
  owner_draw:         'Owner draw',
  owner_contribution: 'Owner contribution',
  loan_payment:       'Loan payment',
  refund:             'Refund',
  tax_payment:        'Tax payment',
  tax_collected:      'Tax collected',
  unknown:            'Unknown',
}

const base = 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ring-1 ring-inset'

export function ReviewBadge({ status }: { status: ReviewStatus }) {
  return <span className={`${base} ${reviewStatusStyles[status]}`}>{reviewStatusLabels[status]}</span>
}

export function DocStatusBadge({ status }: { status: DocumentStatus }) {
  return <span className={`${base} ${docStatusStyles[status]}`}>{docStatusLabels[status]}</span>
}

export function DirectionBadge({ direction, amount }: { direction: Direction; amount: string }) {
  const sign = direction === 'inflow' ? '+' : '−'
  const cls = direction === 'inflow' ? 'text-green-700 font-medium' : 'text-red-700 font-medium'
  return <span className={cls}>{sign}${Number(amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
}

export function TxTypeBadge({ type }: { type: TransactionType }) {
  return <span className="text-xs text-gray-500">{txTypeLabels[type]}</span>
}
