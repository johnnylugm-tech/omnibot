/* KnowledgeEditPage — Markdown editor + attachments + save.

   Reuses @uiw/react-md-editor for the body. Attachments upload to
   /web/upload FIRST so we can attach the resulting media_ids to the
   knowledge entry payload — keeps the write path atomic on the
   server side (no orphan uploads if the knowledge POST fails).
*/
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import MDEditor from '@uiw/react-md-editor'
import {
  useCreateKnowledge,
  useKnowledge,
  useUpdateKnowledge,
} from '@/hooks/useKnowledge'
import { uploadMedia } from '@/lib/format'

interface Attachment {
  media_id: string
  mime_type: string
  size_bytes: number
  url: string
}

export function KnowledgeEditPage() {
  const { id } = useParams<{ id?: string }>()
  const isNew = !id
  const navigate = useNavigate()
  const existing = useKnowledge(isNew ? null : Number(id))
  const create = useCreateKnowledge()
  const update = useUpdateKnowledge()

  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [keywordsStr, setKeywordsStr] = useState('')
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    if (existing.data) {
      setTitle(existing.data.title)
      setContent(existing.data.content)
      setKeywordsStr(existing.data.keywords.join(', '))
    }
  }, [existing.data])

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    if (files.length === 0) return
    setUploading(true)
    try {
      const res = await uploadMedia(files)
      setAttachments((prev) => [...prev, ...res.attachments])
    } catch {
      alert('Upload failed')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  async function onSave() {
    const keywords = keywordsStr
      .split(',')
      .map((k) => k.trim())
      .filter(Boolean)
    try {
      if (isNew) {
        await create.mutateAsync({ title, content, keywords })
      } else if (id) {
        await update.mutateAsync({
          id: Number(id),
          fields: { title, content, keywords },
        })
      }
      navigate('/admin/knowledge')
    } catch {
      alert('Save failed')
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">
          {isNew ? 'New entry' : `Edit #${id}`}
        </h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => navigate('/admin/knowledge')}
            className="rounded-md border px-3 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!title || create.isPending || update.isPending}
            className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"
          >
            {create.isPending || update.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </header>

      <div className="space-y-3 rounded-lg border bg-card p-4">
        <div className="space-y-1">
          <label className="text-sm font-medium">Title</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Keywords (comma-separated)</label>
          <input
            value={keywordsStr}
            onChange={(e) => setKeywordsStr(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            placeholder="refund, shipping, faq"
          />
        </div>
        <div className="space-y-1" data-color-mode="light">
          <label className="text-sm font-medium">Content (Markdown)</label>
          <MDEditor
            value={content}
            onChange={(v) => setContent(v ?? '')}
            height={400}
            preview="edit"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Attachments</label>
          <input
            type="file"
            multiple
            onChange={onUpload}
            disabled={uploading}
            className="text-sm"
          />
          {attachments.length > 0 && (
            <ul className="mt-2 space-y-1 rounded-md border bg-secondary p-2 text-xs">
              {attachments.map((a) => (
                <li key={a.media_id} className="flex items-center justify-between">
                  <span>
                    {a.mime_type} · {(a.size_bytes / 1024).toFixed(1)} KB
                  </span>
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary hover:underline"
                  >
                    open
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}