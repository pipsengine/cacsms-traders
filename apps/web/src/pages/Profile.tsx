import React from 'react';
import { Save, UserRound } from 'lucide-react';
import { Card, PageHeader } from '../components/Ui';
import { patch, post } from '../lib/api';
import type { AuthUser } from '../types';

export function Profile({
  user,
  onChanged,
  onLogout,
}: {
  user: AuthUser | null;
  onChanged: () => void;
  onLogout: () => void;
}) {
  const [first, setFirst] = React.useState(user?.first_name ?? '');
  const [last, setLast] = React.useState(user?.last_name ?? '');
  const [email, setEmail] = React.useState(user?.email ?? '');
  const [timezone, setTimezone] = React.useState(user?.timezone ?? 'Africa/Lagos');
  const [currency, setCurrency] = React.useState(user?.preferred_currency ?? 'USD');
  const [currentPw, setCurrentPw] = React.useState('');
  const [newPw, setNewPw] = React.useState('');
  const [msg, setMsg] = React.useState<string | null>(null);

  React.useEffect(() => {
    setFirst(user?.first_name ?? '');
    setLast(user?.last_name ?? '');
    setEmail(user?.email ?? '');
    setTimezone(user?.timezone ?? 'Africa/Lagos');
    setCurrency(user?.preferred_currency ?? 'USD');
  }, [user]);

  async function saveProfile() {
    await patch('/auth/me', { first_name: first, last_name: last, timezone, preferred_currency: currency });
    setMsg('Profile updated.');
    onChanged();
  }

  async function changePassword() {
    await post('/auth/change-password', { current_password: currentPw, new_password: newPw });
    setCurrentPw('');
    setNewPw('');
    setMsg('Password changed.');
  }

  return (
    <>
      <PageHeader title="My Profile" subtitle="Identity, contact details, timezone and application preferences." />
      {msg && <p className="muted">{msg}</p>}
      <div className="two-col profile-grid">
        <Card>
          <div className="profile-hero">
            <div className="avatar-lg">
              <UserRound />
            </div>
            <div>
              <h2>{user?.display_name}</h2>
              <p>{user?.memberships?.[0]?.role_name ?? 'Member'}</p>
              <span>@{user?.username}</span>
            </div>
          </div>
          <div className="form-grid">
            <label>
              First Name
              <input value={first} onChange={(e) => setFirst(e.target.value)} />
            </label>
            <label>
              Last Name
              <input value={last} onChange={(e) => setLast(e.target.value)} />
            </label>
            <label>
              Email
              <input value={email} onChange={(e) => setEmail(e.target.value)} disabled />
            </label>
            <label>
              Timezone
              <input value={timezone} onChange={(e) => setTimezone(e.target.value)} />
            </label>
            <label>
              Preferred Currency
              <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
                <option>USD</option>
                <option>NGN</option>
              </select>
            </label>
          </div>
          <button type="button" className="primary" onClick={saveProfile}>
            <Save />
            Save Profile
          </button>
        </Card>
        <Card>
          <div className="card-title">
            <div>
              <h2>Security</h2>
              <p>Session and credential controls.</p>
            </div>
          </div>
          <label>
            Current Password
            <input type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
          </label>
          <label>
            New Password
            <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
          </label>
          <button type="button" className="secondary full" onClick={changePassword}>
            Change Password
          </button>
          <button type="button" className="danger-btn" onClick={onLogout}>
            Sign out everywhere (this session)
          </button>
        </Card>
      </div>
    </>
  );
}
