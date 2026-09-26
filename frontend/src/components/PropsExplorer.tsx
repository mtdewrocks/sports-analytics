import React, { useState, useEffect, useMemo } from 'react';
import LoadingSpinner from './LoadingSpinner';
import StatCard from './StatCard';
import SegmentedToggle from './SegmentedToggle';
import BottomSheet from './BottomSheet';
import ScrollTable from './ScrollTable';
import { stickyColStyle } from './tableStyles';
import OddsDisclaimer, { latestFetchedAt } from './OddsDisclaimer';
import useIsMobile from '../hooks/useIsMobile';
import { theme } from '../theme';

// ── Constants ─────────────────────────────────────────────────────────────────

const META_COLS = new Set([
  'line_id', 'player', 'player_name', 'name', 'team', 'market',
  'prop_type', 'stat', 'line', 'line_value', 'over_under',
  'bet_type', 'category', 'description', 'mlb_team_long',
  'date', 'game_date', 'home_team', 'away_team', 'commence_time', 'sport',
  // Carried through the pivot so the staleness banner can report the age of
  // the rows ON SCREEN. Without it here, every non-meta column is treated as a
  // sportsbook and this shows up as a phantom book with timestamps for prices.
  'fetched_at',
  // Whether this game's commence_time has passed -- the book stopped taking
  // these lines at kickoff, so a live row is a frozen snapshot, not a
  // current price. Same reason as fetched_at above: without it here, a
  // boolean column reads as a phantom sportsbook.
  'is_live',
]);

