import React from 'react';
import { ShieldCheck } from 'lucide-react';
import { post } from '../lib/api';

type LoginResponse = {
  user: { display_name: string; username: string };
};

export function Login({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post<LoginResponse>('/auth/login', { username, password });
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <div className="mark">C</div>
          <div>
            <b>Cacsms-Traders</b>
            <span>Platform Foundation</span>
          </div>
        </div>
        <p className="login-lead">Sign in to administer tenants, accounts and system controls.</p>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <div className="login-error">{error}</div>}
        <button className="primary full" type="submit" disabled={busy}>
          <ShieldCheck />
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
