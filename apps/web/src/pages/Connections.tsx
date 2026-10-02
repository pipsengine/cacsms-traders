import React from 'react';
import { PlugZap, Server } from 'lucide-react';
import { Card, Notice, PageHeader, Status } from '../components/Ui';
import { get } from '../lib/api';
import type { ConnectionsPayload } from '../types';

export function Connections({ tenantId }: { tenantId: string }) {
  const [data, setData] = React.useState<ConnectionsPayload | null>(null);

  React.useEffect(() => {
    if (!tenantId) return;
    get<ConnectionsPayload>(`/tenants/${tenantId}/connections`).then(setData).catch(() => setData(null));
  }, [tenantId]);

  const gw = data?.gateway;

  return (
    <>
      <PageHeader
        title="MT5 Connections"
        subtitle="Trading gateway foundation for local terminals now and remote adapters later."
      />
      <Notice
        title="Safe foundation state"
        text="The local MT5 gateway contract is installed, but terminal binding and order submission are not enabled."
      />
      <div className="two-col">
        <Card>
          <div className="card-title">
            <div>
              <h2>Local MT5 Gateway</h2>
              <p>Phase 1 adapter</p>
            </div>
            <Status value={gw?.status ?? 'DISCONNECTED'} />
          </div>
          <div className="detail-list">
            <div>
              <span>Adapter</span>
              <b>{gw?.adapter ?? 'LOCAL_MT5'}</b>
            </div>
            <div>
              <span>Terminal</span>
              <b>{data?.connections.length ? 'Configured records' : 'Not configured'}</b>
            </div>
            <div>
              <span>Heartbeat</span>
              <b>—</b>
            </div>
            <div>
              <span>Execution</span>
              <b>Disabled</b>
            </div>
          </div>
          <button type="button" className="secondary full" disabled>
            <PlugZap />
            Configure Connection
          </button>
        </Card>
        <Card>
          <div className="card-title">
            <div>
              <h2>Connection registry</h2>
              <p>{data?.connections.length ?? 0} record(s) for this tenant.</p>
            </div>
          </div>
          {(data?.connections ?? []).map((c) => (
            <div className="gateway-item" key={c.id}>
              <Server />
              <div>
                <b>
                  {c.account_name} · {c.environment}
                </b>
                <p>
                  {c.adapter_type} · {c.status}
                  {c.server_name ? ` · ${c.server_name}` : ''}
                </p>
              </div>
            </div>
          ))}
          {!data?.connections.length && (
            <p className="muted">Link accounts via the API; terminal handshake is reserved for a later phase.</p>
          )}
        </Card>
      </div>
    </>
  );
}
