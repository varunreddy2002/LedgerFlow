import { useState } from 'react'
import { useBusiness } from '../context/BusinessContext'
import { useAsync } from '../hooks/useAsync'
import { transactionsApi } from '../api/transactions'
import { AmountBadge, ReviewBadge, TxTypeBadge } from '../components/ui/Badge'
import { PageSpinner } from '../components/ui/Spinner'
import type { TransactionFilters, ReviewStatus, TransactionType } from '../types'

const filterSelect = 'rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400'

export default function Transactions() {
  const { selected } = useBusiness()
  const id = selected!.id

  const [filters, setFilters] = useState<TransactionFilters>({ limit: 100 })

  const { data: txns, loading } = useAsync(
    () => transactionsApi.list(id, filters),
    [id, JSON.stringify(filters)],
  )

  function set<K extends keyof TransactionFilters>(key: K, val: TransactionFilters[K]) {
    setFilters(prev => ({ ...prev, [key]: val || undefined, offset: 0 }))
  }

  return (
    <div className="flex flex-col overflow-hidden">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <h1 className="text-base font-semibold text-gray-900">Transactions</h1>
        <span className="text-sm text-gray-400">{txns?.length ?? 0} rows</span>
      </header>

      {/* filters */}
      <div className="flex flex-wrap gap-2 border-b border-gray-100 bg-gray-50 px-6 py-3">
        <select className={filterSelect} onChange={e => set('review_status', e.target.value as ReviewStatus)}>
          <option value="">All statuses</option>
          <option value="uncategorized">Uncategorized</option>
          <option value="needs_review">Needs review</option>
          <option value="auto_approved">Auto approved</option>
          <option value="user_approved">User approved</option>
          <option value="ignored">Ignored</option>
        </select>

        <select className={filterSelect} onChange={e => set('transaction_type', e.target.value as TransactionType)}>
          <option value="">All types</option>
          <option value="credit">Credit</option>
          <option value="debit">Debit</option>
          <option value="receivable">Receivable</option>
          <option value="payable">Payable</option>
        </select>

        <input
          type="date"
          className={filterSelect}
          onChange={e => set('start_date', e.target.value)}
        />
        <input
          type="date"
          className={filterSelect}
          onChange={e => set('end_date', e.target.value)}
        />
      </div>

      {/* table */}
      <div className="flex-1 overflow-auto">
        {loading ? <PageSpinner /> : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-gray-50">
              <tr className="border-b border-gray-100">
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Date</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Description</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Party</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Category</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Type</th>
                <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-gray-400">Amount</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Status</th>
              </tr>
            </thead>
            <tbody>
              {!txns || txns.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-sm text-gray-400">
                    No transactions found
                  </td>
                </tr>
              ) : txns.map(txn => (
                <tr key={txn.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50">
                  <td className="px-4 py-3 tabular-nums text-gray-500 whitespace-nowrap">{txn.date}</td>
                  <td className="px-4 py-3 max-w-[220px] truncate text-gray-800">
                    {txn.description ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {txn.vendor_name ?? txn.customer_name ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {txn.category_name
                      ? txn.category_name
                      : <span className="text-amber-600 text-xs">Uncategorized</span>
                    }
                  </td>
                  <td className="px-4 py-3">
                    <TxTypeBadge type={txn.trans_type} />
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    <AmountBadge transType={txn.trans_type} amount={txn.amount} />
                  </td>
                  <td className="px-4 py-3">
                    <ReviewBadge status={txn.review_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
