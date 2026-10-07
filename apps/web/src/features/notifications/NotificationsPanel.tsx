import React from 'react';
import { SubTabs } from '../../components/SubTabs';
import { TabPanel } from '../../components/PageTabs';
import { get } from '../../lib/api';
import { AlertHistory } from './AlertHistory';
import { EmailAlerts } from './EmailAlerts';
import type { AlertType } from './types';

const SUB_TABS = [
  { id: 'email', label: 'Email Alerts' },
  { id: 'history', label: 'Alert History' },
];

const FALLBACK_TYPES: { key: AlertType; label: string }[] = [
  { key: 'CHANNEL_BREAK', label: 'Channel Break' },
  { key: 'CHANNEL_TOUCH', label: 'Channel Touch' },
  { key: 'BREAK_RETEST_CONTINUATION', label: 'Break & Retest / Trend Continuation' },
  { key: 'TIT_DETECTED', label: 'TiT Detected' },
];
const FALLBACK_STATUSES = ['DETECTED', 'VALIDATED', 'QUEUED', 'SENDING', 'SENT', 'FAILED', 'RETRY_PENDING', 'SUPPRESSED', 'DUPLICATE'];

export function NotificationsPanel({ tenantId }: { tenantId: string }) {
  const [sub, setSub] = React.useState('email');
  const [meta, setMeta] = React.useState({ types: FALLBACK_TYPES, statuses: FALLBACK_STATUSES });

  React.useEffect(() => {
    if (!tenantId || sub !== 'history') return;
    get<{ alert_types: typeof FALLBACK_TYPES; statuses: string[] }>(`/notifications/email?tenant_id=${encodeURIComponent(tenantId)}`)
      .then((o) => setMeta({ types: o.alert_types, statuses: o.statuses }))
      .catch(() => undefined);
  }, [tenantId, sub]);

  return (
    <div className="nt-panel">
      <SubTabs tabs={SUB_TABS} active={sub} onChange={setSub} />
      <TabPanel active={sub} id="email">
        <EmailAlerts tenantId={tenantId} />
      </TabPanel>
      <TabPanel active={sub} id="history">
        <AlertHistory tenantId={tenantId} types={meta.types} statuses={meta.statuses} />
      </TabPanel>
    </div>
  );
}
