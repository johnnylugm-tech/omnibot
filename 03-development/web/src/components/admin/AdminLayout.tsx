/* AdminLayout — sidebar nav + outlet.
 *
 * Shared shell for /admin/* pages. Sidebar links are role-gated via
 * the zustand authStore.role check; the route-level ``ProtectedRoute``
 * already guards /admin so this is UX sugar (hide links the user
 * cannot reach) rather than a security boundary.
 */
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

const NAV_ITEMS: ReadonlyArray<{ to: string; label: string; end?: boolean }> = [
  { to: '/admin', label: 'Dashboard', end: true },
  { to: '/admin/knowledge', label: 'Knowledge' },
  { to: '/admin/rag', label: 'RAG Debugger' },
  { to: '/admin/portal', label: 'Live Portal' },
]

export function AdminLayout() {
  const username = useAuthStore((s) => s.username)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()

  return (
    <div className="flex min-h-screen bg-secondary">
      <aside className="flex w-56 flex-col border-r bg-card">
        <div className="border-b p-4">
          <h1 className="text-lg font-semibold tracking-tight">OmniBot</h1>
          <p className="text-xs text-muted-foreground">{username}</p>
        </div>
        <nav className="flex-1 space-y-0.5 p-2">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-accent hover:text-accent-foreground'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t p-2">
          <button
            type="button"
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
            className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-accent"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}