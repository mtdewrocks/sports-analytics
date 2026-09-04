import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getBillingStatus, createCheckout, createPortal } from '../api/billing';
import LoadingSpinner from '../components/LoadingSpinner';
import { theme } from '../theme';

interface BillingStatus {
  has_access: boolean;
  trial_active: boolean;
  trial_ends_at: string | null;
  days_remaining: number | null;
  subscription_active: boolean;
  subscription_status: string | null;
}

export default function Billing() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState<'monthly' | 'yearly'>('monthly');
  const [searchParams] = useSearchParams();

  const success = searchParams.get('success');
  const canceled = searchParams.get('canceled');

  useEffect(() => {
    getBillingStatus()
      .then((res) => setStatus(res.data))
      .catch(() => setError('Failed to load billing information'))
      .finally(() => setLoading(false));
  }, []);

  const handleCheckout = async () => {
    setActionLoading(true);
    try {
      const res = await createCheckout(plan);
      window.location.href = res.data.checkout_url;
    } catch {
      setError('Failed to start checkout. Please try again.');
      setActionLoading(false);
    }
  };

  const handlePortal = async () => {
    setActionLoading(true);
    try {
      const res = await createPortal();
      window.location.href = res.data.portal_url;
    } catch {
      setError('Failed to open billing portal.');
      setActionLoading(false);
    }
  };

  const card: React.CSSProperties = {
    background: theme.bgCard,
    borderRadius: 12,
    padding: '32px',
    marginBottom: 24,
    boxShadow: '0 2px 12px rgba(0,0,0,0.4)',
  };

  return (
    <div style={{ maxWidth: 640, margin: '40px auto', padding: '0 24px', background: theme.bgPage, minHeight: '100vh' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, color: theme.textPrimary, marginBottom: 24 }}>Billing & Subscription</h1>

      {success && (
        <div style={{ background: 'rgba(29,158,117,0.12)', border: `1px solid ${theme.accent}`, color: theme.accent, padding: '12px 16px', borderRadius: 8, marginBottom: 20, fontWeight: 600 }}>
          Subscription activated successfully! Welcome aboard.
        </div>
      )}
      {canceled && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, color: theme.dataRed, padding: '12px 16px', borderRadius: 8, marginBottom: 20 }}>
          Checkout was canceled. No charges were made.
        </div>
      )}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, color: theme.dataRed, padding: '12px 16px', borderRadius: 8, marginBottom: 20 }}>
          {error}
        </div>
      )}

      {loading ? (
        <LoadingSpinner />
      ) : status ? (
        <>
          {/* Status Card */}
          <div style={card}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 20, color: theme.textPrimary }}>Account Status</h2>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 120, background: theme.bgCardHover, borderRadius: 8, padding: '16px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: status.has_access ? theme.dataBlue : theme.dataRed }}>
                  {status.has_access ? 'Active' : 'Inactive'}
                </div>
                <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 4 }}>Access Status</div>
              </div>
              {status.trial_active && status.days_remaining !== null && (
                <div style={{ flex: 1, minWidth: 120, background: theme.bgCardHover, borderRadius: 8, padding: '16px 20px', textAlign: 'center' }}>
                  <div style={{ fontSize: 28, fontWeight: 800, color: theme.dataBlue }}>{status.days_remaining}</div>
                  <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 4 }}>Trial Days Left</div>
                </div>
              )}
              {status.trial_ends_at && (
                <div style={{ flex: 1, minWidth: 160, background: theme.bgCardHover, borderRadius: 8, padding: '16px 20px', textAlign: 'center' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary }}>
                    {new Date(status.trial_ends_at).toLocaleDateString()}
                  </div>
                  <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 4 }}>Trial Ends</div>
                </div>
              )}
            </div>

            {status.subscription_active && (
              <div style={{ marginTop: 16, padding: '10px 14px', background: 'rgba(29,158,117,0.12)', borderRadius: 6, color: theme.accent, fontSize: 14 }}>
                Subscription status: <strong>{status.subscription_status}</strong>
              </div>
            )}
          </div>

          {/* Action Card */}
          <div style={card}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, color: theme.textPrimary }}>
              {status.subscription_active ? 'Manage Subscription' : 'Upgrade to Pro'}
            </h2>
            {!status.subscription_active && (
              <>
                <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                  <button
                    onClick={() => setPlan('monthly')}
                    style={{
                      flex: 1, padding: '10px 0', borderRadius: 6, fontSize: 14, fontWeight: 700, cursor: 'pointer',
                      border: plan === 'monthly' ? `2px solid ${theme.accent}` : `1px solid ${theme.border}`,
                      background: plan === 'monthly' ? theme.accent : theme.bgCardHover,
                      color: plan === 'monthly' ? 'white' : theme.textPrimary,
                    }}
                  >
                    Monthly — $9.99/mo
                  </button>
                  <button
                    onClick={() => setPlan('yearly')}
                    style={{
                      flex: 1, padding: '10px 0', borderRadius: 6, fontSize: 14, fontWeight: 700, cursor: 'pointer',
                      border: plan === 'yearly' ? `2px solid ${theme.accent}` : `1px solid ${theme.border}`,
                      background: plan === 'yearly' ? theme.accent : theme.bgCardHover,
                      color: plan === 'yearly' ? 'white' : theme.textPrimary,
                    }}
                  >
                    Annual — $99.99/yr
                  </button>
                </div>
                <p style={{ color: theme.textSecondary, fontSize: 14, marginBottom: 20 }}>
                  Subscribe for full access at{' '}
                  <strong>{plan === 'monthly' ? '$9.99/month' : '$99.99/year'}</strong>. Cancel anytime.
                </p>
              </>
            )}
            {status.subscription_active ? (
              <button
                onClick={handlePortal}
                disabled={actionLoading}
                style={{ background: theme.accent, color: 'white', border: 'none', padding: '12px 28px', fontSize: 15, fontWeight: 700, borderRadius: 6, cursor: actionLoading ? 'not-allowed' : 'pointer' }}
              >
                {actionLoading ? 'Loading...' : 'Manage Subscription'}
              </button>
            ) : (
              <button
                onClick={handleCheckout}
                disabled={actionLoading}
                style={{ background: theme.accent, color: 'white', border: 'none', padding: '12px 28px', fontSize: 15, fontWeight: 700, borderRadius: 6, cursor: actionLoading ? 'not-allowed' : 'pointer' }}
              >
                {actionLoading ? 'Loading...' : `Start Subscription — ${plan === 'monthly' ? '$9.99/month' : '$99.99/year'}`}
              </button>
            )}
          </div>

          {/* Included Features */}
          <div style={card}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, color: theme.textPrimary }}>What's Included</h2>
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {[
                'Full NBA game log analysis with filters',
                'In/Out player correlation tools',
                'NFL matchup breakdowns',
                'MLB pitcher/hitter matchups',
                'Live prop odds from top sportsbooks',
                'Daily hot hitter trends',
                'Back-to-back and 3-in-4 filters',
                'Export-ready tables and charts',
              ].map((f) => (
                <li key={f} style={{ padding: '10px 0', borderBottom: `1px solid ${theme.border}`, display: 'flex', gap: 10, alignItems: 'center' }}>
                  <span style={{ color: theme.accent, fontWeight: 700 }}>✓</span>
                  <span style={{ color: theme.textPrimary, fontSize: 14 }}>{f}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </div>
  );
}
