import React, { useState, useEffect, useMemo } from 'react';
import { getMLBProps } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';

// ── Constants ─────────────────────────────────────────────────────────────────

const META_COLS = new Set([
  'line_id', 'player', 'player_name', 'name', 'team', 'market',
  'prop_type', 'stat', 'line', 'line_value', 'over_under',
  'bet_type', 'category', 'description', 'mlb_team_long',
  'date', 'game_date', 'home_team', 'away_team', 'commence_time', 'sport',
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

// ── Styles ────────────────────────────────────────────────────────────────────

const labelStyle: React.CSSProperties = {
  color: '#aaa',
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
  border: '1px solid #3a3a5c',
  background: '#2a2a4a',
  color: 'white',
  marginBottom: 14,
  boxSizing: 'border-box',
  cursor: 'pointer',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '7px 10px',
  fontSize: 12,
  borderRadius: 4,
  border: '1px solid #3a3a5c',
  background: '#2a2a4a',
  color: 'white',
  boxSizing: 'border-box',
  outline: 'none',
};

const dividerStyle: React.CSSProperties = {
  borderBottom: '1px solid #2a2a4a',
  margin: '14px 0',
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function MLBProps() {
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
  // Load all props on mount
  useEffect(() => {
    setLoading(true);
    getMLBProps({})
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

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 60px)', overflow: 'hidden', background: '#f5f6fa' }}>

      {/* ── Left Sidebar ── */}
      <div style={{
        width: 210,
        flexShrink: 0,
        background: '#1a1a2e',
        padding: '18px 14px',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{ color: 'white', fontWeight: 700, fontSize: 15, marginBottom: 16 }}>MLB Props</div>

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
              background: 'white', border: '1px solid #ddd', borderRadius: 4,
              maxHeight: 200, overflowY: 'auto', boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
            }}>
              {uniquePlayers
                .filter(p => p.toLowerCase().includes(playerSearch.toLowerCase()))
                .slice(0, 60)
                .map(p => (
                  <div
                    key={p}
                    onMouseDown={() => { setSelectedPlayer(p); setPlayerSearch(p); setShowPlayerDrop(false); }}
                    style={{ padding: '7px 10px', cursor: 'pointer', fontSize: 12, color: '#333' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#eef2ff')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'white')}
                  >{p}</div>
                ))
              }
              {uniquePlayers.filter(p => p.toLowerCase().includes(playerSearch.toLowerCase())).length === 0 && (
                <div style={{ padding: '7px 10px', color: '#999', fontSize: 12 }}>No players found</div>
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
                background: 'none', border: 'none', color: '#4a9eff', fontSize: 10,
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
                style={{ accentColor: '#4a9eff', cursor: 'pointer' }}
              />
              <span style={{ color: selectedBooks.has(book) ? '#e0e0e0' : '#666', fontSize: 12 }}>
                {book.replace(/_/g, ' ')}
              </span>
            </label>
          ))}
        </div>
      </div>

      {/* ── Main Content ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
        {loading && <LoadingSpinner />}

        {error && (
          <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b', marginBottom: 16 }}>
            {error}
          </div>
        )}

        {!loading && displayProps.length > 0 && (
          <>
            <div style={{ fontSize: 12, color: '#999', marginBottom: 10 }}>
              {displayProps.length} line{displayProps.length !== 1 ? 's' : ''}
              {filteredProps.length !== displayProps.length && ` (${filteredProps.length} before min-odds filter)`}
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: '#1a1a2e', color: 'white' }}>
                    <th style={{
                      padding: '10px 16px', textAlign: 'left', whiteSpace: 'nowrap',
                      minWidth: 260, position: 'sticky', left: 0, background: '#1a1a2e', zIndex: 2,
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
                      <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa', borderBottom: '1px solid #eee' }}>
                        <td style={{
                          padding: '8px 16px', whiteSpace: 'nowrap', fontWeight: 500, fontSize: 13,
                          position: 'sticky', left: 0,
                          background: i % 2 === 0 ? '#fff' : '#fafafa', zIndex: 1,
                          borderRight: '1px solid #e8e8e8',
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
                              color: isBest ? '#155724' : passes ? '#222' : '#ccc',
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
          </>
        )}

        {!loading && !error && displayProps.length === 0 && allProps.length > 0 && (
          <div style={{ color: '#999', textAlign: 'center', fontSize: 15, marginTop: 80 }}>
            No props match the current filters.
          </div>
        )}

        {!loading && !error && allProps.length === 0 && (
          <div style={{ color: '#999', textAlign: 'center', fontSize: 15, marginTop: 80 }}>
            No MLB props data available.
          </div>
        )}
      </div>
    </div>
  );
}
