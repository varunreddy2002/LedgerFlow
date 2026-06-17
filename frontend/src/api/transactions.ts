import { api } from './client'
import type { Transaction, TransactionFilters, TransactionSummary, TransactionUpdate } from '../types'

function buildQuery(filters: TransactionFilters): string {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== '') params.set(k, String(v))
  })
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export const transactionsApi = {
  list: (businessId: number, filters: TransactionFilters = {}) =>
    api.get<Transaction[]>(
      `/businesses/${businessId}/transactions${buildQuery(filters)}`,
    ),

  summary: (businessId: number, startDate?: string, endDate?: string) => {
    const filters: Record<string, string> = {}
    if (startDate) filters.start_date = startDate
    if (endDate) filters.end_date = endDate
    return api.get<TransactionSummary>(
      `/businesses/${businessId}/transactions/summary${buildQuery(filters)}`,
    )
  },

  get: (id: number) => api.get<Transaction>(`/transactions/${id}`),

  update: (id: number, payload: TransactionUpdate) =>
    api.patch<Transaction>(`/transactions/${id}`, payload),
}
