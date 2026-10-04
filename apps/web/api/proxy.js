// Vercel serverless function: forwards same-origin /api/* requests to the Cacsms-Traders FastAPI backend.
//
// The backend cannot run on Vercel (it needs the MT5 terminal on Windows, a durable SQLite file and long-running
// engine threads), so it runs on the trading host and is published at API_ORIGIN (e.g. a Cloudflare Tunnel URL).
// Keeping the browser on the Vercel origin lets the HttpOnly session cookie stay first-party.
//
// Server-side env (Vercel → Project → Settings → Environment Variables; never VITE_*):
//   API_ORIGIN        required, e.g. https://api.example.com  (no trailing /api)
//   API_PROXY_SECRET  optional, must match the backend's API_PROXY_SECRET

const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'host',
  'content-length',
]);
const UPSTREAM_TIMEOUT_MS = 25000;

function json(status, detail) {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}

async function proxy(request) {
  const origin = (process.env.API_ORIGIN || '').trim().replace(/\/+$/, '');
  if (!origin) {
    return json(503, 'Backend API is not configured: set API_ORIGIN in the Vercel project environment and redeploy.');
  }

  const incoming = new URL(request.url);
  const params = new URLSearchParams(incoming.search);
  const path = (params.get('__path') ?? incoming.pathname.replace(/^\/api\/?/, '')).replace(/^\/+/, '');
  params.delete('__path');
  const search = params.toString();
  const target = `${origin}/api/${path}${search ? `?${search}` : ''}`;

  const headers = new Headers();
  for (const [key, value] of request.headers) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  }
  headers.set('x-forwarded-host', incoming.host);
  headers.set('x-forwarded-proto', 'https');
  const clientIp = request.headers.get('x-real-ip') || request.headers.get('x-forwarded-for')?.split(',')[0]?.trim();
  if (clientIp) headers.set('x-forwarded-for', clientIp);
  const secret = (process.env.API_PROXY_SECRET || '').trim();
  if (secret) headers.set('x-ct-proxy-secret', secret);

  const method = request.method.toUpperCase();
  const body = method === 'GET' || method === 'HEAD' ? undefined : await request.arrayBuffer();

  let upstream;
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body,
      redirect: 'manual',
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (err) {
    console.error('API proxy: upstream unreachable', err?.name || 'Error');
    return json(502, 'Backend API is unreachable. Check that the trading host and its tunnel are running.');
  }

  const out = new Headers();
  for (const [key, value] of upstream.headers) {
    const k = key.toLowerCase();
    if (HOP_BY_HOP.has(k) || k === 'content-encoding' || k === 'set-cookie') continue;
    out.set(key, value);
  }
  for (const cookie of upstream.headers.getSetCookie?.() ?? []) out.append('set-cookie', cookie);
  if (!out.has('cache-control')) out.set('cache-control', 'no-store');

  const noBody = method === 'HEAD' || [204, 304].includes(upstream.status);
  return new Response(noBody ? null : upstream.body, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
export const OPTIONS = proxy;
