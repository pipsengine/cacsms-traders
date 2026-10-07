import { useCallback, useEffect, useRef, useState } from 'react';

export function useAsync<T>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
  options: { enabled?: boolean } = {},
) {
  const { enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(enabled);
  const refresh = useCallback(() => {
    if (!enabled) return;
    setLoading(true);
    setError('');
    loader()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [enabled, ...deps]);
  useEffect(() => {
    if (enabled) refresh();
    else setLoading(false);
  }, [enabled, refresh]);
  return { data, error, loading, refresh, setData };
}

/** Initial load + silent polling (skips overlapping requests). */
export function usePollingAsync<T>(
  loader: () => Promise<T>,
  deps: unknown[],
  options: { enabled?: boolean; intervalMs?: number } = {},
) {
  const { enabled = true, intervalMs = 1000 } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const busy = useRef<unknown>(null);
  const current = useRef<unknown>(null);

  const run = useCallback(
    async function self(silent: boolean) {
      if (!enabled || busy.current === self) return;
      busy.current = self;
      if (silent) setRefreshing(true);
      else {
        setLoading(true);
        setError('');
      }
      try {
        const next = await loader();
        if (current.current !== self) return;
        setData(next);
        setError('');
      } catch (e) {
        if (current.current !== self) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (busy.current === self) busy.current = null;
        if (current.current === self) {
          if (!silent) setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [enabled, ...deps],
  );
  current.current = run;

  const refresh = useCallback(() => void run(false), [run]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    void run(false);
  }, [enabled, run]);

  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => void run(true), intervalMs);
    return () => window.clearInterval(id);
  }, [enabled, intervalMs, run]);

  return { data, error, loading, refreshing, refresh, setData };
}
