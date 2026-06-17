import { useState } from 'react'
import { useBusiness } from '../context/BusinessContext'
import { useAsync } from '../hooks/useAsync'
import { transactionsApi } from '../api/transactions'
import { DirectionBadge, TxTypeBadge } from '../components/ui/Badge'
import { PageSpinner } from '../components/ui/Spinner'
import type { Transaction, ReviewStatus } from '../types'

function confidence(score: number | null) {
  if (score === null) return '—'
  const pct = Math.round(score * 100)
  const color = pct >= 75 ? 'text-green-700' : pct >= 50 ? 'text-amber-700' : 'text-red-700'
  return <span className={color}>{pct}%</span>
}

export default function ReviewQueue() {
  const { selected } = useBusiness()
  const id = selected!.id

  const { data: txns, loading, refetch } = useAsync(
    () => transactionsApi.list(id, { review_status: 'needs_review', limit: 100 }),
    [id],
  )

  const [active, setActive] = useState<Transaction | null>(null)
  const [saving, setSaving] = useState(false)
  const [savedId, setSavedId] = useState<number | null>(null)

  async function approve(status: ReviewStatus) {
    if (!active) return
    setSaving(true)
    try {
      await transactionsApi.update(active.id, { review_status: status })
      setSavedId(active.id)
      setActive(null)
      refetch()
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <PageSpinner />

  const pending = (txns ?? []).filter(t => t.id !== savedId)

  return (
    <div className="flex flex-col overflow-hidden">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <h1 className="text-base font-semibold text-gray-900">Review queue</h1>
        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
          {pending.length} pending
        </span>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="w-1/2 overflow-auto border-r border-gray-200">
          {pending.length === 0 ? (
            <div className="flex h-64 items-center justify-center text-sm text-gray-400">
              All caught up ✓
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-gray-50">
                <tr className="border-b border-gray-100">
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Date</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Description</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-gray-400">Amount</th>
                </tr>
              </thead>
              <tbody>
                {pending.map(txn => (
                  <tr
                    key={txn.id}
                    onClick={() => setActive(txn)}
                    className={`cursor-pointer border-b border-gray-50 last:border-0 hover:bg-gray-50 ${active?.id === txn.id ? 'bg-blue-50' : ''}`}
                  >
                    <td className="px-4 py-3 text-gray-500 tabular-nums">{txn.transaction_date}</td>
                    <td className="px-4 py-3 max-w-[180px] truncate text-gray-800">
                      {txn.description_clean ?? txn.description_raw ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      <DirectionBadge direction={txn.direction} amount={txn.amount} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="w-1/2 overflow-auto p-5">
          {!active ? (
            <div className="flex h-48 items-center justify-center rounded-xl border-2 border-dashed border-gray-200 text-sm text-gray-400">
              Select a transaction to review
            </div>
          ) : (
            <div className="space-y-4">
              <h2 className="text-sm font-semibold text-gray-700">Transaction detail</h2>

              <dl className="divide-y divide-gray-100 rounded-xl border border-gray-200 bg-white text-sm">
                {[
                  ['Description', active.description_clean ?? active.description_raw ?? '—'],
                  ['Date', active.transaction_date],
                  ['Amount', <DirectionBadge direction={active.direction} amount={active.amount} />],
                  ['Merchant', active.merchant_name ?? '—'],
                  ['Type', <TxTypeBadge type={active.transaction_type} />],
                  ['Confidence', confidence(active.confidence_score)],
                  ['Notes', active.notes ?? '—'],
                ].map(([label, val]) => (
                  <div key={String(label)} className="flex justify-between gap-4 px-4 py-2.5">
                    <dt className="text-gray-400">{label}</dt>
                    <dd className="text-right font-medium text-gray-800">{val as React.ReactNode}</dd>
                  </div>
                ))}
              </dl>

              <div className="flex gap-2">
                <button
                  onClick={() => approve('user_approved')}
                  disabled={saving}
                  className="flex-1 rounded-lg bg-green-600 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
                >
                  Approve
                </button>
                <button
                  onClick={() => approve('ignored')}
                  disabled={saving}
                  className="flex-1 rounded-lg border border-gray-200 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-60"
                >
                  Ignore
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
