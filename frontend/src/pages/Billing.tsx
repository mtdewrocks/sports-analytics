import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getBillingStatus, createCheckout, createPortal } from '../api/billing';
import LoadingSpinner from '../components/LoadingSpinner';

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
      const res = await createCheckout();
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
    background: 'white',
    borderRadius: 12,
    padding: '32px',
    marginBottom: 24,
    boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
  };

  return (
    <div style={{ maxWidth: 640, margin: '40px auto', padding: '0 24px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, color: '#1a1a2e', marginBottom: 24 }}>Billing & Subscription</h1>

      {success && (
        <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#15803d', padding: '12px 16px', borderRadius: 8, marginBottom: 20, fontWeight: 600 }}>
          Subscription activated successfully! Welcome aboard.
        </div>
      )}
      {canceled && (
        <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: '12px 16px', borderRadius: 8, marginBottom: 20 }}>
          Checkout was canceled. No charges were made.
        </div>
      )}
      {error && (
        <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: '12px 16px', borderRadius: 8, marginBottom: 20 }}>
          {error}
        </div>
      )}

      {loading ? (
        <LoadingSpinner />
      ) : status ? (
        <>
          {/* Status Card */}
          <div style={card}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 20, color: '#1a1a2e' }}>Account Status</h2>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 120, background: '#f9fafb', borderRadius: 8, padding: '16px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: status.has_access ? '#2ecc71' : '#e74c3c' }}>
                  {status.has_access ? 'Active' : 'Inactive'}
                </div>
                <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>Access Status</div>
              </div>
              {status.trial_active && status.days_remaining !== null && (
                <div style={{ flex: 1, minWidth: 120, background: '#eff6ff', borderRadius: 8, padding: '16px 20px', textAlign: 'center' }}>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#2563eb' }}>{status.days_remaining}</div>
                  <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>Trial Days Left</div>
                </div>
              )}
              {status.trial_ends_at && (
                <div style={{ flex: 1, minWidth: 160, background: '#f9fafb', borderRadius: 8, padding: '16px 20px', textAlign: 'center' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#374151' }}>
                    {new Date(status.trial_ends_at).toLocaleDateString()}
                  </div>
                  <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>Trial Ends</div>
                </div>
              )}
            </div>

            {status.subscription_active && (
              <div style={{ marginTop: 16, padding: '10px 14px', background: '#f0fdf4', borderRadius: 6, color: '#15803d', fontSize: 14 }}>
                Subscription status: <strong>{status.subscription_status}</strong>
              </div>
            )}
          </div>

          {/* Action Card */}
          <div style={card}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, color: '#1a1a2e' }}>
              {status.subscription_active ? 'Manage Subscription' : 'Upgrade to Pro'}
            </h2>
            {!status.subscription_active && (
              <p style={{ color: '#666', fontSize: 14, marginBottom: 20 }}>
                Subscribe for full access at <strong>$5.99/month</strong>. Cancel anytime.
              </p>
            )}
            {status.subscription_active ? (
              <button
                onClick={handlePortal}
                disabled={actionLoading}
                style={{ background: '#1a1a2e', color: 'white', border: 'none', padding: '12px 28px', fontSize: 15, fontWeight: 700, borderRadius: 6, cursor: actionLoading ? 'not-allowed' : 'pointer' }}
              >
                {actionLoading ? 'Loading...' : 'Manage Subscription'}
              </button>
            ) : (
              <button
                onClick={handleCheckout}
                disabled={actionLoading}
                style={{ background: '#e94560', color: 'white', border: 'none', padding: '12px 28px', fontSize: 15, fontWeight: 700, borderRadius: 6, cursor: actionLoading ? 'not-allowed' : 'pointer' }}
              >
                {actionLoading ? 'Loading...' : 'Start Subscription — $5.99/month'}
              </button>
            )}
          </div>

          {/* Included Features */}
          <div style={card}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, color: '#1a1a2e' }}>What's Included</h2>
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
                <li key={f} style={{ padding: '10px 0', borderBottom: '1px solid #f3f4f6', display: 'flex', gap: 10, alignItems: 'center' }}>
                  <span style={{ color: '#2ecc71', fontWeight: 700 }}>✓</span>
                  <span style={{ color: '#374151', fontSize: 14 }}>{f}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </div>
  );
}
