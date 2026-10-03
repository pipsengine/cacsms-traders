import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const API_TARGET = 'http://127.0.0.1:8000';

/** FastAPI routes (everything except static Vite assets). */
const PROXY_PATHS = ['/api', '/auth', '/health', '/tenants', '/dashboard', '/system', '/reference'];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      PROXY_PATHS.map((path) => [
        path,
        {
          target: API_TARGET,
          changeOrigin: true,
        },
      ]),
    ),
  },
});
