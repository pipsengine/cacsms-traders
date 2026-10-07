import React from 'react';
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react';
import { Card, Empty } from '../../components/Ui';
import type { AlertType, Recipient } from './types';

export type RecipientDraft = { email: string; name: string; enabled: boolean; alert_types: AlertType[] };

const EMPTY: RecipientDraft = { email: '', name: '', enabled: true, alert_types: [] };
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function TypePicker({ types, value, disabled, onChange }: {
  types: { key: AlertType; label: string }[];
  value: AlertType[];
  disabled: boolean;
  onChange: (v: AlertType[]) => void;
}) {
  const all = value.length === 0;
  return (
    <div className="nt-chips">
      <button type="button" className={all ? 'nt-chip on' : 'nt-chip'} disabled={disabled} onClick={() => onChange([])}>All alert types</button>
      {types.map((t) => {
        const on = value.includes(t.key);
        return (
          <button type="button" key={t.key} className={on ? 'nt-chip on' : 'nt-chip'} disabled={disabled}
            onClick={() => onChange(on ? value.filter((k) => k !== t.key) : [...value, t.key])}>
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

function RecipientForm({ initial, types, busy, submitLabel, onSubmit, onCancel }: {
  initial: RecipientDraft;
  types: { key: AlertType; label: string }[];
  busy: boolean;
  submitLabel: string;
  onSubmit: (d: RecipientDraft) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = React.useState(initial);
  const valid = EMAIL.test(draft.email.trim());
  return (
    <div className="nt-recipientForm">
      <div className="nt-form nt-form--recipient">
        <label>
          <span>Email address</span>
          <input type="email" value={draft.email} disabled={busy} placeholder="desk@example.com" onChange={(e) => setDraft({ ...draft, email: e.target.value })} />
        </label>
        <label>
          <span>Name (optional)</span>
          <input value={draft.name} disabled={busy} placeholder="Trading desk" onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        </label>
        <label className="nt-switch nt-switch--inline">
          <input type="checkbox" checked={draft.enabled} disabled={busy} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />
          <span>Enabled</span>
        </label>
      </div>
      <TypePicker types={types} value={draft.alert_types} disabled={busy} onChange={(alert_types) => setDraft({ ...draft, alert_types })} />
      <div className="nt-actions">
        <button type="button" className="sc-btnPrimary sc-btnSmall" disabled={busy || !valid}
          onClick={async () => { if (await onSubmit({ ...draft, email: draft.email.trim() }) && !onCancel) setDraft(EMPTY); }}>
          {onCancel ? <Check /> : <Plus />} {submitLabel}
        </button>
        {onCancel && <button type="button" className="sc-btnSecondary sc-btnSmall" disabled={busy} onClick={onCancel}><X /> Cancel</button>}
      </div>
    </div>
  );
}

export function RecipientsCard({ recipients, types, canEdit, busy, onAdd, onUpdate, onDelete }: {
  recipients: Recipient[];
  types: { key: AlertType; label: string }[];
  canEdit: boolean;
  busy: boolean;
  onAdd: (d: RecipientDraft) => Promise<boolean>;
  onUpdate: (id: string, d: Partial<RecipientDraft>) => Promise<boolean>;
  onDelete: (id: string) => Promise<boolean>;
}) {
  const [editing, setEditing] = React.useState<string | null>(null);
  const label = (k: AlertType) => types.find((t) => t.key === k)?.label ?? k;
  const enabled = recipients.filter((r) => r.enabled).length;

  return (
    <Card className="nt-card">
      <div className="card-title">
        <div>
          <h2>Recipients</h2>
          <p>{recipients.length ? `${enabled} of ${recipients.length} enabled. Each recipient can receive all or selected alert types.` : 'Who receives market intelligence alerts for this tenant.'}</p>
        </div>
      </div>

      {recipients.length === 0 ? (
        <Empty title="No recipients yet" text="Add at least one email address — alerts are only queued for enabled recipients." />
      ) : (
        <div className="nt-recipients">
          {recipients.map((r) =>
            editing === r.id ? (
              <RecipientForm key={r.id} types={types} busy={busy} submitLabel="Save"
                initial={{ email: r.email, name: r.name ?? '', enabled: r.enabled, alert_types: r.alert_types }}
                onCancel={() => setEditing(null)}
                onSubmit={async (d) => { const ok = await onUpdate(r.id, d); if (ok) setEditing(null); return ok; }} />
            ) : (
              <div className={r.enabled ? 'nt-recipient' : 'nt-recipient is-off'} key={r.id}>
                <div className="nt-recipient__main">
                  <b>{r.name || r.email}</b>
                  {r.name && <span>{r.email}</span>}
                  <div className="nt-tags">
                    {(r.alert_types.length ? r.alert_types : null)?.map((k) => <i key={k}>{label(k)}</i>) ?? <i>All alert types</i>}
                  </div>
                </div>
                <label className="nt-switch nt-switch--inline" title={r.enabled ? 'Disable recipient' : 'Enable recipient'}>
                  <input type="checkbox" checked={r.enabled} disabled={!canEdit || busy} onChange={(e) => void onUpdate(r.id, { enabled: e.target.checked })} />
                  <span>{r.enabled ? 'Enabled' : 'Disabled'}</span>
                </label>
                <div className="nt-recipient__actions">
                  <button type="button" className="nt-iconBtn" aria-label={`Edit ${r.email}`} disabled={!canEdit || busy} onClick={() => setEditing(r.id)}><Pencil /></button>
                  <button type="button" className="nt-iconBtn danger" aria-label={`Remove ${r.email}`} disabled={!canEdit || busy}
                    onClick={() => window.confirm(`Remove ${r.email} from alert recipients?`) && void onDelete(r.id)}><Trash2 /></button>
                </div>
              </div>
            ),
          )}
        </div>
      )}

      {canEdit && (
        <>
          <h3 className="nt-subhead">Add recipient</h3>
          <RecipientForm initial={EMPTY} types={types} busy={busy} submitLabel="Add recipient" onSubmit={onAdd} />
        </>
      )}
    </Card>
  );
}
