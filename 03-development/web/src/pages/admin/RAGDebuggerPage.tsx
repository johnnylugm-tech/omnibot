/* RAGDebuggerPage — query input + sandbox slider + 3-section result pane.

   FR-102 contract (test_fr102.py L447-486):
     * ``saved_threshold`` MUST remain the value returned by
       ``GET /admin/rag/saved-threshold`` regardless of slider position.
     * The backend's ``set_slider_threshold`` only mutates an instance
       attribute; it never touches ``platform_configs``.
     * The frontend renders the sandbox value next to the saved value
       so a regression that flips the backend would be visible here.
*/
import { useState } from 'react'
import { useRAGDebug, useRAGSavedThreshold, useRAGSetSlider } from '@/hooks/useRAG'
import type { RAGDebugResponse } from '@/lib/format'

const SECTION_TITLES: Record<string, string> = {
  ilike_results: 'Tier 1 · ILIKE matches',
  cosine_scores: 'Tier 2 · Cosine hits',
  rrf_top3: 'RRF Top-3 (k=60)',
}

function ResultSection({ section, data }: { section: string; data: RAGDebugResponse }) {
  if (section === 'ilike_results') {
    return (
      <ul className="space-y-2 text-sm">
        {data.ilike_results.length === 0 && <li className="text-muted-foreground">No ILIKE matches</li>}
        {data.ilike_results.map((m, i) => (
          <li key={i} className="rounded-md border bg-secondary p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>row #{m.row_id}</span>
              <span>conf {m.confidence.toFixed(3)}</span>
            </div>
            <p className="mt-1 line-clamp-3">{m.content}</p>
          </li>
        ))}
      </ul>
    )
  }
  if (section === 'cosine_scores') {
    return (
      <ul className="space-y-2 text-sm">
        {data.cosine_scores.length === 0 && <li className="text-muted-foreground">No cosine hits above threshold</li>}
        {data.cosine_scores.map((c, i) => (
          <li key={i} className="flex items-center justify-between rounded-md border bg-secondary p-3">
            <span className="font-mono text-xs">{c.chunk_id}</span>
            <span className="text-xs text-muted-foreground">score {c.score.toFixed(3)}</span>
          </li>
        ))}
      </ul>
    )
  }
  // rrf_top3
  return (
    <ul className="space-y-2 text-sm">
      {data.rrf_top3.length === 0 && <li className="text-muted-foreground">No RRF results</li>}
      {data.rrf_top3.map((r) => (
        <li key={r.rank} className="rounded-md border bg-secondary p-3">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>rank #{r.rank} · parent #{r.parent_id}</span>
            <span>score {r.score.toFixed(4)}</span>
          </div>
          <p className="mt-1 line-clamp-3">{r.content}</p>
        </li>
      ))}
    </ul>
  )
}

export function RAGDebuggerPage() {
  const [query, setQuery] = useState('')
  const [threshold, setThreshold] = useState(0.75)
  const savedQ = useRAGSavedThreshold()
  const setSlider = useRAGSetSlider()
  const debug = useRAGDebug()

  const saved = savedQ.data ?? 0.75
  const lastResult = debug.data

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">RAG Debugger</h1>
        <p className="text-sm text-muted-foreground">
          Sandbox RAG query — sandbox slider does not persist.
        </p>
      </header>

      <section className="rounded-lg border bg-card p-4">
        <div className="grid gap-4 md:grid-cols-[1fr_auto]">
          <div className="space-y-1">
            <label className="text-sm font-medium">Query</label>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="退款流程是什麼？"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </div>
          <button
            type="button"
            onClick={() => debug.mutate({ query, threshold })}
            disabled={!query || debug.isPending}
            className="self-end rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
          >
            {debug.isPending ? 'Running…' : 'Run debug'}
          </button>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-[1fr_180px]">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Sandbox threshold</label>
              <span className="font-mono text-sm">{threshold.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={threshold}
              onChange={(e) => {
                const v = parseFloat(e.target.value)
                setThreshold(v)
                setSlider.mutate(v)
              }}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Sandbox value is local-only; saved threshold is unchanged.
            </p>
          </div>
          <div className="rounded-md border bg-secondary p-3">
            <div className="text-xs uppercase text-muted-foreground">Saved threshold</div>
            <div className="mt-1 font-mono text-2xl font-semibold">{saved.toFixed(2)}</div>
            <p className="mt-1 text-xs text-muted-foreground">
              Persisted in platform_configs · never overwritten by the slider
            </p>
          </div>
        </div>
      </section>

      {debug.error && (
        <div className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          Debug request failed.
        </div>
      )}

      {lastResult && (
        <section className="grid gap-4 md:grid-cols-3">
          {lastResult.sections.map((s) => (
            <div key={s} className="rounded-lg border bg-card p-4">
              <h3 className="mb-3 text-sm font-medium">{SECTION_TITLES[s] ?? s}</h3>
              <ResultSection section={s} data={lastResult} />
            </div>
          ))}
        </section>
      )}
    </div>
  )
}