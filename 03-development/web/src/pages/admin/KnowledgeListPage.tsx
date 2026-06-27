/* KnowledgeListPage — table with embedding-status chips + import + delete. */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useDeleteKnowledge,
  useEmbeddingStatus,
  useImportCSV,
  useKnowledgeList,
} from '@/hooks/useKnowledge'

const STATUS_CHIP: Record<string, string> = {
  synced: 'bg-green-100 text-green-700',
  syncing: 'bg-yellow-100 text-yellow-700',
  failed: 'bg-red-100 text-red-700',
}

export function KnowledgeListPage() {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useKnowledgeList(page, 20)
  const embedding = useEmbeddingStatus()
  const del = useDeleteKnowledge()
  const importCSV = useImportCSV()
  const navigate = useNavigate()

  function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    importCSV.mutate(file, {
      onSuccess: (r) => alert(`Imported ${r.imported}, skipped ${r.skipped}`),
      onError: () => alert('Import failed'),
    })
    e.target.value = ''
  }

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Knowledge Base</h1>
          {embedding.data && (
            <p className="text-sm text-muted-foreground">
              Embedding sync: {embedding.data.display} ({embedding.data.chunks_synced}/{embedding.data.total})
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <label className="cursor-pointer rounded-md border bg-card px-3 py-2 text-sm hover:bg-accent">
            Import CSV
            <input type="file" accept=".csv" className="hidden" onChange={onUpload} />
          </label>
          <button
            type="button"
            onClick={() => navigate('/admin/knowledge/new')}
            className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:opacity-90"
          >
            New entry
          </button>
        </div>
      </header>

      <div className="overflow-hidden rounded-lg border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b bg-secondary text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Keywords</th>
              <th className="px-4 py-3">Embedding</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={4} className="p-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            ) : data && data.items.length > 0 ? (
              data.items.map((e) => (
                <tr key={e.id} className="border-b last:border-0 hover:bg-secondary/50">
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => navigate(`/admin/knowledge/${e.id}`)}
                      className="text-left font-medium hover:underline"
                    >
                      {e.title}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {e.keywords.slice(0, 3).map((k) => (
                        <span
                          key={k}
                          className="rounded-full bg-secondary px-2 py-0.5 text-xs"
                        >
                          {k}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        STATUS_CHIP[e.embedding_status] ?? 'bg-secondary text-muted-foreground'
                      }`}
                    >
                      {e.embedding_status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => e.id && del.mutate(e.id)}
                      className="text-xs text-destructive hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={4} className="p-6 text-center text-muted-foreground">
                  No entries yet — create one to get started.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && data.total > data.limit && (
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="rounded-md border px-3 py-1 text-sm disabled:opacity-50"
          >
            Prev
          </button>
          <span className="text-sm text-muted-foreground">
            Page {page} / {Math.ceil(data.total / data.limit)}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={page * data.limit >= data.total}
            className="rounded-md border px-3 py-1 text-sm disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}