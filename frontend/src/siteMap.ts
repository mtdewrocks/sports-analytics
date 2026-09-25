/**
 * Single source of truth for every sport page on the site.
 *
 * The Navbar (desktop dropdowns, mobile tab bar + chip bar), the Dashboard
 * cards and the Landing page's coverage cards all read from here. They used
 * to each keep their own hand-written list, and the Dashboard/Landing copies
 * fell badly behind (the Dashboard showed 10 of 26 pages). Add a new page
 * here and it shows up everywhere at once.
 *
 * Pages are grouped by workflow -- what's happening today / this week first,
 * then deeper player research, then betting tools, then conditions. The
 * Navbar flattens the groups in order; the first page of the first group is
 * where the mobile tab bar lands when a sport is tapped.
 */

export interface SitePage {
  label: string;
  to: string;
  description: string;
}

export interface PageSection {
  label: string;
  pages: SitePage[];
}

export interface Sport {
  key: 'nfl' | 'mlb' | 'nba';
  label: string;
  icon: string;
  /** Legible on the dark card background -- see Dashboard.tsx. */
  color: string;
  /** Months (1-12) the season is active, preseason/postseason included.
   *  Wraps across the new year when start > end. */
  season: { start: number; end: number };
  /** Landing page coverage-card copy. */
  pitch: string;
  sections: PageSection[];
}

const SPORTS: Sport[] = [
  {
    key: 'nfl', label: 'NFL', icon: '🏈', color: '#5b9bf0',
    season: { start: 9, end: 2 },
    pitch: 'A weekly mismatch finder, team and fantasy matchups, target and carry share, and a season-long stat screener. Props and game-day weather for every game.',
    sections: [
      {
        label: 'This week',
        pages: [
          { label: 'Mismatches', to: '/nfl/mismatches', description: "This week's biggest statistical edges, league-wide" },
          { label: 'Team Matchup', to: '/nfl/matchup', description: 'Team comparison and projected game script for an upcoming game' },
          { label: 'Fantasy Matchup', to: '/nfl/fantasy-matchup', description: 'Compare players side by side against their matchups' },
        ],
      },
      {
        label: 'Players',
        pages: [
          { label: 'Game Log', to: '/nfl/game-log', description: 'Player stats by week, with opponent defense context' },
          { label: 'Screener', to: '/nfl/season-screener', description: 'Find every player clearing a stat threshold this season' },
          { label: 'In/Out', to: '/nfl/in-out', description: 'How players produce with teammates in or out of the lineup' },
        ],
      },
      {
        label: 'Usage',
        pages: [
          { label: 'Team Usage', to: '/nfl/team-usage', description: 'Target and carry share for every player on a team' },
          { label: 'Usage Trend', to: '/nfl/usage-trend', description: "A player's share of targets or carries, week by week" },
        ],
      },
      {
        label: 'Lines',
        pages: [
          { label: 'Props', to: '/nfl/props', description: 'Player prop lines with the best price across books' },
        ],
      },
      {
        label: 'Conditions',
        pages: [
          { label: 'Weather', to: '/nfl/weather', description: 'Kickoff forecast and wind for every outdoor game' },
        ],
      },
    ],
  },
  {
    key: 'mlb', label: 'MLB', icon: '⚾', color: '#3ab7d1',
    season: { start: 3, end: 10 },
    pitch: 'Daily pitcher reports and slate-wide matchup edges, pitcher vs. lineup splits, bullpen workload and hot hitters. Props and ballpark weather for every game.',
    sections: [
      {
        label: 'Today',
        pages: [
          { label: 'Pitcher Daily Report', to: '/mlb/pitcher-daily-report', description: "Every starter on today's slate, with form and the opposing lineup" },
          { label: 'Matchup Edge', to: '/mlb/matchup-edge', description: 'Slate-wide best and toughest matchups, platoon edges and strikeout risk' },
        ],
      },
      {
        label: 'Matchups',
        pages: [
          { label: 'Pitcher Matchup', to: '/mlb/matchup', description: "One starter vs. today's lineup, with props and his last 10 starts" },
          { label: 'Team Matchup', to: '/mlb/team-matchup', description: 'Team records, recent form and head-to-head for a game' },
          { label: 'Bullpen', to: '/mlb/bullpen', description: 'Bullpen workload and freshness by team' },
        ],
      },
      {
        label: 'Players',
        pages: [
          { label: 'Game Log', to: '/mlb/game-log', description: 'Hitter and pitcher stats, game by game' },
          { label: 'Hot Hitters', to: '/mlb/hot-hitters', description: 'Hitters on a heater over the last seven days' },
        ],
      },
      {
        label: 'Lines',
        pages: [
          { label: 'Props', to: '/mlb/props', description: 'Pitcher and hitter prop lines with the best price across books' },
        ],
      },
      {
        label: 'Conditions',
        pages: [
          { label: 'Weather', to: '/mlb/weather', description: "Wind, temperature and park orientation for today's games" },
        ],
      },
    ],
  },
  {
    key: 'nba', label: 'NBA', icon: '🏀', color: '#c674db',
    season: { start: 10, end: 6 },
    pitch: 'Game logs with opponent and back-to-back context, in/out teammate analysis, team usage and team matchups, plus player props.',
    sections: [
      {
        label: 'Players',
        pages: [
          { label: 'Game Log', to: '/nba/game-log', description: 'Player stats by game, with opponent and back-to-back context' },
          { label: 'In/Out', to: '/nba/in-out', description: 'How players produce with teammates in or out of the lineup' },
          { label: 'Team Usage', to: '/nba/team-usage', description: 'How a team splits its usage across players' },
        ],
      },
      {
        label: 'Matchups',
        pages: [
          { label: 'Team Matchup', to: '/nba/team-matchup', description: 'Two teams side by side, with league ranks' },
        ],
      },
      {
        label: 'Lines',
        pages: [
          { label: 'Props', to: '/nba/props', description: 'Player prop lines with the best price across books' },
        ],
      },
    ],
  },
];

