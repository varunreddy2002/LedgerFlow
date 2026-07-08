import { useBusiness } from '../context/BusinessContext'
import { useAsync } from '../hooks/useAsync'
import { transactionsApi } from '../api/transactions'
import { documentsApi } from '../api/documents'
import { MetricCard } from '../components/ui/MetricCard'
import { DocStatusBadge } from '../components/ui/Badge'
import { PageSpinner } from '../components/ui/Spinner'

function fmt(n: number) {
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export default function Dashboard() {
  const { selected } = useBusiness()
  const id = selected!.id

  const summary = useAsync(() => transactionsApi.summary(id), [id])
  const docs = useAsync(() => documentsApi.list(id), [id])

  if (summary.loading || docs.loading) return <PageSpinner />

  const s = summary.data
  const recentDocs = (docs.data ?? []).slice(0, 5)

  return (
    <div className="flex flex-col overflow-auto">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <h1 className="text-base font-semibold text-gray-900">Dashboard</h1>
        <span className="text-sm text-gray-400">{selected!.name}</span>
      </header>

      <div className="flex-1 space-y-6 p-6">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MetricCard
            label="Total inflow"
            value={s ? fmt(s.total_inflow) : '—'}
            valueClassName="text-green-700"
          />
          <MetricCard
            label="Total outflow"
            value={s ? fmt(s.total_outflow) : '—'}
            valueClassName="text-red-700"
          />
          <MetricCard
            label="Net"
            value={s ? fmt(s.net) : '—'}
          />
          <MetricCard
            label="Needs review"
            value={s?.needs_review_count ?? '—'}
            valueClassName={s && s.needs_review_count > 0 ? 'text-amber-700' : ''}
          />
        </div>

        <div>
          <h2 className="mb-3 text-sm font-medium text-gray-700">Recent documents</h2>
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
            {recentDocs.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-gray-400">No documents uploaded yet</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">File</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Type</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Uploaded</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {recentDocs.map(doc => (
                    <tr key={doc.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50">
                      <td className="px-4 py-2.5 font-medium text-gray-800">{doc.filename}</td>
                      <td className="px-4 py-2.5 text-gray-500 capitalize">{doc.source.replace(/_/g, ' ')}</td>
                      <td className="px-4 py-2.5 text-gray-500">
                        {new Date(doc.uploaded_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-2.5">
                        <DocStatusBadge status={doc.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
