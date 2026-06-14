import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy API calls to the FastAPI backend so the browser hits the Vite origin
// (no CORS) during development.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/translate-chapter': 'http://127.0.0.1:8000',
      '/translate-image': 'http://127.0.0.1:8000',
    },
  },
})
