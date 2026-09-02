import { Link } from 'react-router-dom';

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

const sections: SportSection[] = [
  {
    sport: 'NFL',
    color: '#1a1a2e',
    pages: [
      { label: 'Game Log', to: '/nfl/game-log', description: 'Player stats by week, with opponent defense context' },
      { label: 'Matchup', to: '/nfl/matchup', description: 'Team comparison and projected game script for an upcoming game' },
      { label: 'Mismatches', to: '/nfl/mismatches', description: "This week's biggest statistical edges, league-wide" },
    ],
  },
  {
    sport: 'MLB',
    color: '#0f3460',
    pages: [
      { label: 'Matchup', to: '/mlb/matchup', description: 'Starting pitcher matchup breakdown' },
      { label: 'Bullpen', to: '/mlb/bullpen', description: 'Bullpen workload and freshness by team' },
      { label: 'Hot Hitters', to: '/mlb/hot-hitters', description: 'Players trending up recently' },
      { label: 'Props', to: '/mlb/props', description: 'Prop research across recent games' },
    ],
  },
  {
    sport: 'NBA',
    color: '#7b2d8e',
    pages: [
      { label: 'Game Log', to: '/nba/game-log', description: 'Player stats by game' },
      { label: 'In/Out', to: '/nba/in-out', description: 'Availability and injury context' },
      { label: 'Props', to: '/nba/props', description: 'Prop research across recent games' },
    ],
  },
];

export default function Dashboard() {
  return (
    <div style={{ padding: 32, maxWidth: 1100, margin: '0 auto' }}>
      <h1 style={{ color: '#1a1a2e', marginBottom: 4 }}>Sports Analytics</h1>
      <p style={{ color: '#888', marginBottom: 32 }}>Pick a sport and a page to get started.</p>

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
                  background: 'white', border: '1px solid #eee', borderRadius: 8,
                  padding: 18, boxShadow: '0 2px 8px rgba(0,0,0,0.05)',
                }}
              >
                <div style={{ fontWeight: 700, fontSize: 15, color: section.color, marginBottom: 6 }}>
                  {page.label}
                </div>
                <div style={{ fontSize: 13, color: '#888', lineHeight: 1.4 }}>{page.description}</div>
              </Link>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
