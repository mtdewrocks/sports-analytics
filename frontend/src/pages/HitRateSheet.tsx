import { useEffect, useMemo, useState } from 'react';
import { getMLBHitRateSheet, getNFLHitRateSheet } from '../api/hitRateSheet';
import LoadingSpinner from '../components/LoadingSpinner';
import StatCard from '../components/StatCard';
import SegmentedToggle from '../components/SegmentedToggle';
import ScrollTable from '../components/ScrollTable';
import { stickyColStyle } from '../components/tableStyles';
import OddsDisclaimer, { latestFetchedAt } from '../components/OddsDisclaimer';
import { fieldLabelStyle, fieldStyle } from '../components/filterStyles';
import useIsMobile from '../hooks/useIsMobile';
import { theme } from '../theme';

/**
 * Hit Rate Sheet -- cross-sport (MLB + NFL; NBA is out of scope while its
 * season is dark), so this lives at the pages root next to Dashboard rather
 * than under pages/mlb or pages/nfl. Mirrors the approved mockup
 * (A_FilteredList.dc.html, "Option A") faithfully: a sport tab row, a
 * filter bar (player / market / min hit rate / min odds / time period),
 * a Books toggle row that recomputes best-odds live, quick presets, and a
 * results table whose Season/Recent headers sort independently of which
 * period is the active toggle.
 *
 * Layout note: the mockup's filter bar is a full-width wrapping row, not a
 * sidebar -- so this page uses filterStyles' field tokens (fieldLabelStyle /
 * fieldStyle) for consistent input styling, but does not wrap the bar in
 * FilterPanel/usePanelLayout, since that component's column-sidebar shape
 * would fight the approved design rather than reproduce it.
 */

type Sport = 'mlb' | 'nfl';
type Period = 'season' | 'recent';
type SortKey = 'season' | 'recent';

interface HitRateRow {
  player: string;
  team: string | null;
  opponent: string | null;
  market: string;
  line: number | string;
  season_pct: number;
  season_sample: string;
  recent_pct: number;
  recent_sample: string;
  best_odds: number;
  best_book: string;
  fetched_at?: string | null;
}

// Real sportsbook column names, as get_props() (and this sheet's
// best_odds/best_book computation) spells them -- NOT display labels.
const BOOK_KEYS = ['draftkings', 'fanduel', 'betmgm', 'williamhill_us'] as const;
type BookKey = (typeof BOOK_KEYS)[number];

const BOOK_LABELS: Record<BookKey, string> = {
  draftkings: 'DraftKings',
  fanduel: 'FanDuel',
  betmgm: 'BetMGM',
  williamhill_us: 'Caesars',
};

interface Preset {
  label: string;
  market: string;
  minHitRate: number;
  minOdds: number;
}

interface MarketOption {
  value: string;
  label: string;
}

interface SportConfig {
  label: string;
  fetcher: (params: Record<string, any>) => Promise<{ data: HitRateRow[] }>;
  recentGames: number;
  seasonLabel: string;
  markets: MarketOption[];
  presets: Preset[];
}

// Market keys match MLB_MARKET_STAT_MAP in backend/app/data/mlb.py exactly
// (batter_* markets are prefixed there to disambiguate "strikeouts" thrown
// vs. drawn). Sourced from batter_logs.parquet (MLB Stats API box scores,
// via get_batter_logs.py) rather than Statcast, so runs/RBIs/stolen bases
// are real columns here, not approximated. first_home_run is left out --
// it needs play-order (who homered first), which a per-game total can't
// tell you.
const MLB_MARKETS: MarketOption[] = [
  { value: 'batter_hits', label: 'Hits' },
  { value: 'batter_total_bases', label: 'Total Bases' },
  { value: 'batter_home_runs', label: 'Home Runs' },
  { value: 'batter_doubles', label: 'Doubles' },
  { value: 'batter_singles', label: 'Singles' },
  { value: 'batter_walks', label: 'Walks' },
  { value: 'batter_strikeouts', label: 'Strikeouts (batter)' },
  { value: 'batter_rbis', label: 'RBIs' },
  { value: 'batter_runs_scored', label: 'Runs Scored' },
  { value: 'batter_stolen_bases', label: 'Stolen Bases' },
  { value: 'batter_hits_runs_rbis', label: 'Hits + Runs + RBIs' },
  { value: 'pitcher_strikeouts', label: 'Strikeouts (P)' },
  { value: 'pitcher_earned_runs', label: 'Earned Runs (P)' },
  { value: 'pitcher_hits_allowed', label: 'Hits Allowed (P)' },
  { value: 'pitcher_walks', label: 'Walks Allowed (P)' },
  { value: 'pitcher_outs', label: 'Outs Recorded (P)' },
  { value: 'pitcher_record_a_win', label: 'To Record a Win (P)' },
];

