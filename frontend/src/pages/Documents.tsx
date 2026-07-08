import { useRef, useState } from 'react'
import { useBusiness } from '../context/BusinessContext'
import { useAsync } from '../hooks/useAsync'
import { documentsApi } from '../api/documents'
import { DocStatusBadge } from '../components/ui/Badge'
import { PageSpinner } from '../components/ui/Spinner'
import type { UploadResponse } from '../types'

export default function Documents() {
  const { selected } = useBusiness()
  const id = selected!.id
  const { data: docs, loading, refetch } = useAsync(() => documentsApi.list(id), [id])

  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<UploadResponse | null>(null)
  const [uploadError, setUploadError] = useState('')
  const [dragging, setDragging] = useState(false)

  async function upload(file: File) {
    setUploading(true)
    setResult(null)
    setUploadError('')
    try {
      const res = await documentsApi.upload(id, file)
      setResult(res)
      refetch()
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) upload(file)
  }

  return (
    <div className="flex flex-col overflow-auto">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <h1 className="text-base font-semibold text-gray-900">Documents</h1>
        <button
          onClick={() => inputRef.current?.click()}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          ↑ Upload file
        </button>
      </header>

      <div className="flex-1 space-y-5 p-6">
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition ${
            dragging ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
          }`}
        >
          <p className="text-3xl text-gray-300">↑</p>
          <p className="mt-2 text-sm font-medium text-gray-600">Drop a file or click to browse</p>
          <p className="mt-1 text-xs text-gray-400">Supports .csv (bank statements) and .pdf (invoices)</p>
          {uploading && <p className="mt-2 text-xs text-blue-600">Uploading…</p>}
        </div>

        <input
          ref={inputRef}
          type="file"
          accept=".csv,.pdf"
          className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = '' }}
        />

        {uploadError && (
          <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200">
            {uploadError}
          </div>
        )}

        {result && (
          <div className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-800 ring-1 ring-green-200">
            File uploaded — processing in background.
          </div>
        )}

        <div>
          <h2 className="mb-3 text-sm font-medium text-gray-700">All documents</h2>
          {loading ? <PageSpinner /> : (
            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
              {!docs || docs.length === 0 ? (
                <p className="px-4 py-8 text-center text-sm text-gray-400">No documents yet</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Filename</th>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Type</th>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Uploaded</th>
                      <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {docs.map(doc => (
                      <tr key={doc.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50">
                        <td className="px-4 py-2.5 font-medium text-gray-800">{doc.filename}</td>
                        <td className="px-4 py-2.5 text-gray-500 capitalize">{doc.source.replace(/_/g, ' ')}</td>
                        <td className="px-4 py-2.5 text-gray-500">{new Date(doc.uploaded_at).toLocaleDateString()}</td>
                        <td className="px-4 py-2.5"><DocStatusBadge status={doc.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
