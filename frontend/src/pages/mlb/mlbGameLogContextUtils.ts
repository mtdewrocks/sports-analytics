import { theme } from '../../theme';

// Types, formatting and column-order helpers for the MLB Game Log's
// upcoming-game context (MLBGameLogContext.tsx). Kept in their own module so
// the component file only exports components (react-refresh lint rule).

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export type LineupMetric = 'k_pct' | 'avg' | 'woba' | 'iso' | 'bb_pct';
export type LineupStats = Partial<Record<LineupMetric, number | null>>;

export interface PriceRung { line: number; price: number; books: string[]; }

export interface NextGame {
  status: 'in_lineup' | 'pending' | 'out' | 'no_game';
  team: string | null;
  opponent: string | null;
  is_home: boolean | null;
  date: string | null;
  game_time_utc: string | null;
  batting_order: number | null;
  pitcher: string | null;
  throws: 'L' | 'R' | null;
  vs_side: 'L' | 'R' | null;
  pitcher_split: { AVG?: number; wOBA?: number; SLG?: number; 'K%'?: number; 'BB%'?: number } | null;
  pitcher_season: { games_started: number | null; era: number | null; ip_per_start: number | null } | null;
  line: number | null;
  price: PriceRung | null;
}

export interface VsHand {
  hand: 'L' | 'R';
  games: number;
  over: number;
  total: number;
  pct: number;
  avg?: number | null;
  obp?: number | null;
  slg?: number | null;
  k_pct?: number | null;
}

export interface NextStart {
  date: string | null;
  game_time_utc: string | null;
  opponent: string | null;
  is_home: boolean | null;
  throws: 'L' | 'R' | null;
  lineup_status: 'posted' | 'projected' | 'unknown';
  batters: number | null;
  tonight: LineupStats;
  faced_avg: LineupStats;
  league: LineupStats | null;
  key_metric: LineupMetric;
  flag: { key: string; count: number | null; faced_avg: number | null; op: 'ge' | 'le'; threshold: number } | null;
  similar: { side: 'above' | 'below'; metric: LineupMetric; over: number; total: number; pct: number } | null;
  walks_per_9: number | null;
  line: number | null;
  prices: { over: PriceRung | null; under: PriceRung | null };
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

export function fmtRate(v?: number | null): string {
  return v == null ? '—' : v.toFixed(3).replace(/^0/, '');
}
export function fmtPct(v?: number | null): string {
  return v == null ? '—' : `${v.toFixed(1)}%`;
}
export function fmtMetric(m: LineupMetric, v?: number | null): string {
  return m === 'k_pct' || m === 'bb_pct' ? fmtPct(v) : fmtRate(v);
}
export function fmtPrice(p: number): string {
  return p > 0 ? `+${p}` : `${p}`;
}
export function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}
export function gameWhen(date: string | null, timeUtc: string | null): string {
  if (timeUtc) {
    const d = new Date(timeUtc);
    if (!isNaN(d.getTime())) {
      return d.toLocaleString(undefined, { weekday: 'short', month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    }
  }
  if (date) {
    const d = new Date(`${date}T12:00:00`);
    if (!isNaN(d.getTime())) return d.toLocaleDateString(undefined, { weekday: 'short', month: 'numeric', day: 'numeric' });
  }
  return '';
}
export function handWord(h: 'L' | 'R' | null): string {
  return h === 'L' ? 'left-handed' : h === 'R' ? 'right-handed' : '';
}

export const METRIC_LABELS: Record<LineupMetric, string> = {
  k_pct: 'Strikeout %',
  avg: 'Batting avg',
  woba: 'wOBA',
  iso: 'Isolated power',
  bb_pct: 'Walk %',
};
export const METRIC_SHORT: Record<LineupMetric, string> = {
  k_pct: 'K%', avg: 'avg', woba: 'wOBA', iso: 'ISO', bb_pct: 'BB%',
};

// Column order follows the selected pitcher stat: the numbers that drive
// that prop come first (hits -> batting average and contact; strikeouts ->
// strikeout %), the rest trail behind.
export const LINEUP_ORDER: Record<string, LineupMetric[]> = {
  pitcher_strikeouts: ['k_pct', 'avg', 'woba', 'iso', 'bb_pct'],
  pitcher_hits_allowed: ['avg', 'woba', 'iso', 'bb_pct', 'k_pct'],
  pitcher_earned_runs: ['woba', 'iso', 'avg', 'bb_pct', 'k_pct'],
  pitcher_walks: ['bb_pct', 'k_pct', 'avg', 'woba', 'iso'],
  pitcher_outs: ['woba', 'avg', 'k_pct', 'bb_pct', 'iso'],
  pitcher_record_a_win: ['woba', 'avg', 'k_pct', 'bb_pct', 'iso'],
};
export function lineupOrder(stat: string): LineupMetric[] {
  return LINEUP_ORDER[stat] ?? LINEUP_ORDER.pitcher_strikeouts;
}

// Does a HIGHER lineup value help this pitcher's Over? (More strikeout-prone
// lineups help a strikeouts Over; better-hitting lineups help hits/runs
// Overs and hurt an outs or win Over.)
const HIGHER_HELPS_OVER: Record<string, Partial<Record<LineupMetric, boolean>>> = {
  pitcher_strikeouts: { k_pct: true, bb_pct: false, avg: false, woba: false, iso: false },
  pitcher_hits_allowed: { avg: true, woba: true, iso: true, k_pct: false },
  pitcher_earned_runs: { woba: true, iso: true, avg: true, bb_pct: true, k_pct: false },
  pitcher_walks: { bb_pct: true, k_pct: true },
  pitcher_outs: { woba: false, avg: false, iso: false, bb_pct: false, k_pct: true },
  pitcher_record_a_win: { woba: false, avg: false, iso: false, k_pct: true },
};

/** Blue when this lineup value is on the side that helps the Over versus the
 *  league benchmark, red when it hurts it, neutral otherwise or if unknown. */
export function overColor(stat: string, m: LineupMetric, v?: number | null, bench?: number | null): string {
  const dir = HIGHER_HELPS_OVER[stat]?.[m];
  if (dir === undefined || v == null || bench == null) return theme.textPrimary;
  const tol = m === 'k_pct' || m === 'bb_pct' ? 1.0 : 0.008;
  if (Math.abs(v - bench) < tol) return theme.textPrimary;
  const higher = v > bench;
  return higher === dir ? theme.dataBlue : theme.dataRed;
}

const FLAG_LABELS: Record<string, (t: number) => string> = {
  high_k_hitter: (t) => `Hitters ${t}%+ K`,
  high_avg_hitter: (t) => `Hitters ${fmtRate(t)}+ avg`,
  high_bb_hitter: (t) => `Hitters ${t}%+ walks`,
  high_woba_hitter: (t) => `Hitters ${fmtRate(t)}+ wOBA`,
  high_iso_hitter: (t) => `Hitters ${fmtRate(t)}+ ISO`,
};
export function flagLabel(flag: NextStart['flag']): string | null {
  if (!flag) return null;
  const f = FLAG_LABELS[flag.key];
  return f ? f(flag.threshold) : null;
}

// Rough league-wide hitting benchmarks, for coloring a starter's split
// against the batter on the batter card (red = tough on hitters).
export const HITTER_BENCH = { AVG: 0.245, wOBA: 0.315, SLG: 0.405, 'K%': 22.5, 'BB%': 8.5 } as const;

