import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],

  // Forward /api and /health to the FastAPI backend during development.
  // In production, FastAPI serves the built dist/ directly (single container).
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,        // proxy WebSocket connections too
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },

  // Ensure Carbon SCSS variables are available globally without explicit imports
  css: {
    preprocessorOptions: {
      scss: {
        // silence Carbon's deprecation warnings about legacy @import
        quietDeps: true,
        api: 'modern-compiler',
      },
    },
  },
})
