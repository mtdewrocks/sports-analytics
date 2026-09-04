import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { login as loginApi } from '../api/auth';
import { useAuth } from '../context/AuthContext';
import { theme } from '../theme';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await loginApi(email, password);
      const { access_token, user } = res.data;
      login(access_token, user);
      const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname;
      navigate(from || '/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: `linear-gradient(135deg, ${theme.bgPage} 0%, ${theme.bgCardHover} 100%)`, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ background: theme.bgCard, borderRadius: 12, padding: '48px 40px', width: '100%', maxWidth: 400, boxShadow: '0 20px 60px rgba(0,0,0,0.5)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🏆</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: theme.textPrimary, marginBottom: 4 }}>Welcome Back</h1>
          <p style={{ color: theme.textSecondary, fontSize: 14 }}>Sign in to Sports Analytics Pro</p>
        </div>

        {error && (
          <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, color: theme.dataRed, padding: '10px 14px', borderRadius: 6, marginBottom: 20, fontSize: 14 }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.textSecondary, marginBottom: 6 }}>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
              style={{ width: '100%', padding: '10px 14px', border: `1px solid ${theme.border}`, borderRadius: 6, fontSize: 14, outline: 'none', boxSizing: 'border-box', background: theme.bgPage, color: theme.textPrimary }}
            />
          </div>
          <div style={{ marginBottom: 24 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.textSecondary, marginBottom: 6 }}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="••••••••"
              style={{ width: '100%', padding: '10px 14px', border: `1px solid ${theme.border}`, borderRadius: 6, fontSize: 14, outline: 'none', boxSizing: 'border-box', background: theme.bgPage, color: theme.textPrimary }}
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            style={{ width: '100%', background: loading ? theme.bgCardHover : theme.accent, color: 'white', border: 'none', padding: '12px', fontSize: 15, fontWeight: 700, borderRadius: 6, cursor: loading ? 'not-allowed' : 'pointer', transition: 'background 0.2s' }}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 20, fontSize: 14, color: theme.textSecondary }}>
          Don't have an account?{' '}
          <Link to="/register" style={{ color: theme.accent, fontWeight: 600 }}>Register</Link>
        </div>
      </div>
    </div>
  );
}