const MIN_ODDS_OPTIONS = [
  { label: 'Any', value: null },
  { label: '-100', value: -100 },
  { label: '-150', value: -150 },
  { label: '-200', value: -200 },
  { label: '-250', value: -250 },
  { label: '-300', value: -300 },
  { label: '-350', value: -350 },
  { label: '-400', value: -400 },
  { label: '-450', value: -450 },
  { label: '-500', value: -500 },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Market key -> readable label, for prose. The raw key is fine in a dropdown
 *  where it sits beside its siblings, but reads as a database column in the
 *  middle of a sentence.
 *
 *  BASE labels only. `_alternate` is handled as a suffix below, which halves
 *  the map and means a new alternate ladder is labelled correctly the day it
 *  appears without anyone touching this.
 *
 *  Keys are POST-prefix-strip: get_props.py removes `batter_` for MLB and
 *  `player_` for NFL, so `batter_hits` arrives here as `hits`. That is also
 *  why the batter/pitcher pairs below are spelled out -- bare `strikeouts` is
 *  the batter market, and the pitcher one has to say so.
 */
const MARKET_LABELS: Record<string, string> = {
  // ---- MLB, batter ----
  hits: 'hits',
  hits_runs_rbis: 'hits + runs + RBIs',
  home_runs: 'home runs',
  first_home_run: 'first home run',
  rbis: 'RBIs',
  runs_scored: 'runs scored',
  singles: 'singles',
  doubles: 'doubles',
  total_bases: 'total bases',
  stolen_bases: 'stolen bases',
  strikeouts: 'batter strikeouts',
  walks: 'batter walks',
  // ---- MLB, pitcher ----
  pitcher_strikeouts: 'pitcher strikeouts',
  pitcher_hits_allowed: 'hits allowed',
  pitcher_walks: 'walks allowed',
  pitcher_earned_runs: 'earned runs',
  pitcher_outs: 'outs recorded',
  pitcher_record_a_win: 'to record a win',
  // ---- NFL, passing ----
  pass_yds: 'passing yards',
  pass_tds: 'passing touchdowns',
  pass_attempts: 'pass attempts',
  pass_completions: 'completions',
  pass_interceptions: 'interceptions thrown',
  pass_longest_completion: 'longest completion',
  pass_yds_q1: '1st-quarter passing yards',
  // ---- NFL, rushing / receiving ----
  rush_yds: 'rushing yards',
  rush_tds: 'rushing touchdowns',
  rush_attempts: 'rush attempts',
  rush_longest: 'longest rush',
  receptions: 'receptions',
  reception_yds: 'receiving yards',
  reception_tds: 'receiving touchdowns',
  reception_longest: 'longest reception',
  // ---- NFL, combined ----
  rush_reception_yds: 'rush + receiving yards',
  pass_rush_yds: 'pass + rush yards',
  pass_rush_reception_yds: 'pass + rush + receiving yards',
  // ---- NFL, touchdown scorer ----
  anytime_td: 'anytime touchdown',
  '1st_td': 'first touchdown scorer',
  last_td: 'last touchdown scorer',
  // ---- NFL, kicking and defence ----
  kicking_points: 'kicking points',
  field_goals: 'field goals',
  pats: 'extra points',
  sacks: 'sacks',
  solo_tackles: 'solo tackles',
  tackles_assists: 'tackles + assists',
  assists: 'assisted tackles',
};

export function prettyMarket(market: string): string {
  const key = String(market || '');
  const alt = key.endsWith('_alternate');
  const base = alt ? key.slice(0, -'_alternate'.length) : key;
  // Unmapped keys degrade to underscores-as-spaces rather than breaking, so a
  // market added to props_config before this map reads acceptably in the mean
  // time.
  const label = MARKET_LABELS[base] ?? base.replace(/_/g, ' ');
  return alt ? `alternate ${label}` : label;
}

function parseOdds(val: any): number | null {
  if (val === '' || val === null || val === undefined) return null;
  const n = typeof val === 'number' ? val : parseFloat(String(val));
  return isNaN(n) ? null : n;
}

export function formatOdds(n: number): string {
  return n > 0 ? `+${n}` : String(n);
}

/** Book column -> short header, so four books fit across a phone instead of
 *  one. Anything unmapped falls back to its first three letters rather than
 *  breaking, since the book set comes from the data. */
const BOOK_SHORT: Record<string, string> = {
  draftkings: 'DK', fanduel: 'FD', betmgm: 'MGM', caesars: 'CZR', espnbet: 'ESPN',
  pointsbetus: 'PB', betrivers: 'BR', williamhill_us: 'WH', wynnbet: 'WYNN',
  superbook: 'SB', unibet_us: 'UNI', betonlineag: 'BOL', lowvig: 'LV',
  bovada: 'BOV', mybookieag: 'MB', betus: 'BU', fanatics: 'FAN', hardrockbet: 'HR',
};

function shortBook(book: string): string {
  return BOOK_SHORT[book.toLowerCase()] ?? book.replace(/_/g, ' ').slice(0, 3).toUpperCase();
}

/** Books capitalise their own names in ways title-casing gets wrong
 *  ("Draftkings", "Betmgm"), so the known ones are spelled out. */
const BOOK_NAME: Record<string, string> = {
  draftkings: 'DraftKings', fanduel: 'FanDuel', betmgm: 'BetMGM', caesars: 'Caesars',
  espnbet: 'ESPN BET', pointsbetus: 'PointsBet', betrivers: 'BetRivers',
  williamhill_us: 'William Hill', wynnbet: 'WynnBET', superbook: 'SuperBook',
  unibet_us: 'Unibet', betonlineag: 'BetOnline', lowvig: 'LowVig', bovada: 'Bovada',
  mybookieag: 'MyBookie', betus: 'BetUS', fanatics: 'Fanatics', hardrockbet: 'Hard Rock Bet',
};

export function prettyBook(book: string): string {
  return BOOK_NAME[book.toLowerCase()] ?? book.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Market label for a card that already carries the player's name: the
 *  batter/pitcher qualifier is redundant there ("Strikeouts 3.5" under a
 *  pitcher's name), so it's dropped and the first letter capitalised. */
function cardMarketLabel(market: string): string {
  const label = prettyMarket(market).replace(/\b(pitcher|batter) /g, '');
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** Accent-, case- and punctuation-insensitive name, matching the backend's
 *  _name_key() so an Odds API "Jose Berrios" finds "José Berríos". */
function nameKey(name: string): string {
  return String(name).normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().replace(/\./g, '').split(/\s+/).filter(Boolean).join(' ');
}

/** How far a price sits from even money, in cents: -110 and +110 are both 10. */
const distFromEven = (o: number) => Math.abs(Math.abs(o) - 100);

// ── Opposing-lineup strip for pitcher props ───────────────────────────────────

type LineupCountKey =
  | 'high_k_hitter' | 'high_bb_hitter' | 'high_avg_hitter'
  | 'low_avg_hitter' | 'high_iso_hitter' | 'high_woba_hitter';

export interface PitcherLineupContext {
  league: { avg: number | null; woba: number | null; k_pct: number | null; bb_pct: number | null };
  pitchers: Record<string, {
    pitcher: string;
    throws: 'L' | 'R' | null;
    opponent: string | null;
    lineup_posted: boolean;
    batters: number;
    avg: number | null; woba: number | null; k_pct: number | null; bb_pct: number | null;
    counts: Record<LineupCountKey, number> | null;
  }>;
}

type LineupStat = 'avg' | 'woba' | 'k_pct' | 'bb_pct';

/** Which lineup numbers each pitcher market cares about. `higherHelpsPitcher`
 *  sets the colour direction; the counts reuse the Pitcher Daily Report's
 *  cutoffs (backend HITTER_FLAG_THRESHOLDS). No entry = no strip. */
const LINEUP_STRIP: Record<string, { stats: LineupStat[]; counts: LineupCountKey[] }> = {
  pitcher_strikeouts:   { stats: ['k_pct'],                  counts: ['high_k_hitter'] },
  pitcher_hits_allowed: { stats: ['avg', 'woba'],            counts: ['high_avg_hitter', 'low_avg_hitter'] },
  pitcher_earned_runs:  { stats: ['woba', 'avg'],            counts: ['high_woba_hitter', 'high_iso_hitter'] },
  pitcher_walks:        { stats: ['bb_pct'],                 counts: ['high_bb_hitter'] },
  pitcher_outs:         { stats: ['woba', 'bb_pct', 'k_pct'], counts: ['high_woba_hitter', 'high_bb_hitter'] },
};

const STAT_META: Record<LineupStat, { label: string; higherHelpsPitcher: boolean; margin: number; fmt: (v: number) => string }> = {
  k_pct:  { label: 'strikeout rate',  higherHelpsPitcher: true,  margin: 1.5,   fmt: (v) => `${v.toFixed(1)}%` },
  bb_pct: { label: 'walk rate',       higherHelpsPitcher: false, margin: 1.0,   fmt: (v) => `${v.toFixed(1)}%` },
  avg:    { label: 'batting average', higherHelpsPitcher: false, margin: 0.010, fmt: (v) => v.toFixed(3).replace(/^0/, '') },
  woba:   { label: 'wOBA',            higherHelpsPitcher: false, margin: 0.010, fmt: (v) => v.toFixed(3).replace(/^0/, '') },
};

const COUNT_META: Record<LineupCountKey, { label: string; helpsPitcher: boolean }> = {
  high_k_hitter:    { label: 'high strikeout',   helpsPitcher: true },
  low_avg_hitter:   { label: 'low average',      helpsPitcher: true },
  high_bb_hitter:   { label: 'high walk',        helpsPitcher: false },
  high_avg_hitter:  { label: 'high average',     helpsPitcher: false },
  high_iso_hitter:  { label: 'high power (ISO)', helpsPitcher: false },
  high_woba_hitter: { label: 'high wOBA',        helpsPitcher: false },
};

function LineupStrip({ ctx, player, market }: { ctx: PitcherLineupContext | null; player: string; market: string }) {
  const spec = LINEUP_STRIP[market];
  const p = ctx?.pitchers[nameKey(player)];
  if (!spec || !p) return null;

  const label = (
    <div style={{ fontSize: 9.5, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
      Opposing lineup{p.throws ? ` vs ${p.throws === 'L' ? 'left' : 'right'}-handed pitching` : ''}
    </div>
  );
  const wrap: React.CSSProperties = { marginTop: 10, paddingTop: 10, borderTop: `1px solid ${theme.border}` };

  if (!p.lineup_posted) {
    return (
      <div style={wrap}>
        {label}
        <span style={{
          display: 'inline-block', marginTop: 5, fontSize: 10.5, fontWeight: 600, padding: '2px 8px',
          borderRadius: 999, background: 'rgba(232,163,61,0.15)', color: theme.warningText,
        }}>
          Waiting on today's lineup
        </span>
      </div>
    );
  }

  return (
    <div style={wrap}>
      {label}
      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginTop: 5 }}>
        {spec.stats.map((k) => {
          const v = p[k];
          const m = STAT_META[k];
          const lg = ctx?.league[k];
          let color: string = theme.textPrimary;
          if (v != null && lg != null) {
            const diff = m.higherHelpsPitcher ? v - lg : lg - v;
            if (diff >= m.margin) color = theme.dataBlue;
            else if (diff <= -m.margin) color = theme.dataRed;
          }
          return (
            <div key={k}>
              <div style={{ fontSize: 16, fontWeight: 700, color, fontVariantNumeric: 'tabular-nums', lineHeight: 1.2 }}>
                {v == null ? '—' : m.fmt(v)}
              </div>
              <div style={{ fontSize: 10.5, color: theme.textMuted }}>{m.label}</div>
            </div>
          );
        })}
      </div>
      {p.counts && (
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 8 }}>
          {spec.counts.map((c) => {
            const n = p.counts![c] ?? 0;
            const good = COUNT_META[c].helpsPitcher;
            return (
              <span key={c} style={{
                fontSize: 10.5, fontWeight: 600, padding: '3px 8px', borderRadius: 999,
                fontVariantNumeric: 'tabular-nums',
                background: n === 0 ? theme.bgPage : good ? 'rgba(107,168,240,0.15)' : 'rgba(244,87,63,0.15)',
                color: n === 0 ? theme.textMuted : good ? theme.dataBlue : theme.dataRed,
              }}>
                {n} of {p.batters} {COUNT_META[c].label}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Tap-to-open list of the other lines in a group, best price + book each. */
export function AltLines({ items }: { items: { label: string; price: number; book: string }[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <div style={{ marginTop: 10, paddingTop: 8, borderTop: `1px solid ${theme.border}` }}>
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        style={{
          background: 'none', border: 'none', padding: '4px 0', cursor: 'pointer',
          color: theme.accent, fontSize: 12, fontWeight: 600,
        }}
      >
        {items.length} alternate line{items.length !== 1 ? 's' : ''} {open ? '▴' : '▾'}
      </button>
      {open && items.map((it, i) => (
        <div key={i} style={{
          display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 10, alignItems: 'center',
          padding: '7px 0', fontSize: 12.5, color: theme.textPrimary,
          borderBottom: i < items.length - 1 ? `1px solid ${theme.border}` : undefined,
        }}>
          <span>{it.label}</span>
          <span style={{ color: theme.dataBlue, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{formatOdds(Math.round(it.price))}</span>
          <span style={{ color: theme.textMuted, fontSize: 11, minWidth: 72, textAlign: 'right' }}>{prettyBook(it.book)}</span>
        </div>
      ))}
    </div>
  );
}

/** Marks a row whose game has already started. The book stopped taking these
 *  lines at kickoff, so this is a frozen pre-game snapshot rather than a
 *  current price -- shown rather than hidden (unlike Middles & Arbs, which
 *  drops a game entirely once it's live, since those are meant to be
 *  actionable and a frozen line isn't one). */
function LiveBadge() {
  return (
    <span
      title="This game has started -- lines are frozen from just before kickoff, not current."
      style={{
        fontSize: 9, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase',
        color: theme.warningText, border: `1px solid ${theme.warningText}`,
        borderRadius: 4, padding: '1px 5px', marginLeft: 6, whiteSpace: 'nowrap',
      }}
    >
      Live
    </span>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const labelStyle: React.CSSProperties = {
  color: theme.textSecondary,
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 5,
  display: 'block',
};

const selectStyle: React.CSSProperties = {
  width: '100%',
  padding: '7px 10px',
  fontSize: 12,
  borderRadius: 4,
  border: `1px solid ${theme.border}`,
  background: theme.bgCardHover,
  color: theme.textPrimary,
  marginBottom: 14,
  boxSizing: 'border-box',
  cursor: 'pointer',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '7px 10px',
  fontSize: 12,
  borderRadius: 4,
  border: `1px solid ${theme.border}`,
  background: theme.bgCardHover,
  color: theme.textPrimary,
  boxSizing: 'border-box',
  outline: 'none',
};

const dividerStyle: React.CSSProperties = {
  borderBottom: `1px solid ${theme.border}`,
  margin: '14px 0',
};

// ── Component ─────────────────────────────────────────────────────────────────

export interface PropsExplorerProps {
  /** Returns the long-format prop rows for one sport. */
  fetcher: (params: Record<string, any>) => Promise<{ data: Record<string, any>[] }>;
  /** Shown in the sidebar and the empty state. Required, not defaulted: a
   *  default would have let the NFL page keep rendering "MLB Props", which is
   *  exactly the bug this parameter exists to prevent. */
  title: string;
  /** MLB only: opposing-lineup context per probable starter. When given,
   *  pitcher props on the mobile Best view are grouped one card per
   *  pitcher per market (main line + tap-open alternates) with an
   *  "Opposing lineup" strip. */
  pitcherContextFetcher?: () => Promise<{ data: PitcherLineupContext }>;
}

/** Line-shopping grid, shared by the MLB and NFL props pages.
 *
 *  Both sports produce the identical long-format schema from get_props.py and
 *  are pivoted by the same backend helper, so the only thing that differs is
 *  which endpoint to call. Forking this into two 600-line files would mean
 *  every future fix landing once and being forgotten the other time. */
export default function PropsExplorer({ fetcher, title, pitcherContextFetcher }: PropsExplorerProps) {
  const [pitcherCtx, setPitcherCtx] = useState<PitcherLineupContext | null>(null);
  useEffect(() => {
    if (!pitcherContextFetcher) return;
    // A bonus layer: if it fails the cards just render without the strip.
    pitcherContextFetcher().then((res) => setPitcherCtx(res.data)).catch(() => setPitcherCtx(null));
  }, [pitcherContextFetcher]);
  const [allProps, setAllProps]   = useState<Record<string, any>[]>([]);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');

  // Sidebar state
  const [playerSearch, setPlayerSearch]       = useState('');
  const [showPlayerDrop, setShowPlayerDrop]   = useState(false);
  const [selectedPlayer, setSelectedPlayer]   = useState('');
  const [selectedMarket, setSelectedMarket]   = useState('');
  const [selectedBooks, setSelectedBooks]     = useState<Set<string>>(new Set());
  const [minOdds, setMinOdds]                 = useState<number | null>(null);

  const isMobile = useIsMobile();
  const [filtersOpen, setFiltersOpen] = useState(false);
  // Line shopping is what this page is for, so on a phone the default view is
  // the answer -- best price and the book holding it -- with the full grid one
  // tap away rather than removed.
  const [mobileView, setMobileView] = useState<'best' | 'grid'>('best');

  // Load all props on mount
  useEffect(() => {
    setLoading(true);
    fetcher({})
      .then(res => setAllProps(res.data))
      .catch(err => setError(err?.response?.data?.detail || 'Failed to load props.'))
      .finally(() => setLoading(false));
  }, []);

  // Detect column roles and sportsbook columns
  const colRoles = useMemo(() => {
    if (!allProps.length) return { player: '', market: '', line: '', books: [] as string[] };
    const cols = Object.keys(allProps[0]);
    const find = (...names: string[]) => cols.find(c => names.includes(c.toLowerCase())) || '';
    return {
      player: find('player', 'player_name', 'name'),
      market: find('market', 'prop_type', 'stat', 'bet_type', 'category'),
      line:   find('line', 'line_value'),
      books:  cols.filter(c => !META_COLS.has(c.toLowerCase())),
    };
  }, [allProps]);

  // Initialize all books as selected when first loaded
  useEffect(() => {
    if (colRoles.books.length > 0 && selectedBooks.size === 0) {
      setSelectedBooks(new Set(colRoles.books));
    }
  }, [colRoles.books]);

  // Unique filter options
  // The two dropdowns constrain each OTHER: markets narrow to the ones the
  // chosen player actually has, and players narrow to the ones who have the
  // chosen market. Picking Mahomes takes the NFL market list from 37 to 19,
  // and the median NFL player has exactly ONE market -- so for most of the
  // board the unfiltered list is 36 rows of noise.
  //
  // This costs nothing: every row is already in `allProps` from the single
  // fetch on mount, so it's a filter over an in-memory array (~0.4 ms on the
  // larger MLB set), not a request. No spinner, no round trip.
  const uniqueMarkets = useMemo(() => {
    if (!colRoles.market) return [];
    const rows = selectedPlayer && colRoles.player
      ? allProps.filter(r => String(r[colRoles.player] || '').toLowerCase()
                             === selectedPlayer.toLowerCase())
      : allProps;
    return [...new Set(rows.map(r => String(r[colRoles.market] || '')).filter(Boolean))].sort();
  }, [allProps, colRoles.market, colRoles.player, selectedPlayer]);

  // EVERY player, always -- deliberately not narrowed by the selected market.
  //
  // Narrowing it seemed symmetric and was worse: with pass_yds selected the
  // list held only quarterbacks, so searching "Kenneth Walker" returned
  // nothing and the page looked broken. A search box that can't find a player
  // who is plainly in the data is a bug report, not a filter.
  //
  // The market stays selected and the mismatch is explained on the right
  // instead, which is recoverable -- the user can see what happened and change
  // the market.
  const uniquePlayers = useMemo(() => {
    if (!colRoles.player) return [];
    return [...new Set(allProps.map(r => String(r[colRoles.player] || '')).filter(Boolean))].sort();
  }, [allProps, colRoles.player]);

  // A market the current player doesn't have still belongs in the <select>,
  // or the control renders blank while the filter is demonstrably still
  // applied -- the state and the UI would disagree.
  const marketOptions = useMemo(() => (
    selectedMarket && !uniqueMarkets.includes(selectedMarket)
      ? [...uniqueMarkets, selectedMarket].sort()
      : uniqueMarkets
  ), [uniqueMarkets, selectedMarket]);

  // The specific dead end: a real player, a real market, no line between them.
  // Distinct from "no props match the current filters", which says nothing
  // about which filter to change.
  const marketMissingForPlayer = Boolean(
    selectedPlayer && selectedMarket && !uniqueMarkets.includes(selectedMarket),
  );

  // Active sportsbook columns (selected + exist in data)
  const activeCols = useMemo(
    () => colRoles.books.filter(b => selectedBooks.has(b)),
    [colRoles.books, selectedBooks],
  );

  // Row filtering (player + market)
  const filteredProps = useMemo(() => {
    return allProps.filter(row => {
      if (selectedPlayer && String(row[colRoles.player] || '').toLowerCase() !== selectedPlayer.toLowerCase()) return false;
      if (selectedMarket && String(row[colRoles.market] || '').toLowerCase() !== selectedMarket.toLowerCase()) return false;
      return true;
    });
  }, [allProps, selectedPlayer, selectedMarket, colRoles]);

  // Apply min-odds filter: keep rows where at least one active book meets threshold
  const displayProps = useMemo(() => {
    if (minOdds === null) return filteredProps;
    return filteredProps.filter(row =>
      activeCols.some(book => {
        const o = parseOdds(row[book]);
        return o !== null && o >= minOdds;
      }),
    );
  }, [filteredProps, activeCols, minOdds]);

  // Mobile Best view cards. Each row's best price (and the rest, best first)
  // among the active books that clear the min-odds filter. With
  // pitcherContextFetcher set, pitcher props collapse to one card per
  // pitcher per market: the main line -- the one the most books hang, ties
  // to the price closest to even -- on the card, every other line (the
  // _alternate ladder included) in a tap-open list. Everything else stays
  // one card per line, as before.
  const bestCards = useMemo(() => {
    type Priced = { book: string; odds: number };
    type Row = (typeof displayProps)[number];
    type Entry = { row: Row; best: Priced | null; rest: Priced[]; count: number };
    const price = (row: Row): Entry => {
      const priced = activeCols
        .map((b) => ({ book: b, odds: parseOdds(row[b]) }))
        .filter((x): x is Priced => x.odds !== null && (minOdds === null || x.odds >= minOdds))
        .sort((a, b) => b.odds - a.odds);
      return { row, best: priced[0] ?? null, rest: priced.slice(1), count: priced.length };
    };
    const lineOf = (r: Row) => parseFloat(String(colRoles.line ? r[colRoles.line] : '')) || 0;

    const cards: { key: string; main: Entry; alternates: Entry[]; baseMarket: string | null }[] = [];
    const groups = new Map<string, Entry[]>();
    displayProps.forEach((row, i) => {
      const market = colRoles.market ? String(row[colRoles.market] ?? '') : '';
      const base = market.replace(/_alternate$/, '');
      if (pitcherContextFetcher && base.startsWith('pitcher_') && colRoles.player) {
        const key = `${String(row[colRoles.player] ?? '')}|${base}`;
        if (!groups.has(key)) {
          groups.set(key, []);
          cards.push({ key, main: null as unknown as Entry, alternates: [], baseMarket: base });
        }
        groups.get(key)!.push(price(row));
      } else {
        cards.push({ key: `row-${i}`, main: price(row), alternates: [], baseMarket: null });
      }
    });
    for (const card of cards) {
      const entries = groups.get(card.key);
      if (!entries) continue;
      // Prefer the core market's rows for the main line: an alternate rung
      // is never "the" line even when more pick'em apps happen to hang it.
      const core = entries.filter((e) => !String(e.row[colRoles.market] ?? '').endsWith('_alternate') && e.best);
      const pool = core.length > 0 ? core : entries.filter((e) => e.best);
      const main = [...pool].sort((a, b) =>
        b.count - a.count || distFromEven(a.best!.odds) - distFromEven(b.best!.odds))[0] ?? entries[0];
      card.main = main;
      // One entry per line: a core and an alternate row at the same number
      // collapse to whichever pays more.
      const byLine = new Map<number, Entry>();
      for (const e of entries) {
        if (e === main || !e.best) continue;
        const ln = lineOf(e.row);
        if (ln === lineOf(main.row)) continue;
        const cur = byLine.get(ln);
        if (!cur || e.best.odds > cur.best!.odds) byLine.set(ln, e);
      }
      card.alternates = [...byLine.entries()].sort((a, b) => a[0] - b[0]).map(([, e]) => e);
    }
    return cards;
  }, [displayProps, activeCols, minOdds, colRoles, pitcherContextFetcher]);

  const toggleBook = (book: string) => {
    setSelectedBooks(prev => {
      const next = new Set(prev);
      next.has(book) ? next.delete(book) : next.add(book);
      return next;
    });
  };

  const toggleAllBooks = () => {
    if (selectedBooks.size === colRoles.books.length) {
      setSelectedBooks(new Set());
    } else {
      setSelectedBooks(new Set(colRoles.books));
    }
  };

  // Count of filters that are actually narrowing something, for the mobile
  // button label -- "Filters" alone doesn't tell you whether any are on.
  const activeFilterCount =
    (selectedPlayer ? 1 : 0) +
    (selectedMarket ? 1 : 0) +
    (minOdds !== null ? 1 : 0) +
    (colRoles.books.length > 0 && selectedBooks.size !== colRoles.books.length ? 1 : 0);

  // ── Render ─────────────────────────────────────────────────────────────────

  const filterControls = (
      <>
        {/* Player search */}
        <div style={{ marginBottom: 14, position: 'relative' }}>
          <span style={labelStyle}>Player</span>
          <input
            style={inputStyle}
            placeholder="Search player..."
            value={playerSearch}
            onChange={e => {
              setPlayerSearch(e.target.value);
              if (!e.target.value) setSelectedPlayer('');
              setShowPlayerDrop(true);
            }}
            onFocus={() => setShowPlayerDrop(true)}
            onBlur={() => setTimeout(() => setShowPlayerDrop(false), 150)}
          />
          {showPlayerDrop && playerSearch.length > 0 && (
            <div style={{
              position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 300,
              background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 4,
              maxHeight: 200, overflowY: 'auto', boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
            }}>
              {uniquePlayers
                .filter(p => p.toLowerCase().includes(playerSearch.toLowerCase()))
                .slice(0, 60)
                .map(p => (
                  <div
                    key={p}
                    onMouseDown={() => { setSelectedPlayer(p); setPlayerSearch(p); setShowPlayerDrop(false); }}
                    style={{ padding: '7px 10px', cursor: 'pointer', fontSize: 12, color: theme.textPrimary }}
                    onMouseEnter={e => (e.currentTarget.style.background = theme.bgCardHover)}
                    onMouseLeave={e => (e.currentTarget.style.background = theme.bgCard)}
                  >{p}</div>
                ))
              }
              {uniquePlayers.filter(p => p.toLowerCase().includes(playerSearch.toLowerCase())).length === 0 && (
                <div style={{ padding: '7px 10px', color: theme.textMuted, fontSize: 12 }}>No players found</div>
              )}
            </div>
          )}
        </div>

        {/* Market dropdown */}
        <div style={{ marginBottom: 0 }}>
          <span style={labelStyle}>Market</span>
          <select style={selectStyle} value={selectedMarket} onChange={e => setSelectedMarket(e.target.value)}>
            <option value="">All Markets</option>
            {marketOptions.map(m => <option key={m} value={m}>{prettyMarket(m)}</option>)}
          </select>
        </div>

        {/* Min Odds */}
        <div style={{ marginBottom: 0 }}>
          <span style={labelStyle}>Min Odds</span>
          <select
            style={selectStyle}
            value={minOdds === null ? '' : String(minOdds)}
            onChange={e => setMinOdds(e.target.value === '' ? null : parseInt(e.target.value))}
          >
            {MIN_ODDS_OPTIONS.map(o => (
              <option key={o.label} value={o.value === null ? '' : String(o.value)}>{o.label}</option>
            ))}
          </select>
        </div>

        <div style={dividerStyle} />

        {/* Sportsbook checkboxes */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={labelStyle}>Sportsbooks</span>
            <button
              onClick={toggleAllBooks}
              style={{
                background: 'none', border: 'none', color: theme.accent, fontSize: 10,
                cursor: 'pointer', padding: 0, fontWeight: 600, textTransform: 'uppercase',
              }}
            >
              {selectedBooks.size === colRoles.books.length ? 'None' : 'All'}
            </button>
          </div>
          {colRoles.books.map(book => (
            <label key={book} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 7, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={selectedBooks.has(book)}
                onChange={() => toggleBook(book)}
                style={{ accentColor: theme.accent, cursor: 'pointer' }}
              />
              <span style={{ color: selectedBooks.has(book) ? theme.textPrimary : theme.textMuted, fontSize: isMobile ? 14 : 12 }}>
                {prettyBook(book)}
              </span>
            </label>
          ))}
        </div>
      </>
  );

  return (
    <div style={{
      display: 'flex',
      flexDirection: isMobile ? 'column' : 'row',
      height: isMobile ? 'auto' : 'calc(100vh - 60px)',
      minHeight: isMobile ? 'calc(100vh - 60px)' : undefined,
      overflow: isMobile ? 'visible' : 'hidden',
      background: theme.bgPage,
    }}>

      {/* ── Left Sidebar (desktop) ── */}
      {!isMobile && (
        <div style={{
          width: 210,
          flexShrink: 0,
          background: theme.bgCard,
          padding: '18px 14px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <div style={{ color: 'white', fontWeight: 700, fontSize: 15, marginBottom: 16 }}>{title}</div>
          {filterControls}
        </div>
      )}

      {/* ── Filters as a sheet (mobile) ── */}
      {isMobile && (
        <BottomSheet
          open={filtersOpen}
          onClose={() => setFiltersOpen(false)}
          title="Filters"
          footer={
            <button
              onClick={() => setFiltersOpen(false)}
              style={{
                width: '100%', padding: '12px 0', minHeight: 44, borderRadius: 4, border: 'none',
                background: theme.accent, color: 'white', fontSize: 14, fontWeight: 700, cursor: 'pointer',
              }}
            >
              Show {displayProps.length} line{displayProps.length !== 1 ? 's' : ''}
            </button>
          }
        >
          {filterControls}
        </BottomSheet>
      )}

      {/* ── Main Content ── */}
      <div style={{
        flex: 1,
        overflowY: isMobile ? 'visible' : 'auto',
        padding: isMobile ? 16 : '20px 24px',
      }}>
        <OddsDisclaimer fetchedAt={latestFetchedAt(filteredProps)} compact={isMobile} />

        {filteredProps.some((r: any) => r.is_live) && (
          <div style={{ fontSize: 11.5, color: theme.textMuted, marginBottom: 12 }}>
            <span style={{ color: theme.warningText, fontWeight: 700 }}>LIVE</span> marks a game that's
            already started -- lines are frozen from just before kickoff, not current prices.
          </div>
        )}

        {isMobile && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <button
              onClick={() => setFiltersOpen(true)}
              style={{
                padding: '8px 14px', minHeight: 38, borderRadius: 6, cursor: 'pointer',
                border: `1px solid ${activeFilterCount > 0 ? theme.accent : theme.border}`,
                background: theme.bgCard,
                color: activeFilterCount > 0 ? theme.accent : theme.textSecondary,
                fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap',
              }}
            >
              Filters{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ''}
            </button>
            <SegmentedToggle
              value={mobileView}
              onChange={setMobileView}
              size="sm"
              options={[
                { value: 'best', label: 'Best' },
                { value: 'grid', label: 'Grid' },
              ]}
              style={{ marginLeft: 'auto' }}
            />
          </div>
        )}

        {loading && <LoadingSpinner />}

        {error && (
          <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
            {error}
          </div>
        )}

        {!loading && displayProps.length > 0 && (
          <>
            <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 10 }}>
              {displayProps.length} line{displayProps.length !== 1 ? 's' : ''}
              {filteredProps.length !== displayProps.length && ` (${filteredProps.length} before min-odds filter)`}
            </div>
            {isMobile && mobileView === 'best' && (
              <div>
                {bestCards.map((card) => {
                  const { row, best, rest } = card.main;
                  const player = colRoles.player ? String(row[colRoles.player] ?? '') : '';
                  const market = colRoles.market ? String(row[colRoles.market] ?? '') : '';
                  const line = colRoles.line ? String(row[colRoles.line] ?? '') : '';
                  const descriptor = [market ? cardMarketLabel(market) : '', line].filter(Boolean).join(' ');

                  return (
                    <StatCard
                      key={card.key}
                      title={<span style={{ fontWeight: 700 }}>{player || String(row['line_id'] ?? '—')}{row['is_live'] ? <LiveBadge /> : null}</span>}
                      titleAside={colRoles.player && row['team'] ? String(row['team']) : undefined}
                      value={best ? formatOdds(Math.round(best.odds)) : '—'}
                      valueColor={best ? theme.dataBlue : theme.textMuted}
                      valueLabel={best ? prettyBook(best.book) : 'no price'}
                      meta={descriptor ? [descriptor] : undefined}
                      metaSecondary={rest.length > 0
                        ? rest.map((p) => <>{shortBook(p.book)} {formatOdds(Math.round(p.odds))}</>)
                        : undefined}
                    >
                      {card.baseMarket && (
                        <LineupStrip ctx={pitcherCtx} player={player} market={card.baseMarket} />
                      )}
                      {card.alternates.length > 0 && (
                        <AltLines items={card.alternates.map((a) => ({
                          label: `Over ${colRoles.line ? String(a.row[colRoles.line] ?? '') : ''}`.trim(),
                          price: a.best!.odds,
                          book: a.best!.book,
                        }))} />
                      )}
                    </StatCard>
                  );
                })}
              </div>
            )}

            {isMobile && mobileView === 'grid' && (
              <ScrollTable>
                <table style={{ borderCollapse: 'collapse', fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
                  <thead>
                    <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                      <th style={{
                        ...stickyColStyle(theme.bgCardHover),
                        padding: '9px 10px', textAlign: 'left', width: 120, minWidth: 120,
                        fontSize: 11, fontWeight: 600, zIndex: 2,
                      }}>
                        Line
                      </th>
                      {activeCols.map((book) => (
                        <th key={book} title={prettyBook(book)} style={{
                          padding: '9px 8px', textAlign: 'center', whiteSpace: 'nowrap',
                          fontWeight: 600, fontSize: 11, minWidth: 54,
                        }}>
                          {shortBook(book)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {displayProps.map((row, i) => {
                      const bg = i % 2 === 0 ? theme.bgCard : theme.bgPage;
                      const oddsArr = activeCols
                        .map((b) => parseOdds(row[b]))
                        .filter((v): v is number => v !== null && (minOdds === null || v >= minOdds));
                      const bestOdds = oddsArr.length > 0 ? Math.max(...oddsArr) : null;

                      const player = colRoles.player ? String(row[colRoles.player] ?? '') : '';
                      const market = colRoles.market ? String(row[colRoles.market] ?? '') : '';
                      const line = colRoles.line ? String(row[colRoles.line] ?? '') : '';

                      return (
                        <tr key={i} style={{ borderBottom: `1px solid ${theme.border}` }}>
                          <td style={{
                            ...stickyColStyle(bg),
                            padding: '7px 10px', fontSize: 11.5, color: theme.textPrimary,
                            borderRight: `1px solid ${theme.border}`,
                          }}>
                            <div style={{ fontWeight: 700 }}>{player || String(row['line_id'] ?? '—')}{row['is_live'] ? <LiveBadge /> : null}</div>
                            {(market || line) && (
                              <div style={{ fontSize: 10, color: theme.textMuted }}>
                                {[market ? cardMarketLabel(market) : '', line].filter(Boolean).join(' ')}
                              </div>
                            )}
                          </td>
                          {activeCols.map((book) => {
                            const odds = parseOdds(row[book]);
                            const passes = odds !== null && (minOdds === null || odds >= minOdds);
                            const isBest = passes && odds !== null && odds === bestOdds;
                            return (
                              <td key={book} style={{
                                padding: '7px 8px', textAlign: 'center', whiteSpace: 'nowrap', background: bg,
                                color: isBest ? theme.dataBlue : passes ? theme.textPrimary : theme.textMuted,
                                fontWeight: isBest ? 700 : 400,
                              }}>
                                {passes && odds !== null ? formatOdds(Math.round(odds)) : '—'}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </ScrollTable>
            )}

            {!isMobile && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                    <th style={{
                      padding: '10px 16px', textAlign: 'left', whiteSpace: 'nowrap',
                      minWidth: 260, position: 'sticky', left: 0, background: theme.bgCardHover, zIndex: 2,
                    }}>
                      Line
                    </th>
                    {activeCols.map(book => (
                      <th key={book} style={{
                        padding: '10px 14px', whiteSpace: 'nowrap', textAlign: 'center',
                        fontWeight: 600, fontSize: 12, textTransform: 'capitalize',
                      }}>
                        {book.replace(/_/g, ' ')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {displayProps.map((row, i) => {
                    // Best odds = max value among active books that pass min-odds filter
                    const oddsArr = activeCols
                      .map(b => parseOdds(row[b]))
                      .filter((v): v is number => v !== null && (minOdds === null || v >= minOdds));
                    const bestOdds = oddsArr.length > 0 ? Math.max(...oddsArr) : null;

                    return (
                      <tr key={i} style={{ background: i % 2 === 0 ? theme.bgCard : theme.bgPage, borderBottom: `1px solid ${theme.border}` }}>
                        <td style={{
                          padding: '8px 16px', whiteSpace: 'nowrap', fontWeight: 500, fontSize: 13,
                          position: 'sticky', left: 0, color: theme.textPrimary,
                          background: i % 2 === 0 ? theme.bgCard : theme.bgPage, zIndex: 1,
                          borderRight: `1px solid ${theme.border}`,
                        }}>
                          {colRoles.player && colRoles.market
                            ? `${String(row[colRoles.player] ?? '')} · ${cardMarketLabel(String(row[colRoles.market] ?? ''))} ${colRoles.line ? String(row[colRoles.line] ?? '') : ''}`.trim()
                            : String(row['line_id'] ?? '—')}
                          {row['is_live'] ? <LiveBadge /> : null}
                        </td>
                        {activeCols.map(book => {
                          const odds = parseOdds(row[book]);
                          const passes = odds !== null && (minOdds === null || odds >= minOdds);
                          const isBest = passes && odds !== null && odds === bestOdds;
                          return (
                            <td key={book} style={{
                              padding: '8px 14px', textAlign: 'center', whiteSpace: 'nowrap',
                              background: isBest ? '#d4edda' : 'transparent',
                              color: isBest ? '#155724' : passes ? theme.textPrimary : theme.textMuted,
                              fontWeight: isBest ? 700 : 400,
                            }}>
                              {passes && odds !== null ? formatOdds(Math.round(odds)) : '—'}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            )}
          </>
        )}

        {!loading && !error && displayProps.length === 0 && allProps.length > 0 && (
          <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 15, marginTop: 80 }}>
            {marketMissingForPlayer ? (
              <>
                There are no {prettyMarket(selectedMarket)} lines for {selectedPlayer}.
                <div style={{ fontSize: 13, color: theme.textMuted, marginTop: 8 }}>
                  Please choose another market.
                </div>
              </>
            ) : 'No props match the current filters.'}
          </div>
        )}

        {!loading && !error && allProps.length === 0 && (
          <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 15, marginTop: 80 }}>
            {`No ${title.replace(/ Props$/, "")} props data available.`}
          </div>
        )}
      </div>
    </div>
  );
}
