import { Link } from 'react-router-dom';
import { theme } from '../theme';

interface PageLink {
  label: string;
  to: string;
  description: string;
}

interface SportSection {
  sport: string;
  color: string;
  pages: PageLink[];
}

// Colors verified via WCAG contrast check against the dark card background
// (theme.bgCard, #161b22) -- the original light-mode sport colors (navy
// #1a1a2e, blue #0f3460, purple #7b2d8e) all fail the 4.5:1 minimum here
// (1.01 / 1.38 / 2.15), since they were tuned for use on a WHITE card.
// These are brighter equivalents that keep each sport visually distinct
// while actually being legible on a dark surface.
const sections: SportSection[] = [
  {
    sport: 'NFL',
    color: '#5b9bf0',
    pages: [
      { label: 'Game Log', to: '/nfl/game-log', description: 'Player stats by week, with opponent defense context' },
      { label: 'Matchup', to: '/nfl/matchup', description: 'Team comparison and projected game script for an upcoming game' },
      { label: 'Mismatches', to: '/nfl/mismatches', description: "This week's biggest statistical edges, league-wide" },
    ],
  },
  {
    sport: 'MLB',
    color: '#3ab7d1',
    pages: [
      { label: 'Matchup', to: '/mlb/matchup', description: 'Starting pitcher matchup breakdown' },
      { label: 'Bullpen', to: '/mlb/bullpen', description: 'Bullpen workload and freshness by team' },
      { label: 'Hot Hitters', to: '/mlb/hot-hitters', description: 'Players trending up recently' },
      { label: 'Props', to: '/mlb/props', description: 'Prop research across recent games' },
    ],
  },
  {
    sport: 'NBA',
    color: '#c674db',
    pages: [
      { label: 'Game Log', to: '/nba/game-log', description: 'Player stats by game' },
      { label: 'In/Out', to: '/nba/in-out', description: 'Availability and injury context' },
      { label: 'Props', to: '/nba/props', description: 'Prop research across recent games' },
    ],
  },
];

export default function Dashboard() {
  return (
    <div style={{ padding: 32, maxWidth: 1100, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 56px)' }}>
      <h1 style={{ color: theme.textPrimary, marginBottom: 4 }}>Sports Analytics</h1>
      <p style={{ color: theme.textSecondary, marginBottom: 32 }}>Pick a sport and a page to get started.</p>

      {sections.map((section) => (
        <div key={section.sport} style={{ marginBottom: 32 }}>
          <h2 style={{ color: section.color, fontSize: 18, marginBottom: 12 }}>{section.sport}</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
            {section.pages.map((page) => (
              <Link
                key={page.to}
                to={page.to}
                style={{
                  display: 'block', textDecoration: 'none', color: 'inherit',
                  background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8,
                  padding: 18, boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = theme.bgCardHover; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = theme.bgCard; }}
              >
                <div style={{ fontWeight: 700, fontSize: 15, color: section.color, marginBottom: 6 }}>
                  {page.label}
                </div>
                <div style={{ fontSize: 13, color: theme.textSecondary, lineHeight: 1.4 }}>{page.description}</div>
              </Link>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
