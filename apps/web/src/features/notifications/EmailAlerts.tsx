import React from 'react';
import { MailCheck, RefreshCcw, Save, Send } from 'lucide-react';
import { Card, Notice, Status } from '../../components/Ui';
import { del, get, patch, post, put } from '../../lib/api';
import { RecipientsCard, type RecipientDraft } from './RecipientsCard';
import { SmtpTransportCard, type SmtpSave } from './SmtpTransportCard';
import { fmtTime } from './format';
import type { AlertSettings, AlertType, EmailOverview, TestResult } from './types';

const TYPE_HINTS: Record<AlertType, string> = {
  CHANNEL_BREAK: 'Confirmed closes beyond a channel boundary',
  CHANNEL_TOUCH: 'Price reaches a boundary zone; re-arms after leaving it',
  BREAK_RETEST_CONTINUATION: 'Break, retest and held continuation',
  TIT_DETECTED: 'Trend-in-Trend setup across the L1–L4 hierarchy',
};

const settingsBody = (s: AlertSettings) => ({
  email_enabled: s.email_enabled,
  alert_types: s.alert_types,
  timeframes: s.timeframes,
  symbols: s.symbols,
  xauusd_enabled: s.xauusd_enabled,
  touch_rearm_bars: s.touch_rearm_bars,
  cooldown_minutes: s.cooldown_minutes,
  max_event_age_bars: s.max_event_age_bars,
  max_attempts: s.max_attempts,
});

function NumberField({ label, hint, value, min, max, disabled, onChange }: {
  label: string; hint: string; value: number; min: number; max: number; disabled: boolean; onChange: (v: number) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <input type="number" min={min} max={max} value={value} disabled={disabled}
        onChange={(e) => onChange(Math.min(max, Math.max(min, Number(e.target.value) || min)))} />
      <small>{hint}</small>
    </label>
  );
}

