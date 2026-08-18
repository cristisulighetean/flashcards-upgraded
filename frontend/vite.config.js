import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'

// TLS is off here by default. The certificate basicSsl generates is
// self-signed, so every browser refuses to verify it — in production the
// reverse proxy in front (Caddy) terminates HTTPS with a real certificate and
// talks plain HTTP to this container. Set PREVIEW_HTTPS=true to serve TLS
// directly anyway; expect the browser warning that comes with it.
const useHttps = process.env.PREVIEW_HTTPS === 'true'

// https://vite.dev/config/
export default defineConfig({
  base: '/flashcards/',
  plugins: [react(), ...(useHttps ? [basicSsl()] : [])],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/flashcards/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/flashcards\/api/, '/api'),
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 80,
    https: useHttps,
    proxy: {
      '/flashcards/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/flashcards\/api/, '/api'),
      },
      '/flashcards/docs': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/flashcards/redoc': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/flashcards/openapi.json': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