// Match NFL_MARKET_STAT in backend/app/data/nfl.py exactly -- these keys are
// unprefixed (get_props.py already strips "player_" before writing NFL_Props
// .parquet), unlike MLB's batter_* markets above. Longest-play, 1st/last TD,
// defensive and kicking markets are left out -- none of that data exists in
// the pipeline (confirmed by direct inspection of player_box_stats.parquet).
const NFL_MARKETS: MarketOption[] = [
  { value: 'pass_yds', label: 'Passing Yards' },
  { value: 'pass_tds', label: 'Passing TDs' },
  { value: 'pass_attempts', label: 'Pass Attempts' },
  { value: 'pass_completions', label: 'Completions' },
  { value: 'pass_interceptions', label: 'Interceptions Thrown' },
  { value: 'rush_yds', label: 'Rushing Yards' },
  { value: 'rush_attempts', label: 'Rush Attempts' },
  { value: 'rush_tds', label: 'Rushing TDs' },
  { value: 'receptions', label: 'Receptions' },
  { value: 'reception_yds', label: 'Receiving Yards' },
  { value: 'reception_tds', label: 'Receiving TDs' },
  { value: 'pass_rush_yds', label: 'Pass + Rush Yards' },
  { value: 'rush_reception_yds', label: 'Rush + Receiving Yards' },
  { value: 'pass_rush_reception_yds', label: 'Pass + Rush + Receiving Yards' },
  { value: 'anytime_td', label: 'Anytime TD' },
];

// Two presets per sport, same "X%+ · market" / "odds or better · market"
// shape the mockup uses. Not specified beyond "2 per sport" -- these
// particular markets/thresholds are this build's own choice.
const SPORTS: Record<Sport, SportConfig> = {
  mlb: {
    label: 'MLB',
    fetcher: getMLBHitRateSheet,
    recentGames: 10,
    seasonLabel: 'Season (2026)',
    markets: MLB_MARKETS,
    presets: [
      { label: '70%+ · Pitcher Strikeouts', market: 'pitcher_strikeouts', minHitRate: 70, minOdds: -100000 },
      { label: '-150 or better · Total Bases', market: 'batter_total_bases', minHitRate: 0, minOdds: -150 },
    ],
  },
  nfl: {
    label: 'NFL',
    fetcher: getNFLHitRateSheet,
    recentGames: 5,
    seasonLabel: 'Season (2026)',
    markets: NFL_MARKETS,
    presets: [
      { label: '70%+ · Passing Yards', market: 'pass_yds', minHitRate: 70, minOdds: -100000 },
      { label: '-200 or better · Receptions', market: 'receptions', minHitRate: 0, minOdds: -200 },
    ],
  },
};

// Traffic-light thresholds, exactly matching the approved mockup's
// levelColor() and this app's theme tokens (theme.accent === '#1d9e75',
// theme.warningText === '#e8a33d', theme.dataRed === '#f4573f').
function levelColor(pct: number): string {
  if (pct >= 70) return theme.accent;
  if (pct >= 50) return theme.warningText;
  return theme.dataRed;
}

function formatOdds(n: number): string {
  return n > 0 ? `+${n}` : String(n);
}

function lineLabel(line: number | string): string {
  return typeof line === 'string' ? line : `O ${line}`;
}

function marketLabel(sport: Sport, market: string): string {
  return SPORTS[sport].markets.find((m) => m.value === market)?.label ?? market.replace(/_/g, ' ');
}

// Debounces the player search box so every keystroke doesn't re-fetch --
// the sheet is a bulk per-market scan, not a lookup on an already-loaded
// player list, so each change is a real network round trip.
function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

const selectStyle = { ...fieldStyle, marginBottom: 0, cursor: 'pointer' } as const;
const inputFieldStyle = { ...fieldStyle, marginBottom: 0 } as const;

