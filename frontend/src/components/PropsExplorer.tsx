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

function parseOdds(val: any): number | null {
  if (val === '' || val === null || val === undefined) return null;
  const n = typeof val === 'number' ? val : parseFloat(String(val));
  return isNaN(n) ? null : n;
}

function formatOdds(n: number): string {
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

function prettyBook(book: string): string {
  return BOOK_NAME[book.toLowerCase()] ?? book.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
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
}

/** Line-shopping grid, shared by the MLB and NFL props pages.
 *
 *  Both sports produce the identical long-format schema from get_props.py and
 *  are pivoted by the same backend helper, so the only thing that differs is
 *  which endpoint to call. Forking this into two 600-line files would mean
 *  every future fix landing once and being forgotten the other time. */
export default function PropsExplorer({ fetcher }: PropsExplorerProps) {
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
  const uniquePlayers = useMemo(() => {
    if (!colRoles.player) return [];
    return [...new Set(allProps.map(r => String(r[colRoles.player] || '')).filter(Boolean))].sort();
  }, [allProps, colRoles.player]);

  const uniqueMarkets = useMemo(() => {
    if (!colRoles.market) return [];
    return [...new Set(allProps.map(r => String(r[colRoles.market] || '')).filter(Boolean))].sort();
  }, [allProps, colRoles.market]);

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
            {uniqueMarkets.map(m => <option key={m} value={m}>{m}</option>)}
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
          <div style={{ color: 'white', fontWeight: 700, fontSize: 15, marginBottom: 16 }}>MLB Props</div>
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
                {displayProps.map((row, i) => {
                  const priced = activeCols
                    .map((b) => ({ book: b, odds: parseOdds(row[b]) }))
                    .filter((x): x is { book: string; odds: number } =>
                      x.odds !== null && (minOdds === null || x.odds >= minOdds))
                    .sort((a, b) => b.odds - a.odds);
                  const best = priced[0] ?? null;
                  const rest = priced.slice(1);

                  const player = colRoles.player ? String(row[colRoles.player] ?? '') : '';
                  const market = colRoles.market ? String(row[colRoles.market] ?? '') : '';
                  const line = colRoles.line ? String(row[colRoles.line] ?? '') : '';
                  const descriptor = [market, line].filter(Boolean).join(' ');

                  return (
                    <StatCard
                      key={i}
                      title={<span style={{ fontWeight: 700 }}>{player || String(row['line_id'] ?? '—')}</span>}
                      titleAside={colRoles.player && row['team'] ? String(row['team']) : undefined}
                      value={best ? formatOdds(Math.round(best.odds)) : '—'}
                      valueColor={best ? theme.dataBlue : theme.textMuted}
                      valueLabel={best ? prettyBook(best.book) : 'no price'}
                      meta={descriptor ? [descriptor] : undefined}
                      metaSecondary={rest.length > 0
                        ? rest.map((p) => <>{shortBook(p.book)} {formatOdds(Math.round(p.odds))}</>)
                        : undefined}
                    />
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
                            <div style={{ fontWeight: 700 }}>{player || String(row['line_id'] ?? '—')}</div>
                            {(market || line) && (
                              <div style={{ fontSize: 10, color: theme.textMuted }}>
                                {[market, line].filter(Boolean).join(' ')}
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
                          {String(row['line_id'] ?? '—')}
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
            No props match the current filters.
          </div>
        )}

        {!loading && !error && allProps.length === 0 && (
          <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 15, marginTop: 80 }}>
            No MLB props data available.
          </div>
        )}
      </div>
    </div>
  );
}
