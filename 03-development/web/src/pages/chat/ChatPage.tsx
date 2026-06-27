/* ChatPage — ChatGPT-style web chat with multimedia.

   Bootstrap (on mount):
     1. POST /web/guest-session  → JWT (stored in sessionStorage so
        a refresh reuses the same identity; logging out clears it).
     2. WS /ws/user?token=<jwt>  → register connection
     3. subscribe channel user:<sub>  → server acks with subscribed

   Send flow:
     a. User types / drags file.
     b. If file attached: POST /web/upload (multipart) → media_ids.
     c. Optimistic append: user message with attachment previews.
     d. POST /web/message {content, conversation_id, attachments}.
     e. Response carries the bot's message_id + content + source.
     f. WS pushes message.reply for the same conversation; merge into
        the list (replace optimistic bot bubble if present, or append
        fresh).
*/
import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import ReconnectingWebSocket from 'reconnecting-websocket'
import { apiClient } from '@/lib/api-client'

interface Attachment {
  media_id: string
  mime_type: string
  size_bytes: number
  message_type: string
  url: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'bot' | 'agent'
  content: string
  attachments?: Attachment[]
  source?: string
  timestamp: number
}

const GUEST_TOKEN_KEY = 'omnibot.chat.guest_token'
const GUEST_SUB_KEY = 'omnibot.chat.guest_sub'

async function ensureGuestToken(): Promise<{ token: string; sub: string }> {
  const existing = sessionStorage.getItem(GUEST_TOKEN_KEY)
  const sub = sessionStorage.getItem(GUEST_SUB_KEY)
  if (existing && sub) return { token: existing, sub }
  const { data } = await apiClient.post<{ token: string }>('/web/guest-session')
  const token = data.token
  // Decode sub claim without full JWT verification — the server
  // will reject forged tokens on the first request anyway.
  const payloadB64 = token.split('.')[1] ?? ''
  const json = atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/'))
  const sub2 = (JSON.parse(json) as { sub: string }).sub
  sessionStorage.setItem(GUEST_TOKEN_KEY, token)
  sessionStorage.setItem(GUEST_SUB_KEY, sub2)
  return { token, sub: sub2 }
}

function MediaPreview({ a }: { a: Attachment }) {
  if (a.mime_type.startsWith('image/')) {
    return (
      <img
        src={a.url}
        alt={a.mime_type}
        className="max-h-48 rounded-md border"
      />
    )
  }
  if (a.mime_type.startsWith('audio/')) {
    return <audio controls src={a.url} className="w-full" />
  }
  if (a.mime_type.startsWith('video/')) {
    return <video controls src={a.url} className="max-h-48 rounded-md border" />
  }
  return (
    <a
      href={a.url}
      download
      className="flex items-center gap-2 rounded-md border bg-secondary px-3 py-2 text-xs hover:bg-accent"
    >
      📎 {a.mime_type} · {(a.size_bytes / 1024).toFixed(1)} KB
    </a>
  )
}

