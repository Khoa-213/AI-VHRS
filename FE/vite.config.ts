import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // In dev the app calls /api on its own origin and Vite forwards it to the
    // backend, so CORS never blocks it, whatever port the dev server lands on.
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'https://ai-vhrs.onrender.com',
        changeOrigin: true,
        configure: (proxy) => {
          // The backend's CORS list does not know the dev origin; same-origin calls do not need it.
          proxy.on('proxyReq', (req) => req.removeHeader('origin'))
        },
      },
    },
  },
})
