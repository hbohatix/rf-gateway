import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The UI calls the API on its own origin (/api/...). Both the dev server and
// `vite preview` forward those requests to the FastAPI backend.
const backend = process.env.RFGW_BACKEND_URL ?? 'http://127.0.0.1:8000'

const proxy = {
  '/api': {
    target: backend,
    changeOrigin: true,
  },
  '/docs': backend,
  '/openapi.json': backend,
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
})
