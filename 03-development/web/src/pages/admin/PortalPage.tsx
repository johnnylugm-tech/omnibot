/* PortalPage — 3-section inbox + takeover panel + WS escalation.new.
 *
 * The WS connection auto-reconnects on close (FR-104 acceptance:
 * "<1s 掌握背景" — every escalation.new must surface immediately).
 * When the backend publishes ``escalation.new`` we push the payload
 * into the local "Unassigned" section so the UI updates without
 * waiting for the next poll.
 */
import { useEffect, useRef, useState } from 'react'
import ReconnectingWebSocket from 'reconnecting-websocket'
import { useAuthStore } from '@/stores/authStore'
import { apiClient } from '@/lib/api-client'

interface Escalation {
  escalation_id: string
  conversation_id?: string
  reason?: string
  priority: number
  platform?: string
  preview?: { user_message?: string; emotion?: string }
  queued_at?: string
  assigned_agent?: string | null
  resolved_at?: string
}

const SECTIONS = ['Unassigned', 'My Chats', 'Resolved'] as const
type Section = (typeof SECTIONS)[number]

const PRIORITY_COLOR: Record<number, string> = {
  0: 'bg-blue-100 text-blue-700',
  1: 'bg-orange-100 text-orange-700',
  2: 'bg-red-100 text-red-700',
}
const PRIORITY_LABEL: Record<number, string> = { 0: 'normal', 1: 'high', 2: 'urgent' }

export function PortalPage() {
  const username = useAuthStore((s) => s.username)
  const [inbox, setInbox] = useState<Record<Section, Escalation[]>>({
    Unassigned: [],
    'My Chats': [],
    Resolved: [],
  })
  const [selected, setSelected] = useState<Escalation | null>(null)
  const [context, setContext] = useState<Record<string, unknown>>({})
  const [wsStatus, setWsStatus] = useState<'connecting' | 'open' | 'closed'>('connecting')
  const tokenRef = useRef<string | null>(null)

  // Initial load + WS connection.
  useEffect(() => {
    const token = localStorage.getItem('omnibot.auth.token')
    tokenRef.current = token
    if (!token) return

    async function loadInbox() {
      const next: Record<Section, Escalation[]> = {
        Unassigned: [],
        'My Chats': [],
        Resolved: [],
      }
      await Promise.all(
        SECTIONS.map(async (s) => {
          try {
            const { data } = await apiClient.get<{ items: Escalation[] }>(
              `/portal/inbox/${encodeURIComponent(s)}`,
            )
            next[s] = data.items
          } catch {
            next[s] = []
          }
        }),
      )
      setInbox(next)
    }
    void loadInbox()

    const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/agent?token=${encodeURIComponent(token)}`
    const ws = new ReconnectingWebSocket(wsUrl, [], {
      maxRetries: Infinity,
      reconnectionDelayGrowFactor: 1,
      connectionTimeout: 5_000,
    })
    ws.onopen = () => setWsStatus('open')
    ws.onclose = () => setWsStatus('closed')
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as {
          type?: string
          event?: string
          payload?: Escalation
        }
        if (msg.type === 'event' && msg.event === 'escalation.new' && msg.payload) {
          setInbox((prev) => ({ ...prev, Unassigned: [msg.payload!, ...prev.Unassigned] }))
        }
      } catch {
        /* malformed frame — ignore */
      }
    }
    return () => {
      ws.close()
    }
  }, [])

  async function claim(id: string) {
    await apiClient.post(`/portal/escalations/${id}/claim`, { agent_id: username })
    setInbox((prev) => {
      const moved = prev.Unassigned.find((e) => e.escalation_id === id)
      if (!moved) return prev
      return {
        ...prev,
        Unassigned: prev.Unassigned.filter((e) => e.escalation_id !== id),
        'My Chats': [{ ...moved, assigned_agent: username }, ...prev['My Chats']],
      }
    })
    if (selected?.escalation_id === id) setSelected((s) => (s ? { ...s, assigned_agent: username } : s))
  }

  async function resolve(id: string) {
    await apiClient.post(`/portal/escalations/${id}/resolve`)
    setInbox((prev) => {
      const all = [...prev.Unassigned, ...prev['My Chats']]
      const moved = all.find((e) => e.escalation_id === id)
      if (!moved) return prev
      return {
        Unassigned: prev.Unassigned.filter((e) => e.escalation_id !== id),
        'My Chats': prev['My Chats'].filter((e) => e.escalation_id !== id),
        Resolved: [{ ...moved, resolved_at: 'now' }, ...prev.Resolved],
      }
    })
    if (selected?.escalation_id === id) setSelected(null)
  }

  async function openContext(e: Escalation) {
    setSelected(e)
    try {
      const { data } = await apiClient.get(`/portal/escalations/${e.escalation_id}/takeover-context`)
      setContext(data)
    } catch {
      setContext({})
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Live Portal</h1>
        <span
          className={`flex items-center gap-2 text-xs ${
            wsStatus === 'open' ? 'text-green-700' : 'text-muted-foreground'
          }`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              wsStatus === 'open' ? 'bg-green-500' : 'bg-muted-foreground'
            }`}
          />
          WS {wsStatus}
        </span>
      </header>

      <div className="grid grid-cols-3 gap-3">
        {SECTIONS.map((s) => (
          <div key={s} className="rounded-lg border bg-card p-3">
            <h2 className="mb-2 text-sm font-semibold text-muted-foreground">
              {s} <span className="ml-1 text-xs">({inbox[s].length})</span>
            </h2>
            <ul className="space-y-2">
              {inbox[s].length === 0 && (
                <li className="text-xs text-muted-foreground">empty</li>
              )}
              {inbox[s].map((e) => (
                <li
                  key={e.escalation_id}
                  className="rounded-md border bg-secondary p-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => openContext(e)}
                      className="font-mono text-left hover:underline"
                    >
                      {e.escalation_id}
                    </button>
                    <span
                      className={`rounded-full px-2 py-0.5 ${
                        PRIORITY_COLOR[e.priority] ?? 'bg-secondary text-muted-foreground'
                      }`}
                    >
                      {PRIORITY_LABEL[e.priority] ?? 'normal'}
                    </span>
                  </div>
                  {e.reason && <p className="mt-1 line-clamp-2">{e.reason}</p>}
                  <div className="mt-1 flex gap-1">
                    {s === 'Unassigned' && (
                      <button
                        type="button"
                        onClick={() => claim(e.escalation_id)}
                        className="rounded-sm border px-2 py-0.5 text-xs hover:bg-accent"
                      >
                        Claim
                      </button>
                    )}
                    {s !== 'Resolved' && (
                      <button
                        type="button"
                        onClick={() => resolve(e.escalation_id)}
                        className="rounded-sm border px-2 py-0.5 text-xs hover:bg-accent"
                      >
                        Resolve
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {selected && (
        <section className="rounded-lg border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold">Takeover context — {selected.escalation_id}</h2>
          <div className="grid gap-3 md:grid-cols-4">
            {(['emotion', 'dst_slots', 'grounding', 'conversation'] as const).map((key) => (
              <div key={key} className="rounded-md border bg-secondary p-3">
                <div className="text-xs uppercase text-muted-foreground">{key}</div>
                <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-xs">
                  {JSON.stringify(context[key] ?? {}, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}