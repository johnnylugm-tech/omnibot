import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // [P0] Vite proxies /api + /ws to the FastAPI dev server so the
    // browser sees a single origin (no preflight, no cookie dance).
    // JWT travels in the Authorization header (credentials=false) so
    // CORS is structurally bypassed. /ws proxy enables the P3
    // portalSocket + P4 chatSocket without extra config — the
    // ``ws: true`` flag preserves the Upgrade handshake.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})