import React from 'react';
import { Bell } from 'lucide-react';
import { ApiError, get } from '../lib/api';
import type { Page } from '../lib/routes';

const POLL_MS = 30_000;

type InboxItem = {
  id: string;
  event_type: string;
  label: string;
  symbol: string;
  timeframe: string | null;
  direction: string | null;
  status: string;
  detected_at: string;
  unread: boolean;
  qualified?: number | null;
  late?: boolean;
};
type Inbox = { unread: number; items: InboxItem[]; server_time: string };

const seenKey = (tenantId: string) => `cacsms.bell.seen.${tenantId}`;

function ago(iso: string, now: number): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86_400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86_400)} d ago`;
}

function statusText(status: string): string {
  if (status === 'SENT') return 'emailed';
  if (status === 'SUPPRESSED') return 'not emailed';
  return status.replaceAll('_', ' ').toLowerCase();
}

function headline(i: InboxItem): string {
  if (i.event_type === 'AI_OUTLOOK_PUBLISHED') {
    const n = i.qualified ?? 0;
    return `${i.label} · ${n} qualified ${n === 1 ? 'opportunity' : 'opportunities'}`;
  }
  return `${i.label} · ${i.symbol}${i.timeframe ? ` ${i.timeframe}` : ''}`;
}

export function NotificationBell({ tenantId, navigate }: { tenantId: string; navigate: (page: Page, tab?: string) => void }) {
  const [inbox, setInbox] = React.useState<Inbox | null>(null);
  const [denied, setDenied] = React.useState(false);
  const [stale, setStale] = React.useState(false);
  const [open, setOpen] = React.useState(false);
  const [seen, setSeen] = React.useState<string | null>(() => (tenantId ? localStorage.getItem(seenKey(tenantId)) : null));
  const wrap = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    setSeen(tenantId ? localStorage.getItem(seenKey(tenantId)) : null);
    setInbox(null);
    setDenied(false);
  }, [tenantId]);

  const load = React.useCallback(async () => {
    if (!tenantId) return;
    const q = new URLSearchParams({ tenant_id: tenantId });
    if (seen) q.set('since', seen);
    try {
      setInbox(await get<Inbox>(`/notifications/inbox?${q}`));
      setDenied(false);
      setStale(false);
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) setDenied(true);
      else setStale(true);
    }
  }, [tenantId, seen]);

  React.useEffect(() => {
    void load();
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void load();
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
  }, [load]);

  React.useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (tenantId && e.key === seenKey(tenantId)) setSeen(e.newValue);
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [tenantId]);

  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const markRead = () => {
    const newest = inbox?.items[0]?.detected_at;
    if (!tenantId || !newest || (seen && seen >= newest)) return;
    localStorage.setItem(seenKey(tenantId), newest);
    setSeen(newest);
    setInbox((cur) => cur && { ...cur, unread: 0, items: cur.items.map((i) => ({ ...i, unread: false })) });
  };

  const toggle = () => {
    if (!open) void load();
    setOpen(!open);
  };

  const unread = denied ? 0 : inbox?.unread ?? 0;
  const now = Date.now();
  const label = unread ? `Notifications, ${unread} unread` : 'Notifications';

  return (
    <div className="bell-wrap" ref={wrap}>
      <button type="button" className="top-bell" aria-label={label} aria-expanded={open} title={label} onClick={toggle}>
        <Bell size={18} />
        {unread > 0 && <i>{unread > 9 ? '9+' : unread}</i>}
      </button>
      {open && (
        <div className="bell-pop" role="dialog" aria-label="Recent alerts">
          <div className="bell-head">
            <b>Alerts</b>
            {unread > 0 && (
              <button type="button" className="bell-link" onClick={markRead}>
                Mark all read
              </button>
            )}
          </div>
          {denied ? (
            <p className="bell-empty">You don't have access to alert history for this tenant.</p>
          ) : !inbox ? (
            <p className="bell-empty">{stale ? 'Alerts could not be loaded. Retrying…' : 'Loading…'}</p>
          ) : inbox.items.length === 0 ? (
            <p className="bell-empty">No alerts yet. Channel events and the daily AI analysis will appear here.</p>
          ) : (
            <ul className="bell-list">
              {inbox.items.map((i) => (
                <li key={i.id} className={i.unread ? 'is-unread' : ''}>
                  <i className={`bell-dot is-${(i.direction ?? 'neutral').toLowerCase()}`} aria-hidden />
                  <div>
                    <b>{headline(i)}</b>
                    <span>
                      {ago(i.detected_at, now)} · {statusText(i.status)}
                      {i.late && <em> · late</em>}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {stale && inbox && <p className="bell-stale">Couldn't refresh — showing the last update.</p>}
          <button
            type="button"
            className="bell-all"
            onClick={() => {
              markRead();
              setOpen(false);
              navigate('system-control', 'alert-history');
            }}
          >
            View alert history
          </button>
        </div>
      )}
    </div>
  );
}
