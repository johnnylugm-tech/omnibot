/* App shell — QueryClientProvider + RouterProvider + hydration.

   The hydrate() call fires once on mount so a refresh after login
   doesn't bounce the user back to /login. Subsequent role changes
   are driven by login/logout actions, not by this effect.
*/
import { useEffect } from 'react'
import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { router } from '@/router'
import { useAuthStore } from '@/stores/authStore'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // [NFR-37] Dashboard / Knowledge lists get a 30s freshness window
      // so the dev-server proxy hits the backend at most once per
      // page-stay rather than on every component re-render.
      staleTime: 30_000,
      retry: 1,
    },
  },
})

export default function App() {
  const hydrate = useAuthStore((s) => s.hydrate)
  useEffect(() => {
    void hydrate()
  }, [hydrate])

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}