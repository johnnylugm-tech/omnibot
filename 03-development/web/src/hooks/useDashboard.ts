import { useQuery } from '@tanstack/react-query'
import { getDashboard } from '@/lib/format'

export function useDashboard(range: string) {
  return useQuery({
    queryKey: ['dashboard', range],
    queryFn: () => getDashboard(range),
    // [NFR-37] placeholderData: keepPreviousData swaps the prior
    // range's metrics in while the new range loads so the chart
    // skeleton never flashes.
    placeholderData: (prev) => prev,
  })
}