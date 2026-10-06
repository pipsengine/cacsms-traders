export async function openLocalMT5(): Promise<string> {
  const response = await fetch('http://127.0.0.1:8917/terminal/open', {
    method: 'POST', headers: { 'X-Cacsms-MT5': 'open' }, signal: AbortSignal.timeout(15000),
  });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || 'MT5 could not open');
  return result.launched ? 'MT5 startup requested on this PC.' : result.restored
    ? 'MT5 window restored on this PC.' : 'MT5 is running on this PC; check its taskbar window.';
}
