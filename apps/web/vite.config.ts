import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const apiTarget = process.env.AGENTBOX_E2E_API_URL ?? 'http://127.0.0.1:8787'
const proxy = {
  '/api': apiTarget,
  '/healthz': apiTarget,
  '/readyz': apiTarget,
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    proxy,
  },
  preview: {
    host: '127.0.0.1',
    proxy,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
