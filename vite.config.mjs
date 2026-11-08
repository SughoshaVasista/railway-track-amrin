import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: apiProxy,
    watch: {
      // Python environments, datasets and training outputs are not frontend
      // source. Watching them causes Vite to crawl/reload thousands of files.
      ignored: [
        '**/.venv/**',
        '**/.venv-ml/**',
        '**/.venv-training/**',
        '**/data/**',
        '**/runs/**',
      ],
    },
  },
  preview: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: apiProxy,
  },
})
