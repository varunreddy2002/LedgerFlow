import { useState } from 'react'
import { useBusiness } from '../context/BusinessContext'
import { useAsync } from '../hooks/useAsync'
import { transactionsApi } from '../api/transactions'
import { ReviewBadge, DirectionBadge, TxTypeBadge } from '../components/ui/Badge'
import { PageSpinner } from '../components/ui/Spinner'
import type { TransactionFilters, ReviewStatus, Direction, TransactionType } from '../types'

export default function Transactions() {
  const { selected } = useBusiness()
  const id = selected!.id

  const [filters, setFilters] = useState<TransactionFilters>({ limit: 100 })

  const { data: txns, loading, error } = useAsync(
    () => transactionsApi.list(id, filters),
    [id, filters],
  )

  function set<K extends keyof TransactionFilters>(key: K, val: TransactionFilters[K]) {
    setFilters(prev => ({ ...prev, [key]: val || undefined, offset: 0 }))
  }

  return (
    <div className="flex flex-col overflow-auto">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <h1 className="text-base font-semibold text-gray-900">Transactions</h1>
        <span className="text-sm text-gray-400">{txns?.length ?? 0} rows</span>
      </header>

      <div className="flex-1 space-y-4 p-6">
        <div className="flex flex-wrap gap-2">
          <select
            value={filters.review_status ?? ''}
            onChange={e => set('review_status', e.target.value as ReviewStatus || undefined)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="">All statuses</option>
            <option value="needs_review">Needs review</option>
            <option value="auto_approved">Auto approved</option>
            <option value="user_approved">User approved</option>
            <option value="user_corrected">User corrected</option>
          </select>

          <select
            value={filters.direction ?? ''}
            onChange={e => set('direction', e.target.value as Direction || undefined)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="">All directions</option>
            <option value="inflow">Inflow</option>
            <option value="outflow">Outflow</option>
          </select>

          <select
            value={filters.transaction_type ?? ''}
            onChange={e => set('transaction_type', e.target.value as TransactionType || undefined)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="">All types</option>
            <option value="revenue">Revenue</option>
            <option value="expense">Expense</option>
            <option value="transfer">Transfer</option>
            <option value="tax_collected">Tax collected</option>
            <option value="tax_payment">Tax payment</option>
            <option value="unknown">Unknown</option>
          </select>

          <input
            type="date"
            value={filters.start_date ?? ''}
            onChange={e => set('start_date', e.target.value || undefined)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <input
            type="date"
            value={filters.end_date ?? ''}
            onChange={e => set('end_date', e.target.value || undefined)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>

        {loading && <PageSpinner />}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!loading && (
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
            {!txns || txns.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-gray-400">No transactions found</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Date</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Description</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Merchant</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Type</th>
                    <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-gray-400">Amount</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {txns.map(txn => (
                    <tr key={txn.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50">
                      <td className="px-4 py-2.5 text-gray-500 tabular-nums">{txn.transaction_date}</td>
                      <td className="px-4 py-2.5 max-w-xs truncate text-gray-800">
                        {txn.description_clean ?? txn.description_raw ?? '—'}
                      </td>
                      <td className="px-4 py-2.5 text-gray-500">{txn.merchant_name ?? '—'}</td>
                      <td className="px-4 py-2.5"><TxTypeBadge type={txn.transaction_type} /></td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        <DirectionBadge direction={txn.direction} amount={txn.amount} />
                      </td>
                      <td className="px-4 py-2.5"><ReviewBadge status={txn.review_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
