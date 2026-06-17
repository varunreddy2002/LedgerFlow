import { api } from './client'
import type { Document, UploadResponse } from '../types'

export const documentsApi = {
  list: (businessId: number) =>
    api.get<Document[]>(`/businesses/${businessId}/documents`),

  get: (documentId: number) =>
    api.get<Document>(`/documents/${documentId}`),

  upload: (businessId: number, file: File) =>
    api.upload<UploadResponse>(`/businesses/${businessId}/documents/upload`, file),
}