export default function HitRateSheet() {
  const isMobile = useIsMobile();

  const [sport, setSport] = useState<Sport>('mlb');
  const [market, setMarket] = useState<string>('all');
  const [minHitRateStr, setMinHitRateStr] = useState('');
  const [minOddsStr, setMinOddsStr] = useState('');
  const [period, setPeriod] = useState<Period>('recent');
  const [playerQuery, setPlayerQuery] = useState('');
  const [enabledBooks, setEnabledBooks] = useState<Record<BookKey, boolean>>({
    draftkings: true, fanduel: true, betmgm: true, williamhill_us: true,
  });
  const [sortBy, setSortBy] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const [allBooksRows, setAllBooksRows] = useState<HitRateRow[]>([]);
  const [checkedRows, setCheckedRows] = useState<HitRateRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const cfg = SPORTS[sport];
  const minHitRate = minHitRateStr === '' ? 0 : Number(minHitRateStr);
  const minOdds = minOddsStr === '' ? -100000 : Number(minOddsStr);
  const playerDebounced = useDebounced(playerQuery, 300);
  const checkedBooksCsv = BOOK_KEYS.filter((b) => enabledBooks[b]).join(',');

  // Server does the market/player/period bulk scan; min-hit-rate, min-odds
  // and sorting are applied client-side below (min_pct=0 here on purpose),
  // matching the mockup's own "fetch once, filter reactively" feel and
  // meaning only market/player/period/books changes need a round trip.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    const base = { market: market === 'all' ? undefined : market, player: playerDebounced || undefined, period };
    Promise.all([
      cfg.fetcher({ ...base, min_pct: 0, min_odds: -100000, books: BOOK_KEYS.join(',') }),
      cfg.fetcher({ ...base, min_pct: 0, min_odds: -100000, books: checkedBooksCsv || 'none' }),
    ])
      .then(([allRes, checkedRes]) => {
        if (cancelled) return;
        setAllBooksRows(allRes.data);
        setCheckedRows(checkedRes.data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.response?.data?.detail || 'Failed to load the hit rate sheet.');
        setAllBooksRows([]);
        setCheckedRows([]);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sport, market, playerDebounced, period, checkedBooksCsv]);

  const effectiveSortBy: SortKey = sortBy ?? period;

  const rows = useMemo(() => {
    const filtered = checkedRows.filter((r) => {
      const pct = period === 'season' ? r.season_pct : r.recent_pct;
      return pct >= minHitRate && r.best_odds >= minOdds;
    });
    const sorted = [...filtered].sort((a, b) => {
      const av = effectiveSortBy === 'season' ? a.season_pct : a.recent_pct;
      const bv = effectiveSortBy === 'season' ? b.season_pct : b.recent_pct;
      return sortDir === 'desc' ? bv - av : av - bv;
    });
    return sorted;
  }, [checkedRows, minHitRate, minOdds, period, effectiveSortBy, sortDir]);

  // Rows that exist somewhere among ALL four books but vanished once
  // narrowed to just the checked ones -- i.e. "no checked book prices this
  // line at all", same concept as the mockup's hiddenByBooks (computed
  // before the min-hit-rate/min-odds cuts, which is why this compares the
  // two NO-THRESHOLD fetches rather than `rows` above).
  const hiddenByBooks = Math.max(0, allBooksRows.length - checkedRows.length);

  const toggleBook = (b: BookKey) => setEnabledBooks((prev) => ({ ...prev, [b]: !prev[b] }));

  const applyPreset = (p: Preset) => {
    setMarket(p.market);
    setMinHitRateStr(p.minHitRate === 0 ? '' : String(p.minHitRate));
    setMinOddsStr(p.minOdds <= -100000 ? '' : String(p.minOdds));
  };

  const clearFilters = () => {
    setMarket('all');
    setMinHitRateStr('');
    setMinOddsStr('');
    setPlayerQuery('');
    setEnabledBooks({ draftkings: true, fanduel: true, betmgm: true, williamhill_us: true });
    setSortBy(null);
    setSortDir('desc');
  };

  const onSort = (key: SortKey) => {
    setSortBy(key);
    setSortDir((prevDir) => (sortBy === key && prevDir === 'desc' ? 'asc' : 'desc'));
  };

  const headerStyle = (key: SortKey): React.CSSProperties => ({
    background: 'transparent', border: 'none', padding: 0, margin: 0,
    fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5, fontFamily: 'inherit',
    textAlign: 'left', cursor: 'pointer',
    color: sortBy === key ? theme.textPrimary : theme.textSecondary,
    fontWeight: sortBy === key ? 700 : 600,
  });

  const headerArrow = (key: SortKey) => (sortBy === key ? (sortDir === 'desc' ? ' ▼' : ' ▲') : '');

  return (
    <div style={{ padding: isMobile ? 16 : 32, maxWidth: 1400, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 56px)' }}>
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ color: theme.textPrimary, fontSize: 22, marginBottom: 4 }}>Hit Rate Sheet</h1>
        <p style={{ color: theme.textSecondary, fontSize: 13, margin: 0 }}>
          Filter every tracked prop by player, market, minimum hit rate and odds to see who actually clears your bar.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(Object.keys(SPORTS) as Sport[]).map((key) => (
          <button
            key={key}
            onClick={() => { setSport(key); setMarket('all'); setMinHitRateStr(''); setMinOddsStr(''); setPlayerQuery(''); setSortBy(null); setSortDir('desc'); }}
            style={{
              padding: '8px 22px', borderRadius: 6, border: `1px solid ${theme.border}`,
              background: sport === key ? theme.accent : 'transparent',
              color: sport === key ? theme.bgPage : theme.textSecondary,
              fontSize: 13, fontWeight: 700, cursor: 'pointer',
            }}
          >
            {SPORTS[key].label}
          </button>
        ))}
      </div>

      <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={fieldLabelStyle}>Player</label>
            <input
              type="text"
              placeholder="Search a name..."
              value={playerQuery}
              onChange={(e) => setPlayerQuery(e.target.value)}
              style={{ ...inputFieldStyle, width: 190 }}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={fieldLabelStyle}>Market</label>
            <select value={market} onChange={(e) => setMarket(e.target.value)} style={{ ...selectStyle, width: 200 }}>
              <option value="all">All Markets</option>
              {cfg.markets.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={fieldLabelStyle}>Min Hit Rate %</label>
            <input
              type="number" min={0} max={100} placeholder="e.g. 70"
              value={minHitRateStr}
              onChange={(e) => setMinHitRateStr(e.target.value)}
              style={{ ...inputFieldStyle, width: 110 }}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={fieldLabelStyle}>Min Odds (or better)</label>
            <input
              type="number" placeholder="e.g. -300"
              value={minOddsStr}
              onChange={(e) => setMinOddsStr(e.target.value)}
              style={{ ...inputFieldStyle, width: 130 }}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={fieldLabelStyle}>Time Period</label>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <SegmentedToggle
                value={period}
                onChange={setPeriod}
                options={[{ value: 'season', label: 'Season' }, { value: 'recent', label: 'Recent' }]}
                size="sm"
              />
              <span style={{ fontSize: 12, color: theme.textSecondary, whiteSpace: 'nowrap' }}>
                {period === 'season' ? cfg.seasonLabel : `Last ${cfg.recentGames} Games`}
              </span>
            </div>
          </div>
          <button
            onClick={clearFilters}
            style={{ padding: '9px 14px', borderRadius: 6, border: `1px solid ${theme.border}`, background: 'transparent', color: theme.textSecondary, fontSize: 12, cursor: 'pointer', marginLeft: 'auto' }}
          >
            Clear filters
          </button>
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', borderTop: `1px solid ${theme.border}`, paddingTop: 12 }}>
          <span style={{ fontSize: 11, color: theme.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Books &middot; odds shown are the best price among the ones checked
          </span>
          {BOOK_KEYS.map((b) => {
            const on = enabledBooks[b];
            return (
              <button
                key={b}
                onClick={() => toggleBook(b)}
                style={{
                  padding: '6px 14px', borderRadius: 14, cursor: 'pointer', fontSize: 12, fontWeight: 600,
                  border: `1px ${on ? 'solid' : 'dashed'} ${on ? theme.accent : theme.textMuted}`,
                  background: on ? 'rgba(29,158,117,0.15)' : 'transparent',
                  color: on ? theme.accent : theme.textMuted,
                }}
              >
                {BOOK_LABELS[b]}
              </button>
            );
          })}
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11, color: theme.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5 }}>Quick presets</span>
          {cfg.presets.map((p) => (
            <button
              key={p.label}
              onClick={() => applyPreset(p)}
              style={{
                padding: '6px 12px', borderRadius: 14, border: `1px solid ${theme.accent}`,
                background: 'rgba(29,158,117,0.12)', color: theme.accent, fontSize: 12, fontWeight: 600, cursor: 'pointer',
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <OddsDisclaimer fetchedAt={latestFetchedAt(rows as any)} compact={isMobile} />

      {loading && <LoadingSpinner />}

      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!loading && !error && rows.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 15, marginTop: 60 }}>
          No props match the current filters.
        </div>
      )}

      {!loading && !error && rows.length > 0 && isMobile && (
        <div>
          {rows.map((r, i) => (
            <StatCard
              key={`${r.player}-${r.market}-${r.line}-${i}`}
              title={<span style={{ fontWeight: 700 }}>{r.player}</span>}
              titleAside={r.team ?? undefined}
              meta={[marketLabel(sport, r.market), lineLabel(r.line), r.opponent ?? undefined]}
              value={formatOdds(r.best_odds)}
              valueLabel={BOOK_LABELS[r.best_book as BookKey] ?? r.best_book}
              metaSecondary={[
                <span style={{ color: period === 'season' ? levelColor(r.season_pct) : theme.textSecondary, fontWeight: period === 'season' ? 700 : 500 }}>
                  Season {r.season_pct}% ({r.season_sample})
                </span>,
                <span style={{ color: period === 'recent' ? levelColor(r.recent_pct) : theme.textSecondary, fontWeight: period === 'recent' ? 700 : 500 }}>
                  Recent {r.recent_pct}% ({r.recent_sample})
                </span>,
              ]}
            />
          ))}
        </div>
      )}

      {!loading && !error && rows.length > 0 && !isMobile && (
        <ScrollTable>
          <div style={{ border: `1px solid ${theme.border}`, borderRadius: 8, overflow: 'hidden', minWidth: 980 }}>
            <div style={{
              display: 'grid', gridTemplateColumns: '220px 160px 220px 100px 150px 150px 150px', gap: 16,
              background: theme.bgCardHover, padding: '10px 16px', fontSize: 11, color: theme.textSecondary,
              textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600,
            }}>
              <div style={stickyColStyle(theme.bgCardHover)}>Player</div>
              <div>Matchup</div>
              <div>Market</div>
              <div>Line</div>
              <div>Best Odds</div>
              <button onClick={() => onSort('season')} style={headerStyle('season')}>Season{headerArrow('season')}</button>
              <button onClick={() => onSort('recent')} style={headerStyle('recent')}>Recent{headerArrow('recent')}</button>
            </div>
            {rows.map((r, i) => {
              const bg = i % 2 === 0 ? theme.bgCard : theme.bgCardHover;
              return (
                <div
                  key={`${r.player}-${r.market}-${r.line}-${i}`}
                  style={{
                    display: 'grid', gridTemplateColumns: '220px 160px 220px 100px 150px 150px 150px', gap: 16,
                    padding: '10px 16px', background: bg, borderTop: `1px solid ${theme.border}`,
                    alignItems: 'center', fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  <div style={stickyColStyle(bg)}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary }}>{r.player}</div>
                    <div style={{ fontSize: 11, color: theme.textSecondary }}>{r.team ?? '—'}</div>
                  </div>
                  <div style={{ fontSize: 12, color: theme.textSecondary }}>{r.opponent ?? '—'}</div>
                  <div style={{ fontSize: 13, color: theme.textPrimary }}>{marketLabel(sport, r.market)}</div>
                  <div style={{ fontSize: 13, color: theme.textPrimary }}>{lineLabel(r.line)}</div>
                  <div style={{ fontSize: 13, color: theme.textPrimary }}>
                    {formatOdds(r.best_odds)} <span style={{ color: theme.textMuted, fontSize: 11 }}>{BOOK_LABELS[r.best_book as BookKey] ?? r.best_book}</span>
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: period === 'season' ? 700 : 500, color: period === 'season' ? levelColor(r.season_pct) : theme.textSecondary }}>
                      {r.season_pct}%
                    </div>
                    <div style={{ fontSize: 10, color: theme.textMuted }}>({r.season_sample})</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: period === 'recent' ? 700 : 500, color: period === 'recent' ? levelColor(r.recent_pct) : theme.textSecondary }}>
                      {r.recent_pct}%
                    </div>
                    <div style={{ fontSize: 10, color: theme.textMuted }}>({r.recent_sample})</div>
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollTable>
      )}

      {!loading && !error && (
        <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 10 }}>
          {rows.length} of {allBooksRows.length} props match your filters, sorted by {effectiveSortBy} hit rate ({sortDir === 'desc' ? 'highest first' : 'lowest first'}) — click a Season or Recent column header to change it
          {hiddenByBooks > 0 && (
            <span style={{ color: theme.warningText }}> &middot; {hiddenByBooks} more not offered by your checked books</span>
          )}
        </div>
      )}
    </div>
  );
}
