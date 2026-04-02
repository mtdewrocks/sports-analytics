import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register as registerApi } from '../api/auth';
import { useAuth } from '../context/AuthContext';

const US_STATES = [
  'Alabama','Alaska','Arizona','Arkansas','California','Colorado','Connecticut',
  'Delaware','Florida','Georgia','Hawaii','Idaho','Illinois','Indiana','Iowa',
  'Kansas','Kentucky','Louisiana','Maine','Maryland','Massachusetts','Michigan',
  'Minnesota','Mississippi','Missouri','Montana','Nebraska','Nevada','New Hampshire',
  'New Jersey','New Mexico','New York','North Carolina','North Dakota','Ohio',
  'Oklahoma','Oregon','Pennsylvania','Rhode Island','South Carolina','South Dakota',
  'Tennessee','Texas','Utah','Vermont','Virginia','Washington','West Virginia',
  'Wisconsin','Wyoming','Washington D.C.',
];

const SPORTS = ['NBA', 'NFL', 'MLB', 'All Sports'];

const field: React.CSSProperties = {
  width: '100%', padding: '10px 14px', border: '1px solid #d1d5db',
  borderRadius: 6, fontSize: 14, outline: 'none', boxSizing: 'border-box',
  fontFamily: 'inherit',
};

const label: React.CSSProperties = {
  display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6,
};

export default function Register() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [state, setState] = useState('');
  const [favSport, setFavSport] = useState('');
  const [favTeams, setFavTeams] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!firstName.trim() || !lastName.trim()) {
      setError('First and last name are required');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }
    setLoading(true);
    try {
      const res = await registerApi(
        email, password,
        firstName.trim(), lastName.trim(),
        state || undefined,
        favSport || undefined,
        favTeams.trim() || undefined,
      );
      const { access_token, user } = res.data;
      login(access_token, user);
      navigate('/nba/game-log');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ background: 'white', borderRadius: 12, padding: '48px 40px', width: '100%', maxWidth: 460, boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🏆</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: '#1a1a2e', marginBottom: 4 }}>Create Account</h1>
          <p style={{ color: '#888', fontSize: 14 }}>Sports Analytics Pro</p>
        </div>

        {/* Trial banner */}
        <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#15803d', padding: '10px 14px', borderRadius: 6, marginBottom: 20, fontSize: 13, textAlign: 'center' }}>
          30 days free, then $5.99/month
        </div>

        {/* Error */}
        {error && (
          <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: '10px 14px', borderRadius: 6, marginBottom: 20, fontSize: 14 }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>

          {/* ── Account Info ── */}
          <div style={{ borderBottom: '1px solid #e5e7eb', paddingBottom: 20, marginBottom: 20 }}>
            <p style={{ fontSize: 12, fontWeight: 700, color: '#9ca3af', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 14 }}>Account Info</p>

            <div style={{ marginBottom: 14 }}>
              <label style={label}>Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="you@example.com" style={field} />
            </div>

            <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
              <div style={{ flex: 1 }}>
                <label style={label}>Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="Min. 6 characters" style={field} />
              </div>
              <div style={{ flex: 1 }}>
                <label style={label}>Confirm Password</label>
                <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required placeholder="••••••••" style={field} />
              </div>
            </div>
          </div>

          {/* ── Personal Info ── */}
          <div style={{ borderBottom: '1px solid #e5e7eb', paddingBottom: 20, marginBottom: 20 }}>
            <p style={{ fontSize: 12, fontWeight: 700, color: '#9ca3af', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 14 }}>Personal Info</p>

            <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
              <div style={{ flex: 1 }}>
                <label style={label}>First Name <span style={{ color: '#e94560' }}>*</span></label>
                <input type="text" value={firstName} onChange={(e) => setFirstName(e.target.value)} required placeholder="John" style={field} />
              </div>
              <div style={{ flex: 1 }}>
                <label style={label}>Last Name <span style={{ color: '#e94560' }}>*</span></label>
                <input type="text" value={lastName} onChange={(e) => setLastName(e.target.value)} required placeholder="Smith" style={field} />
              </div>
            </div>

            <div style={{ marginBottom: 0 }}>
              <label style={label}>State <span style={{ color: '#9ca3af', fontWeight: 400 }}>(optional)</span></label>
              <select value={state} onChange={(e) => setState(e.target.value)} style={{ ...field, color: state ? '#111827' : '#9ca3af', background: 'white' }}>
                <option value="">Select your state...</option>
                {US_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>

          {/* ── Sports Preferences ── */}
          <div style={{ marginBottom: 24 }}>
            <p style={{ fontSize: 12, fontWeight: 700, color: '#9ca3af', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 14 }}>Sports Preferences <span style={{ fontSize: 11, fontWeight: 400 }}>(optional)</span></p>

            <div style={{ marginBottom: 14 }}>
              <label style={label}>Favorite Sport</label>
              <select value={favSport} onChange={(e) => setFavSport(e.target.value)} style={{ ...field, color: favSport ? '#111827' : '#9ca3af', background: 'white' }}>
                <option value="">Select a sport...</option>
                {SPORTS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            <div>
              <label style={label}>Favorite Teams</label>
              <input
                type="text"
                value={favTeams}
                onChange={(e) => setFavTeams(e.target.value)}
                placeholder="e.g. Lakers, Chiefs, Cubs"
                style={field}
              />
              <p style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>Separate multiple teams with commas</p>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{ width: '100%', background: loading ? '#9ca3af' : '#e94560', color: 'white', border: 'none', padding: '12px', fontSize: 15, fontWeight: 700, borderRadius: 6, cursor: loading ? 'not-allowed' : 'pointer', transition: 'background 0.2s' }}
          >
            {loading ? 'Creating account...' : 'Create Account'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 20, fontSize: 14, color: '#666' }}>
          Already have an account?{' '}
          <Link to="/login" style={{ color: '#e94560', fontWeight: 600 }}>Login</Link>
        </div>
      </div>
    </div>
  );
}
