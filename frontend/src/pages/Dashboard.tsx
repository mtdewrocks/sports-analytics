import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { theme } from '../theme';
import useIsMobile from '../hooks/useIsMobile';
import { BETTING, isInSeason, sportsBySeason } from '../siteMap';
import type { SitePage } from '../siteMap';
import { getBillingStatus } from '../api/billing';

// Every page comes from siteMap.ts, the same list the Navbar reads, so a new
// page can't be added to the menu and forgotten here again. Sport colors are
// defined there too (verified for contrast against theme.bgCard).

function PageCard({ page, color }: { page: SitePage; color: string }) {
  return (
    <Link
      to={page.to}
      style={{
        display: 'block', textDecoration: 'none', color: 'inherit',
        background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8,
        padding: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
      }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = theme.bgCardHover; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = theme.bgCard; }}
    >
      <div style={{ fontWeight: 700, fontSize: 15, color, marginBottom: 6 }}>{page.label}</div>
      <div style={{ fontSize: 13, color: theme.textSecondary, lineHeight: 1.4 }}>{page.description}</div>
    </Link>
  );
}

const grid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
  gap: 12,
};

const sectionLabel: CSSProperties = {
  color: theme.textSecondary,
  fontSize: 12,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: 0.6,
  margin: '16px 0 8px',
};

/** Open-beta note: shown while free access runs well past a normal trial
 *  (the backend's BETA_ENDS_AT), with where to send feedback. */
function BetaBanner() {
  const [ends, setEnds] = useState<string | null>(null);
  useEffect(() => {
    getBillingStatus()
      .then((res) => {
        const s = res.data;
        if (s?.status === 'trialing' && (s.days_remaining ?? 0) > 45 && s.trial_ends_at) setEnds(s.trial_ends_at);
      })
      .catch(() => {});
  }, []);
  if (!ends) return null;
  const date = new Date(ends).toLocaleDateString([], { month: 'long', day: 'numeric', year: 'numeric' });
  return (
    <div style={{
      background: 'rgba(29,158,117,0.1)', border: `1px solid ${theme.accent}`, borderRadius: 8,
      padding: '10px 14px', marginBottom: 20, fontSize: 13.5, color: theme.textPrimary, lineHeight: 1.5,
    }}>
      <strong style={{ color: theme.accent }}>Free beta:</strong> full access through {date}, no card needed.
      Something broken, confusing or missing? Tell us at{' '}
      <a href="mailto:sportsanalytics2026@gmail.com?subject=Beta%20feedback" style={{ color: theme.accent }}>
        sportsanalytics2026@gmail.com
      </a>.
    </div>
  );
}

export default function Dashboard() {
  const isMobile = useIsMobile();
  const sports = sportsBySeason();

  return (
    <div style={{
      padding: isMobile ? 16 : 32, maxWidth: 1100, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 56px)',
    }}>
      <h1 style={{ color: theme.textPrimary, fontSize: isMobile ? 26 : 32, lineHeight: 1.2, margin: '0 0 6px' }}>Sports Analytics</h1>
      <p style={{ color: theme.textSecondary, marginBottom: 24 }}>Pick a sport and a page to get started.</p>
      <BetaBanner />

      {sports.map((sport) => (
        <section key={sport.key} style={{ marginBottom: 36 }}>
          <h2 style={{ color: sport.color, fontSize: 20, margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span aria-hidden>{sport.icon}</span>
            {sport.label}
            {!isInSeason(sport) && (
              <span style={{
                fontSize: 11, fontWeight: 600, color: theme.textSecondary,
                border: `1px solid ${theme.borderStrong}`, borderRadius: 999, padding: '2px 8px',
              }}>
                Off-season
              </span>
            )}
          </h2>

          {sport.sections.map((sec) => (
            <div key={sec.label}>
              <div style={sectionLabel}>{sec.label}</div>
              <div style={grid}>
                {sec.pages.map((page) => <PageCard key={page.to} page={page} color={sport.color} />)}
              </div>
            </div>
          ))}
        </section>
      ))}

      {/* After the sports, same as the nav: analytics first, tools on top. */}
      <section style={{ marginBottom: 36 }}>
        <h2 style={{ color: BETTING.color, fontSize: 20, margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span aria-hidden>{BETTING.icon}</span>
          {BETTING.label}
        </h2>
        {BETTING.sections.map((sec) => (
          <div key={sec.label} style={sec.label ? undefined : { marginTop: 12 }}>
            {sec.label && <div style={sectionLabel}>{sec.label}</div>}
            <div style={grid}>
              {sec.pages.map((page) => <PageCard key={page.to} page={page} color={BETTING.color} />)}
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
