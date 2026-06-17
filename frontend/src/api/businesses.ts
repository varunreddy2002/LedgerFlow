import { api } from './client'
import type { Business, BusinessCreate } from '../types'

export const businessesApi = {
  list: () => api.get<Business[]>('/businesses'),
  get: (id: number) => api.get<Business>(`/businesses/${id}`),
  create: (payload: BusinessCreate) => api.post<Business>('/businesses', payload),
  setup: (id: number) => api.post(`/businesses/${id}/setup`),
}
