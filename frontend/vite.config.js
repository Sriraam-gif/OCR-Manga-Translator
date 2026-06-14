import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend target. Defaults to the local CPU backend; set VITE_BACKEND_URL to a
// Colab GPU tunnel URL (e.g. https://xxxx.trycloudflare.com) to run on GPU.
const BACKEND = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
const proxyOpts = { target: BACKEND, changeOrigin: true, secure: true }

// Proxy API calls to the FastAPI backend so the browser hits the Vite origin
// (no CORS) during development.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/translate-chapter': proxyOpts,
      '/translate-image': proxyOpts,
    },
  },
})
