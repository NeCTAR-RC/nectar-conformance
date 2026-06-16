import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, `npm run dev` serves the SPA on :5173 and proxies /api to the backend
// (`nectar-conformance-web` on :8080). In CI/the container, `npm run build` emits
// the static bundle to dist/, which the Dockerfile copies into the package's
// web/static directory.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
  build: {
    outDir: 'dist',
  },
})
