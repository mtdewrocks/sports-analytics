import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { theme } from '../theme';
import useIsMobile from '../hooks/useIsMobile';
import { CROSS_SPORT_PAGES, isInSeason, sportsBySeason } from '../siteMap';
import type { SitePage } from '../siteMap';

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

      <div style={{ ...grid, marginBottom: 32 }}>
        {CROSS_SPORT_PAGES.map((page) => <PageCard key={page.to} page={page} color={theme.accent} />)}
      </div>

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
    </div>
  );
}