function MessageBubble({ m }: { m: ChatMessage }) {
  const isUser = m.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-lg border px-4 py-3 shadow-sm ${
          isUser ? 'bg-primary text-primary-foreground' : 'bg-card'
        }`}
      >
        {m.attachments && m.attachments.length > 0 && (
          <div className="mb-2 flex flex-col gap-2">
            {m.attachments.map((a) => (
              <MediaPreview key={a.media_id} a={a} />
            ))}
          </div>
        )}
        {m.content && (
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {m.content}
            </ReactMarkdown>
          </div>
        )}
        {m.source && m.source === 'escalate' && (
          <p className="mt-2 rounded-md bg-yellow-100 px-2 py-1 text-xs text-yellow-800">
            ⚠ Conversation escalated to a human agent
          </p>
        )}
      </div>
    </div>
  )
}

interface PendingAttachment extends File {
  previewUrl: string
}

export function ChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [pending, setPending] = useState<PendingAttachment[]>([])
  const [sending, setSending] = useState(false)
  const [handoff, setHandoff] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<ReconnectingWebSocket | null>(null)

  // Bootstrap: guest JWT + WS connection.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      const { token, sub } = await ensureGuestToken()
      if (cancelled) return
      const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/user?token=${encodeURIComponent(token)}`
      const ws = new ReconnectingWebSocket(wsUrl, [], {
        maxRetries: Infinity,
        reconnectionDelayGrowFactor: 1,
        connectionTimeout: 5_000,
      })
      wsRef.current = ws
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string) as {
            type?: string
            event?: string
            payload?: {
              conversation_id: string
              message_id: string
              content: string
              source: string
              attachments: Attachment[]
            }
          }
          if (msg.type === 'event' && msg.event === 'message.reply' && msg.payload) {
            const p = msg.payload
            if (p.conversation_id !== conversationIdRef.current) return
            setMessages((prev) => {
              // Replace optimistic bot bubble if its id matches.
              const idx = prev.findIndex((m) => m.id === p.message_id)
              const bot: ChatMessage = {
                id: p.message_id,
                role: p.source === 'escalate' ? 'agent' : 'bot',
                content: p.content,
                source: p.source,
                attachments: p.attachments,
                timestamp: Date.now(),
              }
              if (idx >= 0) {
                const next = [...prev]
                next[idx] = bot
                return next
              }
              return [...prev, bot]
            })
            if (p.source === 'escalate') setHandoff(true)
          }
        } catch {
          /* ignore malformed frame */
        }
      }
      // Subscribe explicitly after connect (server auto-subscribes
      // too but echoing the subscribe keeps the channel registry
      // in sync if the server's auto-subscribe ever drops).
      ws.onopen = () => {
        ws.send(JSON.stringify({ action: 'subscribe', channel: `user:${sub}` }))
      }
    })()
    return () => {
      cancelled = true
      wsRef.current?.close()
    }
  }, [])

  // Track the latest conversation_id in a ref so the WS handler
  // closure (captured on mount) can filter without re-subscribing.
  const conversationIdRef = useRef<string | null>(null)
  useEffect(() => {
    conversationIdRef.current = conversationId
  }, [conversationId])

  // Auto-scroll on new messages.
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const files = Array.from(e.dataTransfer.files).map((f) => {
      const pf = f as PendingAttachment
      pf.previewUrl = f.type.startsWith('image/') ? URL.createObjectURL(f) : ''
      return pf
    })
    setPending((prev) => [...prev, ...files])
  }, [])

  const removePending = (idx: number) => {
    setPending((prev) => {
      const removed = prev[idx]
      if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl)
      return prev.filter((_, i) => i !== idx)
    })
  }

  async function send() {
    if (sending) return
    if (!input.trim() && pending.length === 0) return
    setSending(true)
    try {
      let uploaded: Attachment[] = []
      if (pending.length > 0) {
        const res = await apiClient.post<{ attachments: Attachment[] }>(
          '/web/upload',
          (() => {
            const fd = new FormData()
            for (const f of pending) fd.append('files', f)
            return fd
          })(),
          { headers: { 'Content-Type': 'multipart/form-data' } },
        )
        uploaded = res.data.attachments
      }

      const convId = conversationId ?? `conv-${crypto.randomUUID().slice(0, 12)}`
      setConversationId(convId)

      const userMsg: ChatMessage = {
        id: `local-${Date.now()}`,
        role: 'user',
        content: input,
        attachments: uploaded,
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, userMsg])
      setInput('')
      for (const p of pending) if (p.previewUrl) URL.revokeObjectURL(p.previewUrl)
      setPending([])

      const { data } = await apiClient.post<{
        conversation_id: string
        message_id: string
        content: string
        source: string
        attachments: Attachment[]
      }>('/web/message', {
        content: input,
        conversation_id: convId,
        attachments: uploaded.map((a) => a.media_id),
      })

      // If WS already delivered the reply it would have replaced the
      // optimistic bot bubble. Otherwise append synchronously.
      setMessages((prev) => {
        if (prev.find((m) => m.id === data.message_id)) return prev
        return [
          ...prev,
          {
            id: data.message_id,
            role: data.source === 'escalate' ? 'agent' : 'bot',
            content: data.content,
            source: data.source,
            attachments: data.attachments,
            timestamp: Date.now(),
          },
        ]
      })
      if (data.source === 'escalate') setHandoff(true)
    } catch (err) {
      alert(`Send failed: ${(err as Error).message}`)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex h-screen flex-col bg-secondary">
      {handoff && (
        <div className="border-b bg-yellow-50 px-4 py-2 text-sm text-yellow-800">
          A human agent has joined the conversation. Your replies may take longer.
          <button
            type="button"
            onClick={() => setHandoff(false)}
            className="ml-3 text-xs underline"
          >
            dismiss
          </button>
        </div>
      )}
      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-6">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Send a message to start. Drop a file to attach an image / audio / video / PDF.
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} m={m} />
        ))}
      </div>

      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        className="border-t bg-card p-4"
      >
        {pending.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {pending.map((p, i) => (
              <div key={i} className="relative rounded-md border bg-secondary p-1">
                {p.previewUrl ? (
                  <img src={p.previewUrl} alt="" className="h-16 w-16 rounded object-cover" />
                ) : (
                  <span className="px-2 text-xs">{p.name}</span>
                )}
                <button
                  type="button"
                  onClick={() => removePending(i)}
                  className="absolute -right-1 -top-1 rounded-full bg-destructive px-1 text-xs text-destructive-foreground"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
            placeholder="Type a message… (Shift+Enter for newline)"
            rows={2}
            className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            type="button"
            onClick={() => void send()}
            disabled={sending || (!input.trim() && pending.length === 0)}
            className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
          >
            {sending ? 'Sending…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}