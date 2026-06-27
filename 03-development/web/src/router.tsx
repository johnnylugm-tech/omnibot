/* React Router v6 routes.

   P0 scope: only /login + a stub /admin route so the post-login
   redirect has somewhere to land. P1+ pages register here without
   touching the gate logic — ``ProtectedRoute`` reads the zustand
   ``role`` field.
*/
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom'
import { AdminLayout } from '@/components/admin/AdminLayout'
import { LoginPage } from '@/pages/LoginPage'
import { ChatPage } from '@/pages/chat/ChatPage'
import { DashboardPage } from '@/pages/admin/DashboardPage'
import { KnowledgeEditPage } from '@/pages/admin/KnowledgeEditPage'
import { KnowledgeListPage } from '@/pages/admin/KnowledgeListPage'
import { PortalPage } from '@/pages/admin/PortalPage'
import { RAGDebuggerPage } from '@/pages/admin/RAGDebuggerPage'
import { useAuthStore, type Role } from '@/stores/authStore'

function ProtectedRoute({ allow }: { allow: readonly Role[] }) {
  const role = useAuthStore((s) => s.role)
  if (role === 'anonymous') return <Navigate to="/login" replace />
  if (!allow.includes(role)) return <Navigate to="/login" replace />
  return <Outlet />
}

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/chat', element: <ChatPage /> },
  {
    element: <ProtectedRoute allow={['admin'] as const} />,
    children: [
      {
        element: <AdminLayout />,
        children: [
          { path: '/admin', element: <DashboardPage /> },
          { path: '/admin/knowledge', element: <KnowledgeListPage /> },
          { path: '/admin/knowledge/new', element: <KnowledgeEditPage /> },
          { path: '/admin/knowledge/:id', element: <KnowledgeEditPage /> },
          { path: '/admin/rag', element: <RAGDebuggerPage /> },
          { path: '/admin/portal', element: <PortalPage /> },
        ],
      },
    ],
  },
  { path: '/', element: <Navigate to="/login" replace /> },
  { path: '*', element: <Navigate to="/login" replace /> },
])