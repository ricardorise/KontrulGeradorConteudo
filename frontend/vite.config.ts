/// <reference types="vitest" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  base: process.env.VITE_BASE ?? '/', // prefixo em que o app é servido atrás de proxy reverso (deve terminar com /)
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': process.env.STUDIO_API_URL ?? 'http://localhost:8100' },
  },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test-setup.ts'] },
})