export function EmailAlerts({ tenantId }: { tenantId: string }) {
  const [data, setData] = React.useState<EmailOverview | null>(null);
  const [draft, setDraft] = React.useState<AlertSettings | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [success, setSuccess] = React.useState('');
  const [testTo, setTestTo] = React.useState('');
  const [lastTest, setLastTest] = React.useState<TestResult | null>(null);
  const q = `tenant_id=${encodeURIComponent(tenantId)}`;

  const apply = React.useCallback((o: EmailOverview) => {
    setData(o);
    setDraft(o.settings);
  }, []);

  const load = React.useCallback(async () => {
    if (!tenantId) return;
    try {
      apply(await get<EmailOverview>(`/notifications/email?${q}`));
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load notification settings.');
    }
  }, [tenantId, q, apply]);

  React.useEffect(() => { void load(); }, [load]);

  async function run(action: () => Promise<EmailOverview>, message: string): Promise<boolean> {
    setBusy(true);
    setError('');
    setSuccess('');
    try {
      apply(await action());
      setSuccess(message);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The change could not be saved.');
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function sendTest() {
    setBusy(true);
    setError('');
    setSuccess('');
    try {
      const to = testTo.split(/[,;\s]+/).filter(Boolean);
      const r = await post<{ result: TestResult; overview: EmailOverview }>(`/notifications/email/test?${q}`, { to });
      apply(r.overview);
      setLastTest(r.result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test email could not be sent.');
    } finally {
      setBusy(false);
    }
  }

  if (!data || !draft) {
    return (
      <Card className="nt-card">
        {error ? <Notice title="Email alerts" text={error} tone="warning" /> : <p className="muted">Loading notification settings…</p>}
      </Card>
    );
  }

  const canEdit = data.can_manage && !busy;
  const dirty = JSON.stringify(settingsBody(draft)) !== JSON.stringify(settingsBody(data.settings));
  const set = <K extends keyof AlertSettings>(k: K, v: AlertSettings[K]) => setDraft({ ...draft, [k]: v });
  const toggleIn = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const fxSymbols = data.symbols.filter((s) => s !== 'XAUUSD');
  const test = lastTest ?? data.health.last_test ?? null;
  const enabledRecipients = data.recipients.filter((r) => r.enabled).length;

  return (
    <div className="nt-wrap">
      {error && <Notice title="Email alerts" text={error} tone="warning" />}
      {success && <Notice title="Email alerts" text={success} />}

      <div className="nt-grid">
        <Card className="nt-card">
          <div className="card-title">
            <div>
              <h2>Delivery health</h2>
              <p>Alerts are queued by the Alert Engine and sent by a background worker. Retries after {data.retry_minutes.join(', ')} minutes, then failed.</p>
            </div>
            <button type="button" className="sc-btnSecondary sc-btnSmall" disabled={busy} onClick={() => void load()}><RefreshCcw /> Refresh</button>
          </div>
          <div className="nt-kpis">
            <div><span>SMTP</span><Status value={data.smtp.ready ? 'READY' : data.smtp.enabled ? 'NOT_READY' : 'DISABLED'} /></div>
            <div><span>Notifications</span><Status value={data.settings.email_enabled ? 'ACTIVE' : 'PAUSED'} /></div>
            <div><span>Last successful alert</span><b>{fmtTime(data.stats.last_sent_at)}</b></div>
            <div><span>Failed (7 days / total)</span><b className={data.stats.failed_recent ? 'nt-bad' : ''}>{data.stats.failed_recent} / {data.stats.failed_total}</b></div>
            <div><span>Pending deliveries</span><b>{data.stats.pending}</b></div>
            <div><span>Sent (7 days)</span><b>{data.stats.sent_recent}</b></div>
            <div><span>Events (7 days)</span><b>{data.stats.events_recent}</b></div>
            <div><span>Suppressed (7 days)</span><b>{data.stats.suppressed_recent}</b></div>
          </div>
          {data.health.last_error && (
            <Notice title={`Last SMTP error${data.health.last_error_kind ? ` (${data.health.last_error_kind})` : ''} · ${fmtTime(data.health.last_failure_at)}`}
              text={data.health.last_error} tone="warning" />
          )}

          <h3 className="nt-subhead">Send test email</h3>
          <p className="muted">Sends “[Cacsms Traders] Email Notification Test” through the configured SMTP server. No alert event is created.</p>
          <div className="nt-secret__row">
            <input value={testTo} disabled={!data.can_manage || busy} placeholder={enabledRecipients ? `Leave empty to send to ${enabledRecipients} enabled recipient(s)` : 'Enter an email address'}
              onChange={(e) => setTestTo(e.target.value)} />
            <button type="button" className="sc-btnPrimary sc-btnSmall" disabled={!data.can_manage || busy || (!testTo.trim() && !enabledRecipients)} onClick={() => void sendTest()}>
              <Send /> {busy ? 'Sending…' : 'Send test email'}
            </button>
          </div>
          {test && (
            <div className={`nt-test ${test.status === 'SENT' ? 'ok' : 'bad'}`}>
              <MailCheck />
              <div>
                <b>Test {test.status} · {fmtTime(test.at)}</b>
                <span>{test.status === 'SENT' ? `Delivered to the SMTP server${test.recipients?.length ? ` for ${test.recipients.join(', ')}` : ''}.` : test.error}</span>
              </div>
            </div>
          )}
        </Card>

        <Card className="nt-card">
          <div className="card-title">
            <div>
              <h2>Alert rules</h2>
              <p>Which confirmed, closed-candle events are emailed. All four alert types are enabled by default.</p>
            </div>
            {!data.can_manage && <Status value="READ_ONLY" />}
          </div>

          <label className="nt-switch nt-switch--master">
            <input type="checkbox" checked={draft.email_enabled} disabled={!canEdit} onChange={(e) => set('email_enabled', e.target.checked)} />
            <span>Email notifications enabled</span>
          </label>

          <div className="nt-types">
            {data.alert_types.map((t) => (
              <label key={t.key} className={draft.alert_types[t.key] ? 'nt-type on' : 'nt-type'}>
                <input type="checkbox" checked={draft.alert_types[t.key]} disabled={!canEdit}
                  onChange={(e) => set('alert_types', { ...draft.alert_types, [t.key]: e.target.checked })} />
                <div><b>{t.label}</b><span>{TYPE_HINTS[t.key]}</span></div>
              </label>
            ))}
          </div>

          <h3 className="nt-subhead">Timeframes</h3>
          <div className="nt-chips">
            {data.timeframes.map((tf) => (
              <button type="button" key={tf} className={draft.timeframes.includes(tf) ? 'nt-chip on' : 'nt-chip'} disabled={!canEdit}
                onClick={() => set('timeframes', data.timeframes.filter((x) => x === tf ? !draft.timeframes.includes(tf) : draft.timeframes.includes(x)))}>
                {tf}
              </button>
            ))}
          </div>

          <h3 className="nt-subhead">Symbols</h3>
          <div className="nt-chips">
            <button type="button" className={draft.symbols.length === 0 ? 'nt-chip on' : 'nt-chip'} disabled={!canEdit} onClick={() => set('symbols', [])}>All monitored pairs</button>
            {fxSymbols.map((s) => (
              <button type="button" key={s} className={draft.symbols.includes(s) ? 'nt-chip on' : 'nt-chip'} disabled={!canEdit}
                onClick={() => set('symbols', toggleIn(draft.symbols, s))}>
                {s}
              </button>
            ))}
          </div>
          <label className="nt-switch">
            <input type="checkbox" checked={draft.xauusd_enabled} disabled={!canEdit} onChange={(e) => set('xauusd_enabled', e.target.checked)} />
            <span>Include XAUUSD (Gold)</span>
          </label>

          <div className="nt-form nt-form--numbers">
            <NumberField label="Touch re-arm (closed bars)" hint="Bars outside the zone before another touch alert" value={draft.touch_rearm_bars} min={1} max={20}
              disabled={!canEdit} onChange={(v) => set('touch_rearm_bars', v)} />
            <NumberField label="Cooldown (minutes)" hint="Minimum gap between repeat alerts; 0 = re-arm only" value={draft.cooldown_minutes} min={0} max={1440}
              disabled={!canEdit} onChange={(v) => set('cooldown_minutes', v)} />
            <NumberField label="Max event age (bars)" hint="Older confirmations are not emailed" value={draft.max_event_age_bars} min={1} max={6}
              disabled={!canEdit} onChange={(v) => set('max_event_age_bars', v)} />
            <NumberField label="Delivery attempts" hint="Total attempts per recipient before FAILED" value={draft.max_attempts} min={1} max={6}
              disabled={!canEdit} onChange={(v) => set('max_attempts', v)} />
          </div>

          {data.can_manage && (
            <div className="nt-actions">
              <button type="button" className="sc-btnPrimary" disabled={busy || !dirty || draft.timeframes.length === 0}
                onClick={() => void run(() => put<EmailOverview>(`/notifications/email/settings?${q}`, settingsBody(draft)), 'Alert rules saved.')}>
                <Save /> Save alert rules
              </button>
              {dirty && <button type="button" className="sc-btnSecondary" disabled={busy} onClick={() => setDraft(data.settings)}>Discard changes</button>}
              {draft.timeframes.length === 0 && <span className="nt-bad">Select at least one timeframe.</span>}
              {data.settings.updated_at && <span className="muted">Last saved {fmtTime(data.settings.updated_at)}</span>}
            </div>
          )}
        </Card>
      </div>

      <div className="nt-grid">
        <RecipientsCard recipients={data.recipients} types={data.alert_types} canEdit={data.can_manage} busy={busy}
          onAdd={(d: RecipientDraft) => run(() => post<EmailOverview>(`/notifications/email/recipients?${q}`, { ...d, name: d.name || null }), `${d.email} added.`)}
          onUpdate={(id, d) => run(() => patch<EmailOverview>(`/notifications/email/recipients/${id}?${q}`, d), 'Recipient updated.')}
          onDelete={(id) => run(() => del<EmailOverview>(`/notifications/email/recipients/${id}?${q}`), 'Recipient removed.')} />
        <SmtpTransportCard smtp={data.smtp} canEdit={data.can_manage_smtp} busy={busy}
          onSave={(body: SmtpSave) => run(() => put<EmailOverview>(`/notifications/email/smtp?${q}`, body), body.clear_password ? 'Stored App Password removed.' : 'SMTP settings saved.')}
          onReset={() => run(() => post<EmailOverview>(`/notifications/email/smtp/reset?${q}`, {}), 'SMTP settings reset to the environment values.')} />
      </div>

      <p className="nt-safety">ANALYSIS ONLY — alert emails describe market intelligence events. They never place, modify or close orders, and never change risk authorization.</p>
    </div>
  );
}
