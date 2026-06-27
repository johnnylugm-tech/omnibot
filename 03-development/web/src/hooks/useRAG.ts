import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ragDebug, ragSavedThreshold, ragSetSlider } from '@/lib/format'

export function useRAGDebug() {
  return useMutation({
    mutationFn: (args: { query: string; threshold: number }) =>
      ragDebug(args.query, args.threshold),
  })
}

export function useRAGSavedThreshold() {
  return useQuery({
    queryKey: ['rag', 'saved-threshold'],
    queryFn: ragSavedThreshold,
  })
}

export function useRAGSetSlider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (threshold: number) => ragSetSlider(threshold),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rag'] }),
  })
}