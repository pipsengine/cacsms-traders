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
  const busy = useRef(false);

  const run = useCallback(
    async (silent: boolean) => {
      if (!enabled || busy.current) return;
      busy.current = true;
      if (silent) setRefreshing(true);
      else {
        setLoading(true);
        setError('');
      }
      try {
        const next = await loader();
        setData(next);
        setError('');
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!silent) setLoading(false);
        setRefreshing(false);
        busy.current = false;
      }
    },
    [enabled, ...deps],
  );

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
