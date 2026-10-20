/**
 * The browser always calls its own origin under /api. Which backend that reaches is environment configuration,
 * never baked into the bundle: Vite dev proxy → local API in development, Vercel /api function → API_ORIGIN in production.
 */
export const API_PREFIX = '/api';

const DEFAULT_TIMEOUT_MS = 45_000;

/** URL for a backend path, e.g. apiUrl('/auth/login') -> '/api/auth/login'. */
export const apiUrl = (path: string) => `${API_PREFIX}${path}`;

let unauthorizedHandler: (() => void) | null = null;

/** Clear session UI when the API rejects the cookie (e.g. after a database rebuild). */
export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

/** fetch() for backend calls: same-origin session cookie plus the client header the API requires on cookie-authenticated writes. */
export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('X-CT-Client', 'web');
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const timeoutMs = init.signal ? undefined : DEFAULT_TIMEOUT_MS;
  const signal =
    init.signal ??
    (typeof AbortSignal !== 'undefined' && 'timeout' in AbortSignal
      ? AbortSignal.timeout(timeoutMs!)
      : undefined);
  return fetch(apiUrl(path), { ...init, headers, credentials: 'include', signal });
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let r: Response;
  try {
    r = await apiFetch(path, init);
  } catch (err) {
    if (err instanceof DOMException && err.name === 'TimeoutError') {
      throw new ApiError('Request timed out — is the API running on port 8000?', 504);
    }
    throw err;
  }
  if (!r.ok) {
    if (r.status === 401 && path !== '/auth/me' && !path.startsWith('/auth/login') && unauthorizedHandler) {
      unauthorizedHandler();
    }
    const body = await r.json().catch(() => ({ detail: r.statusText }));
    const detail = body.detail;
    throw new ApiError(
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((x: { msg: string }) => x.msg).join(', ')
          : r.statusText || `Request failed (${r.status})`,
      r.status,
    );
  }
  return r.json();
}

export const get = <T,>(p: string) => api<T>(p);
export const post = <T,>(p: string, b: unknown) => api<T>(p, { method: 'POST', body: JSON.stringify(b) });
export const patch = <T,>(p: string, b: unknown) => api<T>(p, { method: 'PATCH', body: JSON.stringify(b) });
export const put = <T,>(p: string, b: unknown) => api<T>(p, { method: 'PUT', body: JSON.stringify(b) });
export const del = <T,>(p: string) => api<T>(p, { method: 'DELETE' });