/**
 * Betting tools -- cross-sport, one page per tool with its own sport toggle,
 * rather than a copy under every sport. Deliberately placed AFTER the sports
 * everywhere (desktop menu, mobile tab bar, Dashboard, Landing): the sport
 * analytics are the product's focus, these are the tools built on top of it.
 * Props stays under each sport -- it's reference data for that sport, not a
 * bet finder.
 */
export interface BettingGroup {
  key: 'betting';
  label: string;
  icon: string;
  color: string;
  pitch: string;
  sections: PageSection[];
}

export const BETTING: BettingGroup = {
  key: 'betting',
  label: 'Betting',
  icon: '💰',
  color: '#1d9e75',
  pitch: 'Tools that turn the research into bets: +EV prices across books, the best rung on every alt ladder, hit rates against today\'s lines, and middles and arbs.',
  // One unlabeled section: four pages don't need sub-headers. A section with
  // an empty label renders without a header in the Navbar and Dashboard.
  sections: [
    {
      label: '',
      pages: [
        { label: 'Hit Rate Sheet', to: '/betting/hit-rate-sheet', description: "How often players have cleared today's prop lines" },
        { label: 'EV Finder', to: '/betting/ev', description: 'Props where a book is paying more than the fair, no-vig price' },
        { label: 'Alt-Line Value', to: '/betting/alt-lines', description: "The best-value rung on each player's alternate ladder" },
        { label: 'Middles & Arbs', to: '/betting/middles', description: 'Line gaps between sportsbooks worth middling or arbing' },
      ],
    },
  ],
};

export function bettingPages(): SitePage[] {
  return BETTING.sections.flatMap((s) => s.pages);
}

/** Sports the betting tools cover, in-season first -- the default for their
 *  sport toggle. NBA joins once its props come from the same pipeline. */
export type BettingSport = 'mlb' | 'nfl';
export function bettingSports(date: Date = new Date()): BettingSport[] {
  return sportsBySeason(date)
    .map((s) => s.key)
    .filter((k): k is BettingSport => k === 'mlb' || k === 'nfl');
}

export function isInSeason(sport: Sport, date: Date = new Date()): boolean {
  const m = date.getMonth() + 1;
  const { start, end } = sport.season;
  return start <= end ? m >= start && m <= end : m >= start || m <= end;
}

/** Sports in season first, then the rest. Within each half the order above
 *  (NFL, MLB, NBA) is the tiebreak, so the result is stable. */
export function sportsBySeason(date: Date = new Date()): Sport[] {
  return [
    ...SPORTS.filter((s) => isInSeason(s, date)),
    ...SPORTS.filter((s) => !isInSeason(s, date)),
  ];
}

export function flatPages(sport: Sport): SitePage[] {
  return sport.sections.flatMap((s) => s.pages);
}
