import { post } from './api';

export async function connectLocalMT5(tenantId: string): Promise<string> {
  try {
    const health = await fetch('http://127.0.0.1:8917/health', { signal: AbortSignal.timeout(10000) });
    if (!health.ok || !(await health.json()).bridge_supported) throw new Error('Update or restart the Windows MT5 gateway to enable connections.');
  } catch (err) {
    throw err instanceof TypeError ? new Error('Cannot reach the Windows MT5 gateway. Allow local-network access in Chrome and ensure the gateway is running.') : err;
  }
  const pairing = await post<{token: string}>(`/tenants/${encodeURIComponent(tenantId)}/mt5-bridge/credential`, {});
  const origin = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://127.0.0.1:8000' : window.location.origin;
  try {
    const response = await fetch('http://127.0.0.1:8917/bridge/connect', {
      method: 'POST', headers: { 'X-Cacsms-MT5': 'connect', 'Content-Type': 'application/json' },
      body: JSON.stringify({ tenant_id: tenantId, token: pairing.token, origin }), signal: AbortSignal.timeout(60000),
    });
    const result = await response.json();
    if (!response.ok || !result.ok || !result.connected) throw new Error(result.error || 'MT5 bridge did not connect');
    return 'MT5 connected. The hosted platform accepted its heartbeat; trading remains disabled.';
  } catch (err) {
    await post(`/tenants/${encodeURIComponent(tenantId)}/mt5-bridge/disconnect`, {}).catch(() => undefined);
    throw err instanceof TypeError ? new Error('Cannot reach the Windows MT5 gateway. Allow local-network access in Chrome and ensure the gateway is running.') : err;
  }
}

export async function openLocalMT5(): Promise<string> {
  const response = await fetch('http://127.0.0.1:8917/terminal/open', {
    method: 'POST', headers: { 'X-Cacsms-MT5': 'open' }, signal: AbortSignal.timeout(15000),
  });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || 'MT5 could not open');
  return result.launched ? 'MT5 startup requested on this PC.' : result.restored
    ? 'MT5 window restored on this PC.' : 'MT5 is running on this PC; check its taskbar window.';
}
