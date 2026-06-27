import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createKnowledge,
  deleteKnowledge,
  getEmbeddingStatus,
  getKnowledge,
  importKnowledgeCSV,
  listKnowledge,
  updateKnowledge,
  type KnowledgeEntry,
} from '@/lib/format'

export function useKnowledgeList(page = 1, limit = 20) {
  return useQuery({
    queryKey: ['knowledge', 'list', page, limit],
    queryFn: () => listKnowledge(page, limit),
  })
}

export function useKnowledge(id: number | null) {
  return useQuery({
    queryKey: ['knowledge', id],
    queryFn: () => getKnowledge(id!),
    enabled: id != null,
  })
}

export function useEmbeddingStatus() {
  return useQuery({
    queryKey: ['knowledge', 'embedding-status'],
    queryFn: getEmbeddingStatus,
    refetchInterval: 5_000,
  })
}

export function useCreateKnowledge() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { title: string; content: string; keywords?: string[] }) =>
      createKnowledge(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledge'] }),
  })
}

export function useUpdateKnowledge() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: {
      id: number
      fields: Partial<Pick<KnowledgeEntry, 'title' | 'content' | 'keywords'>>
    }) => updateKnowledge(args.id, args.fields),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['knowledge'] })
      qc.invalidateQueries({ queryKey: ['knowledge', vars.id] })
    },
  })
}

export function useDeleteKnowledge() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteKnowledge(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledge'] }),
  })
}

export function useImportCSV() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => importKnowledgeCSV(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledge'] }),
  })
}