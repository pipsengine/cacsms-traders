/** Block until the local API accepts connections (avoids Vite proxy ECONNREFUSED on /api/auth/me). */
import http from 'node:http';

const target = process.env.DEV_API_HEALTH_URL || 'http://127.0.0.1:8000/api/health/live';
const timeoutMs = Number(process.env.DEV_API_WAIT_MS || 120_000);
const intervalMs = 400;

function probe() {
  return new Promise((resolve) => {
    const req = http.get(target, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.setTimeout(2500, () => {
      req.destroy();
      resolve(false);
    });
    req.on('error', () => resolve(false));
  });
}

const started = Date.now();
process.stderr.write('[wait-for-api] Waiting for API…\n');

while (Date.now() - started < timeoutMs) {
  if (await probe()) {
    process.stderr.write('[wait-for-api] API is up.\n');
    process.exit(0);
  }
  await new Promise((r) => setTimeout(r, intervalMs));
}

process.stderr.write('[wait-for-api] Timed out waiting for API.\n');
process.exit(1);
