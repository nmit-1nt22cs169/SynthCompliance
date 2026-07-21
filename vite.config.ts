import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  // No client-side routing here — disable the SPA history fallback so a
  // missing /data/*.jsonl file 404s properly instead of silently
  // returning index.html (which then fails JSON.parse in dataLoader.ts).
  appType: 'mpa',
  plugins: [react()],
})
