const BASE = import.meta.env.VITE_API_BASE ?? '';
export const API_PREFIX = '/api';

/** Absolute URL for a backend path, e.g. apiUrl('/auth/login') -> '/api/auth/login'. */
export const apiUrl = (path: string) => `${BASE}${API_PREFIX}${path}`;

/** fetch() for backend calls: same-origin session cookie plus the client header the API requires on cookie-authenticated writes. */
export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('X-CT-Client', 'web');
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  return fetch(apiUrl(path), { ...init, headers, credentials: 'include' });
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await apiFetch(path, init);
  if (!r.ok) {
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
