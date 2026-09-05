import { useNavigate, Link } from 'react-router-dom';
import { theme } from '../theme';
import { useAuth } from '../context/AuthContext';

export default function Landing() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  return (
    <div style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', color: theme.textPrimary, background: theme.bgPage }}>
      {/* Hero */}
      <section style={{
        background: `linear-gradient(135deg, ${theme.bgPage} 0%, ${theme.bgCardHover} 50%, ${theme.bgCard} 100%)`,
        color: 'white',
        padding: '100px 24px 80px',
        textAlign: 'center',
      }}>
        <div style={{ maxWidth: 720, margin: '0 auto' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🏆</div>
          <h1 style={{ fontSize: 48, fontWeight: 800, marginBottom: 16, lineHeight: 1.1 }}>
            Sports Analytics Pro
          </h1>
          <p style={{ fontSize: 20, color: theme.textSecondary, marginBottom: 40, lineHeight: 1.6 }}>
            Data-driven insights for NBA, NFL &amp; MLB betting and fantasy sports
          </p>
          <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
            {isAuthenticated ? (
              <button
                onClick={() => navigate('/dashboard')}
                style={{
                  background: theme.accent,
                  color: 'white',
                  border: 'none',
                  padding: '14px 36px',
                  fontSize: 16,
                  fontWeight: 700,
                  borderRadius: 8,
                  cursor: 'pointer',
                  transition: 'background 0.2s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = theme.accentHover)}
                onMouseLeave={(e) => (e.currentTarget.style.background = theme.accent)}
              >
                Go to Dashboard
              </button>
            ) : (
              <>
                <button
                  onClick={() => navigate('/register')}
                  style={{
                    background: theme.accent,
                    color: 'white',
                    border: 'none',
                    padding: '14px 36px',
                    fontSize: 16,
                    fontWeight: 700,
                    borderRadius: 8,
                    cursor: 'pointer',
                    transition: 'background 0.2s',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = theme.accentHover)}
                  onMouseLeave={(e) => (e.currentTarget.style.background = theme.accent)}
                >
                  Get Started Free
                </button>
                <Link to="/login" style={{
                  background: 'transparent',
                  color: theme.textSecondary,
                  border: `1px solid ${theme.border}`,
                  padding: '14px 36px',
                  fontSize: 16,
                  borderRadius: 8,
                  display: 'inline-flex',
                  alignItems: 'center',
                }}>
                  Already have an account? Login
                </Link>
              </>
            )}
          </div>
        </div>
      </section>

      {/* Feature Cards */}
      <section style={{ padding: '80px 24px', background: theme.bgCardHover }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <h2 style={{ textAlign: 'center', fontSize: 32, fontWeight: 700, marginBottom: 48, color: theme.textPrimary }}>
            Comprehensive Sports Coverage
          </h2>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', justifyContent: 'center' }}>
            {[
              {
                icon: '🏀',
                title: 'NBA Analysis',
                desc: 'Game logs, player props, in/out analysis, teammate correlations, and advanced stat filters. Track performance against specific opponents and in back-to-back scenarios.',
              },
              {
                icon: '🏈',
                title: 'NFL Analysis',
                desc: 'Weekly game logs, team matchup breakdowns, and player performance data. Compare teams side-by-side with detailed stat rankings.',
              },
              {
                icon: '⚾',
                title: 'MLB Analysis',
                desc: 'Pitcher vs. hitter matchups, hot hitter trends, and prop odds from top sportsbooks. Percentile rankings and last-10 game performance logs.',
              },
            ].map((card) => (
              <div
                key={card.title}
                style={{
                  background: theme.bgCard,
                  borderRadius: 12,
                  padding: '36px 28px',
                  flex: '1 1 280px',
                  maxWidth: 320,
                  boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
                  textAlign: 'center',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.transform = 'translateY(-4px)';
                  (e.currentTarget as HTMLElement).style.boxShadow = '0 8px 30px rgba(0,0,0,0.45)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.transform = '';
                  (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 20px rgba(0,0,0,0.3)';
                }}
              >
                <div style={{ fontSize: 48, marginBottom: 16 }}>{card.icon}</div>
                <h3 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12, color: theme.textPrimary }}>{card.title}</h3>
                <p style={{ color: theme.textSecondary, lineHeight: 1.6, fontSize: 14 }}>{card.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section style={{ padding: '80px 24px', background: theme.bgPage, color: theme.textPrimary, textAlign: 'center' }}>
        <div style={{ maxWidth: 500, margin: '0 auto' }}>
          <h2 style={{ fontSize: 32, fontWeight: 700, marginBottom: 12 }}>Simple Pricing</h2>
          <p style={{ color: theme.textSecondary, marginBottom: 40 }}>No hidden fees. Cancel anytime.</p>
          <div style={{
            background: theme.bgCard,
            borderRadius: 16,
            padding: '48px 40px',
            border: `2px solid ${theme.accent}`,
            boxShadow: '0 8px 32px rgba(29,158,117,0.25)',
          }}>
            <div style={{ fontSize: 18, color: theme.accent, fontWeight: 700, marginBottom: 8 }}>All-Access Pass</div>
            <div style={{ fontSize: 52, fontWeight: 800, marginBottom: 4 }}>
              $9.99<span style={{ fontSize: 20, fontWeight: 400, color: theme.textSecondary }}>/month</span>
            </div>
            <div style={{ fontSize: 15, color: theme.textSecondary, marginBottom: 20 }}>
              or $99.99/year
            </div>
            <div style={{
              background: theme.bgCardHover,
              color: theme.accent,
              padding: '8px 20px',
              borderRadius: 20,
              display: 'inline-block',
              fontSize: 14,
              fontWeight: 700,
              marginBottom: 32,
            }}>
              30-Day Free Trial
            </div>
            <ul style={{ listStyle: 'none', textAlign: 'left', marginBottom: 32 }}>
              {[
                'Full NBA game log analysis',
                'In/Out player correlation tools',
                'NFL matchup breakdowns',
                'MLB pitcher/hitter matchups',
                'Live prop odds from top books',
                'Daily hot hitter trends',
              ].map((feature) => (
                <li key={feature} style={{ padding: '8px 0', borderBottom: `1px solid ${theme.border}`, display: 'flex', gap: 10, alignItems: 'center' }}>
                  <span style={{ color: theme.accent, fontWeight: 700 }}>✓</span>
                  <span style={{ color: theme.textPrimary, fontSize: 15 }}>{feature}</span>
                </li>
              ))}
            </ul>
            <button
              onClick={() => navigate(isAuthenticated ? '/billing' : '/register')}
              style={{
                background: theme.accent,
                color: 'white',
                border: 'none',
                width: '100%',
                padding: '14px',
                fontSize: 16,
                fontWeight: 700,
                borderRadius: 8,
                cursor: 'pointer',
              }}
            >
              {isAuthenticated ? 'Manage Subscription' : 'Start Free Trial'}
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ background: '#08090c', color: theme.textSecondary, textAlign: 'center', padding: '32px 24px', fontSize: 14 }}>
        <div style={{ marginBottom: 8 }}>
          <span style={{ color: theme.accent, fontWeight: 700 }}>Sports Analytics Pro</span>
        </div>
        <div>
          Contact: <a href="mailto:pydata2026@gmail.com" style={{ color: theme.textSecondary }}>pydata2026@gmail.com</a>
        </div>
        <div style={{ marginTop: 8, color: theme.textMuted }}>© 2026 Sports Analytics Pro. All rights reserved.</div>
      </footer>
    </div>
  );
}
