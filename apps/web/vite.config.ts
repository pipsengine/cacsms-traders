import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/** Development-only backend for the dev server proxy (not VITE_-prefixed, so never shipped to the browser). */
const API_TARGET = process.env.DEV_API_ORIGIN || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Every FastAPI route lives under /api — same path layout as the Vercel /api proxy in production.
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
});
