import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const API_TARGET = 'http://127.0.0.1:8000';

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
