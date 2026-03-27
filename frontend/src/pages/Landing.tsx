import React from 'react';
import { useNavigate, Link } from 'react-router-dom';

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', color: '#333' }}>
      {/* Hero */}
      <section style={{
        background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
        color: 'white',
        padding: '100px 24px 80px',
        textAlign: 'center',
      }}>
        <div style={{ maxWidth: 720, margin: '0 auto' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🏆</div>
          <h1 style={{ fontSize: 48, fontWeight: 800, marginBottom: 16, lineHeight: 1.1 }}>
            Sports Analytics Pro
          </h1>
          <p style={{ fontSize: 20, color: '#aaa', marginBottom: 40, lineHeight: 1.6 }}>
            Data-driven insights for NBA, NFL &amp; MLB betting and fantasy sports
          </p>
          <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button
              onClick={() => navigate('/register')}
              style={{
                background: '#e94560',
                color: 'white',
                border: 'none',
                padding: '14px 36px',
                fontSize: 16,
                fontWeight: 700,
                borderRadius: 8,
                cursor: 'pointer',
                transition: 'background 0.2s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = '#c0392b')}
              onMouseLeave={(e) => (e.currentTarget.style.background = '#e94560')}
            >
              Get Started Free
            </button>
            <Link to="/login" style={{
              background: 'transparent',
              color: '#aaa',
              border: '1px solid #555',
              padding: '14px 36px',
              fontSize: 16,
              borderRadius: 8,
              display: 'inline-flex',
              alignItems: 'center',
            }}>
              Already have an account? Login
            </Link>
          </div>
        </div>
      </section>

      {/* Feature Cards */}
      <section style={{ padding: '80px 24px', background: '#f9f9f9' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <h2 style={{ textAlign: 'center', fontSize: 32, fontWeight: 700, marginBottom: 48, color: '#1a1a2e' }}>
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
                  background: 'white',
                  borderRadius: 12,
                  padding: '36px 28px',
                  flex: '1 1 280px',
                  maxWidth: 320,
                  boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
                  textAlign: 'center',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.transform = 'translateY(-4px)';
                  (e.currentTarget as HTMLElement).style.boxShadow = '0 8px 30px rgba(0,0,0,0.14)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.transform = '';
                  (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 20px rgba(0,0,0,0.08)';
                }}
              >
                <div style={{ fontSize: 48, marginBottom: 16 }}>{card.icon}</div>
                <h3 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12, color: '#1a1a2e' }}>{card.title}</h3>
                <p style={{ color: '#666', lineHeight: 1.6, fontSize: 14 }}>{card.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section style={{ padding: '80px 24px', background: '#1a1a2e', color: 'white', textAlign: 'center' }}>
        <div style={{ maxWidth: 500, margin: '0 auto' }}>
          <h2 style={{ fontSize: 32, fontWeight: 700, marginBottom: 12 }}>Simple Pricing</h2>
          <p style={{ color: '#aaa', marginBottom: 40 }}>No hidden fees. Cancel anytime.</p>
          <div style={{
            background: '#16213e',
            borderRadius: 16,
            padding: '48px 40px',
            border: '2px solid #e94560',
            boxShadow: '0 8px 32px rgba(233,69,96,0.2)',
          }}>
            <div style={{ fontSize: 18, color: '#e94560', fontWeight: 700, marginBottom: 8 }}>All-Access Pass</div>
            <div style={{ fontSize: 52, fontWeight: 800, marginBottom: 4 }}>
              $5.99<span style={{ fontSize: 20, fontWeight: 400, color: '#aaa' }}>/month</span>
            </div>
            <div style={{
              background: '#0f3460',
              color: '#4ecca3',
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
                <li key={feature} style={{ padding: '8px 0', borderBottom: '1px solid #0f3460', display: 'flex', gap: 10, alignItems: 'center' }}>
                  <span style={{ color: '#2ecc71', fontWeight: 700 }}>✓</span>
                  <span style={{ color: '#ccc', fontSize: 15 }}>{feature}</span>
                </li>
              ))}
            </ul>
            <button
              onClick={() => navigate('/register')}
              style={{
                background: '#e94560',
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
              Start Free Trial
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ background: '#111', color: '#666', textAlign: 'center', padding: '32px 24px', fontSize: 14 }}>
        <div style={{ marginBottom: 8 }}>
          <span style={{ color: '#e94560', fontWeight: 700 }}>Sports Analytics Pro</span>
        </div>
        <div>
          Contact: <a href="mailto:pydata2026@gmail.com" style={{ color: '#aaa' }}>pydata2026@gmail.com</a>
        </div>
        <div style={{ marginTop: 8, color: '#444' }}>© 2026 Sports Analytics Pro. All rights reserved.</div>
      </footer>
    </div>
  );
}
