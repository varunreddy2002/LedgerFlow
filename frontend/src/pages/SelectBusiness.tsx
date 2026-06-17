import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useBusiness } from '../context/BusinessContext'
import { businessesApi } from '../api/businesses'

export default function SelectBusiness() {
  const { businesses, select } = useBusiness()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    setError('')
    try {
      const biz = await businessesApi.create({ name: name.trim(), currency: 'USD' })
      await businessesApi.setup(biz.id)
      select(biz)
      navigate('/dashboard')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create business')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <span className="text-4xl text-blue-600">◈</span>
          <h1 className="mt-2 text-2xl font-semibold text-gray-900">LedgerFlow</h1>
          <p className="mt-1 text-sm text-gray-500">Select or create a business to get started</p>
        </div>

        {businesses.length > 0 && (
          <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Existing businesses
            </p>
            <ul className="space-y-2">
              {businesses.map(b => (
                <li key={b.id}>
                  <button
                    onClick={() => { select(b); navigate('/dashboard') }}
                    className="flex w-full items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-4 py-3 text-left text-sm font-medium text-gray-800 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
                  >
                    <span>{b.name}</span>
                    <span className="text-xs text-gray-400">{b.currency}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Create new business
          </p>
          <form onSubmit={handleCreate} className="space-y-3">
            <input
              type="text"
              placeholder="Business name"
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
              required
            />
            {error && <p className="text-xs text-red-600">{error}</p>}
            <button
              type="submit"
              disabled={creating}
              className="w-full rounded-lg bg-blue-600 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-60"
            >
              {creating ? 'Creating…' : 'Create & continue'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
