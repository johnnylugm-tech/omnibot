/* Zustand auth store — single source of truth for ``role``/``username``.

   Token persistence is delegated to ``lib/api-client`` so the axios
   interceptor and the store stay consistent without a circular
   import. The store exposes the minimal surface the App + LoginPage
   need; refresh-token handling will be added when the refresh
   endpoint is wired in a later phase.
*/
import { create } from 'zustand'
import { fetchMe, loginRequest, readToken, writeToken, type MeResponse } from '@/lib/api-client'

export type Role = 'admin' | 'customer' | 'agent' | 'editor' | 'auditor' | 'dpo' | 'anonymous'

interface AuthState {
  username: string | null
  role: Role
  exp: number | null
  loading: boolean
  error: string | null

  /** Initialise from localStorage + /auth/me. Safe to call multiple times. */
  hydrate: () => Promise<void>
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  username: null,
  role: 'anonymous',
  exp: null,
  loading: false,
  error: null,

  hydrate: async () => {
    const token = readToken()
    if (!token) return
    set({ loading: true, error: null })
    try {
      const me: MeResponse = await fetchMe()
      set({
        username: me.username,
        role: me.role as Role,
        exp: me.exp,
        loading: false,
      })
    } catch {
      // Token invalid / expired — drop it and surface as anonymous.
      writeToken(null)
      set({ username: null, role: 'anonymous', exp: null, loading: false })
    }
  },

  login: async (username, password) => {
    set({ loading: true, error: null })
    try {
      const { access } = await loginRequest(username, password)
      writeToken(access)
      const me = await fetchMe()
      set({
        username: me.username,
        role: me.role as Role,
        exp: me.exp,
        loading: false,
        error: null,
      })
    } catch (err) {
      const message =
        (err as { response?: { status?: number } }).response?.status === 401
          ? 'Invalid username or password'
          : 'Login failed — please retry'
      writeToken(null)
      set({ username: null, role: 'anonymous', exp: null, loading: false, error: message })
      throw err
    }
  },

  logout: () => {
    writeToken(null)
    set({ username: null, role: 'anonymous', exp: null, error: null })
  },
}))