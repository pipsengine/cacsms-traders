import React from 'react';
import { KeyRound, RotateCcw, Save } from 'lucide-react';
import { Card, Notice, Status } from '../../components/Ui';
import type { SmtpTransport } from './types';

type Form = {
  enabled: boolean;
  host: string;
  port: string;
  security: SmtpTransport['security'];
  username: string;
  from_email: string;
  from_name: string;
};

export type SmtpSave = Omit<Form, 'port'> & { port: number; password?: string; clear_password?: boolean };

const toForm = (s: SmtpTransport): Form => ({
  enabled: s.enabled,
  host: s.host,
  port: String(s.port || ''),
  security: s.security,
  username: s.username,
  from_email: s.from_email,
  from_name: s.from_name,
});

const SOURCE_LABEL: Record<string, string> = {
  database: 'Stored encrypted (set from this screen)',
  environment: 'SMTP_PASSWORD environment variable',
};

export function SmtpTransportCard({
  smtp,
  canEdit,
  busy,
  onSave,
  onReset,
}: {
  smtp: SmtpTransport;
  canEdit: boolean;
  busy: boolean;
  onSave: (body: SmtpSave) => Promise<boolean>;
  onReset: () => Promise<boolean>;
}) {
  const [form, setForm] = React.useState<Form>(() => toForm(smtp));
  const [password, setPassword] = React.useState('');
  const disabled = !canEdit || busy;

  React.useEffect(() => setForm(toForm(smtp)), [smtp]);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
  const dirty = JSON.stringify(form) !== JSON.stringify(toForm(smtp)) || password.trim().length > 0;
  const portValid = /^\d+$/.test(form.port) && Number(form.port) > 0 && Number(form.port) <= 65535;

  async function save(extra: Partial<SmtpSave> = {}) {
    const ok = await onSave({ ...form, port: Number(form.port), ...(password.trim() ? { password } : {}), ...extra });
    if (ok) setPassword('');
  }

  const pickSecurity = (security: Form['security']) =>
    setForm((f) => ({ ...f, security, port: security === 'ssl' && f.port === '587' ? '465' : security === 'starttls' && f.port === '465' ? '587' : f.port }));

  return (
    <Card className="nt-card">
      <div className="card-title">
        <div>
          <h2>SMTP transport</h2>
          <p>Outgoing mail server used by the email worker. Defaults come from the SMTP_* environment variables; saved values override them.</p>
        </div>
        <Status value={smtp.ready ? 'READY' : smtp.enabled ? 'NOT_READY' : 'DISABLED'} />
      </div>

      {!canEdit && <Notice title="Read only" text="Only a Super Administrator can change the SMTP transport." tone="warning" />}
      {smtp.problems.length > 0 && <Notice title="Not ready to send" text={smtp.problems.join(' · ')} tone="warning" />}
      {smtp.vault_error && <Notice title="Stored App Password" text={smtp.vault_error} tone="warning" />}

      <label className="nt-switch">
        <input type="checkbox" checked={form.enabled} disabled={disabled} onChange={(e) => set('enabled', e.target.checked)} />
        <span>SMTP sending enabled</span>
      </label>

      <div className="nt-form">
        <label>
          <span>SMTP host</span>
          <input value={form.host} disabled={disabled} onChange={(e) => set('host', e.target.value)} placeholder="smtp.gmail.com" />
        </label>
        <label>
          <span>Port</span>
          <input value={form.port} disabled={disabled} inputMode="numeric" onChange={(e) => set('port', e.target.value.replace(/\D/g, ''))} placeholder="587" />
        </label>
        <label>
          <span>Security</span>
          <select value={form.security} disabled={disabled} onChange={(e) => pickSecurity(e.target.value as Form['security'])}>
            <option value="starttls">STARTTLS (port 587)</option>
            <option value="ssl">SSL/TLS (port 465)</option>
            <option value="none">None (not recommended)</option>
          </select>
        </label>
        <label>
          <span>SMTP username</span>
          <input value={form.username} disabled={disabled} autoComplete="off" onChange={(e) => set('username', e.target.value)} placeholder="account@gmail.com" />
        </label>
        <label>
          <span>Sender email</span>
          <input value={form.from_email} disabled={disabled} type="email" onChange={(e) => set('from_email', e.target.value)} placeholder="account@gmail.com" />
        </label>
        <label>
          <span>Sender name</span>
          <input value={form.from_name} disabled={disabled} onChange={(e) => set('from_name', e.target.value)} placeholder="Cacsms Traders" />
        </label>
      </div>

      <div className="nt-secret">
        <div className="nt-secret__head">
          <KeyRound />
          <div>
            <b>Google App Password</b>
            <p>
              {smtp.password_configured
                ? `Configured — ${SOURCE_LABEL[smtp.password_source ?? ''] ?? 'server-side'}. The value is never displayed.`
                : 'Not configured. Use a 16-character Google App Password, never the Gmail account password.'}
            </p>
          </div>
        </div>
        <div className="nt-secret__row">
          <input
            type="password"
            value={password}
            disabled={disabled || !smtp.vault_available}
            autoComplete="new-password"
            placeholder={smtp.vault_available ? (smtp.password_configured ? 'Enter a new App Password to replace it' : 'xxxx xxxx xxxx xxxx') : 'Set SMTP_PASSWORD on the server'}
            onChange={(e) => setPassword(e.target.value)}
          />
          {smtp.password_source === 'database' && (
            <button type="button" className="sc-btnSecondary sc-btnSmall" disabled={disabled}
              onClick={() => window.confirm('Remove the stored App Password? The SMTP_PASSWORD environment variable will be used if set.') && void save({ clear_password: true })}>
              Remove stored password
            </button>
          )}
        </div>
        {!smtp.vault_available && (
          <p className="muted">Saving the App Password from this screen needs SMTP_ENCRYPTION_KEY on the server. Until then, set SMTP_PASSWORD in the server environment.</p>
        )}
      </div>

      <div className="nt-actions">
        <button type="button" className="sc-btnPrimary" disabled={disabled || !dirty || !portValid || !form.host.trim() || !form.from_email.trim()} onClick={() => void save()}>
          <Save /> {busy ? 'Saving…' : 'Save SMTP settings'}
        </button>
        {smtp.overrides.length > 0 && (
          <button type="button" className="sc-btnSecondary" disabled={disabled}
            onClick={() => window.confirm('Discard the saved SMTP values and use the SMTP_* environment variables again?') && void onReset()}>
            <RotateCcw /> Reset to environment
          </button>
        )}
        <span className="muted">{smtp.overrides.length ? `Overriding environment: ${smtp.overrides.join(', ')}` : 'Using environment values'}</span>
      </div>
    </Card>
  );
}
