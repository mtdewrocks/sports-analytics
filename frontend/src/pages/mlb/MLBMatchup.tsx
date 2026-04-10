import React, { useState, useEffect } from 'react';
import { getMLBPitchers, getMLBMatchup } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';

const IMAGE_BASE = 'https://github.com/mtdewrocks/sports-analytics/raw/main/backend/data/mlb/pitcher_images';

interface MatchupData {
  season_stats?: Record<string, any>;
  game_logs?: Record<string, any>[];
  splits?: Record<string, any>[];
  percentiles?: { Statistic: string; Percentile: number }[];
  opposing_hitters?: Record<string, any>[];
  [key: string]: any;
}

// ── Color helpers ──────────────────────────────────────────────────────────
function avgColor(v: number) {
  if (v > 0.300) return { bg: '#1a7a3a', fg: 'white' };
  if (v >= 0.275) return { bg: '#1565c0', fg: 'white' };
  if (v >= 0.250) return { bg: '#1e88e5', fg: 'white' };
  if (v >= 0.200) return { bg: '#e57373', fg: 'white' };
  return { bg: '#b71c1c', fg: 'white' };
}
function wobaColor(v: number) {
  if (v > 0.400) return { bg: '#1a7a3a', fg: 'white' };
  if (v >= 0.360) return { bg: '#1565c0', fg: 'white' };
  if (v >= 0.325) return { bg: '#1e88e5', fg: 'white' };
  if (v >= 0.275) return { bg: '#e57373', fg: 'white' };
  return { bg: '#b71c1c', fg: 'white' };
}
function isoColor(v: number) {
  if (v > 0.275) return { bg: '#1a7a3a', fg: 'white' };
  if (v >= 0.225) return { bg: '#1565c0', fg: 'white' };
  if (v >= 0.175) return { bg: '#1e88e5', fg: 'white' };
  if (v >= 0.125) return { bg: '#e57373', fg: 'white' };
  return { bg: '#b71c1c', fg: 'white' };
}
function kpctColor(v: number) {
  if (v >= 25) return { bg: '#b71c1c', fg: 'white' };
  if (v >= 20) return { bg: '#e57373', fg: 'white' };
  if (v >= 15) return { bg: '#1e88e5', fg: 'white' };
  return { bg: '#1a7a3a', fg: 'white' };
}

function pctBarColor(pct: number) {
  if (pct >= 70) return '#2ecc71';
  if (pct >= 40) return '#f39c12';
  return '#e74c3c';
}

const SEASON_DISPLAY = ['Handedness', 'GS', 'W', 'L', 'ERA', 'IP', 'SO', 'K/IP', 'WHIP'];

const cardStyle: React.CSSProperties = {
  background: 'white',
  borderRadius: 8,
  boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
  marginBottom: 20,
  overflow: 'hidden',
};
const cardHeaderStyle: React.CSSProperties = {
  background: '#1a1a2e',
  color: 'white',
  padding: '10px 16px',
  fontWeight: 700,
  fontSize: 14,
  textAlign: 'center',
};
const thStyle: React.CSSProperties = {
  padding: '8px 12px',
  fontWeight: 600,
  color: '#333',
  whiteSpace: 'nowrap',
  background: '#f0f0f0',
  textAlign: 'center',
};
const tdStyle: React.CSSProperties = {
  padding: '7px 12px',
  textAlign: 'center',
  whiteSpace: 'nowrap',
  borderBottom: '1px solid #f0f0f0',
};

export default function MLBMatchup() {
  const [pitchers, setPitchers] = useState<string[]>([]);
  const [loadingPitchers, setLoadingPitchers] = useState(true);
  const [selectedPitcher, setSelectedPitcher] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [matchupData, setMatchupData] = useState<MatchupData | null>(null);

  useEffect(() => {
    setLoadingPitchers(true);
    getMLBPitchers()
      .then((res) => setPitchers(res.data))
      .catch(() => setPitchers([]))
      .finally(() => setLoadingPitchers(false));
  }, []);

  const fetchMatchup = async (pitcher: string) => {
    if (!pitcher) return;
    setLoading(true);
    setError('');
    setMatchupData(null);
    try {
      const res = await getMLBMatchup(pitcher);
      setMatchupData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch matchup data.');
    } finally {
      setLoading(false);
    }
  };

  const seasonStats = matchupData?.season_stats;
  const gameLogs = matchupData?.game_logs ?? [];
  const splits = matchupData?.splits ?? [];
  const percentiles = matchupData?.percentiles ?? [];
  const opposingHitters = matchupData?.opposing_hitters ?? [];

  const gameLogColumns = gameLogs.length > 0 ? Object.keys(gameLogs[0]) : [];
  const splitsColumns = splits.length > 0 ? Object.keys(splits[0]) : [];

  const seasonDisplay = seasonStats
    ? SEASON_DISPLAY.filter((k) => k in seasonStats).map((k) => ({ key: k, val: seasonStats[k] }))
    : [];

  const photoUrl = selectedPitcher
    ? `${IMAGE_BASE}/${encodeURIComponent(selectedPitcher)}.jpg`
    : '';

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 60px)', overflow: 'hidden', background: '#f5f6fa' }}>

      {/* ── Left Sidebar ── */}
      <div style={{
        width: 220,
        flexShrink: 0,
        background: '#1a1a2e',
        padding: '20px 14px',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
      }}>
        <div style={{ color: 'white', fontWeight: 700, fontSize: 15, marginBottom: 4 }}>MLB Matchup</div>
        <div>
          <div style={{ color: '#aaa', fontSize: 12, fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Pitcher</div>
          {loadingPitchers ? (
            <div style={{ color: '#aaa', fontSize: 12, padding: '8px 4px' }}>Loading pitchers…</div>
          ) : (
            <SearchDropdown
              players={pitchers}
              value={selectedPitcher}
              onSelect={(p) => { setSelectedPitcher(p); fetchMatchup(p); }}
              placeholder="Search pitcher..."
              inputStyle={{ padding: '7px 10px', fontSize: 13, width: '100%', boxSizing: 'border-box' }}
            />
          )}
        </div>
      </div>

      {/* ── Main Content ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>

        {/* ── Pitcher Photo + Season Stats ── */}
        {(selectedPitcher || seasonDisplay.length > 0) && (
          <div style={{ ...cardStyle, marginBottom: 20 }}>
            <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 20, padding: '16px 20px' }}>
              {selectedPitcher && (
                <img
                  src={photoUrl}
                  alt={selectedPitcher}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  style={{ width: 80, height: 80, borderRadius: '50%', objectFit: 'cover', border: '3px solid #e0e0e0', flexShrink: 0 }}
                />
              )}
              <div>
                {selectedPitcher && (
                  <div style={{ fontWeight: 700, fontSize: 18, color: '#1a1a2e', marginBottom: 10 }}>
                    {selectedPitcher}
                  </div>
                )}
                {seasonDisplay.length > 0 && (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#1a1a2e', color: 'white' }}>
                          {seasonDisplay.map(({ key }) => (
                            <th key={key} style={{ padding: '7px 14px', fontWeight: 600, whiteSpace: 'nowrap' }}>{key}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          {seasonDisplay.map(({ key, val }) => (
                            <td key={key} style={{ padding: '7px 14px', textAlign: 'center', fontWeight: 700, color: '#1a1a2e', whiteSpace: 'nowrap', borderTop: '1px solid #f0f0f0' }}>
                              {String(val ?? '—')}
                            </td>
                          ))}
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
                {loading && !seasonDisplay.length && (
                  <div style={{ color: '#888', fontSize: 13 }}>Loading...</div>
                )}
              </div>
            </div>
          </div>
        )}

        {loading && <LoadingSpinner />}
        {error && (
          <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b', marginBottom: 16 }}>
            {error}
          </div>
        )}

        {!loading && matchupData && (
          <>
            {/* ── Game Logs ── */}
            {gameLogs.length > 0 && (
              <div style={cardStyle}>
                <div style={cardHeaderStyle}>Recent Game Logs</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr>{gameLogColumns.map((col) => <th key={col} style={thStyle}>{col}</th>)}</tr>
                    </thead>
                    <tbody>
                      {gameLogs.map((row, i) => (
                        <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                          {gameLogColumns.map((col) => (
                            <td key={col} style={tdStyle}>{String(row[col] ?? '—')}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ── Splits + Percentiles side by side ── */}
            {(splits.length > 0 || percentiles.length > 0) && (
              <div style={{ display: 'flex', gap: 20, marginBottom: 20, flexWrap: 'wrap' }}>

                {splits.length > 0 && (
                  <div style={{ ...cardStyle, flex: 1, minWidth: 300, marginBottom: 0 }}>
                    <div style={cardHeaderStyle}>Splits (vs L / vs R) — 2025–2026</div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                        <thead>
                          <tr>
                            {splitsColumns.map((col) => (
                              <th key={col} style={thStyle}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {splits.map((row, i) => (
                            <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                              {splitsColumns.map((col) => (
                                <td key={col} style={{ ...tdStyle, fontWeight: col === 'Statistic' ? 600 : 400 }}>
                                  {String(row[col] ?? '—')}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {percentiles.length > 0 && (
                  <div style={{ ...cardStyle, flex: 1, minWidth: 300, marginBottom: 0 }}>
                    <div style={cardHeaderStyle}>2026 Percentile Rankings</div>
                    <div style={{ padding: '12px 16px' }}>
                      {percentiles.map((row, i) => {
                        const pct = Math.round(Number(row.Percentile));
                        const color = pctBarColor(pct);
                        return (
                          <div key={i} style={{ marginBottom: 10 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 3 }}>
                              <span style={{ fontWeight: 600, color: '#444' }}>{row.Statistic}</span>
                              <span style={{ fontWeight: 700, color }}>{pct}th</span>
                            </div>
                            <div style={{ background: '#eee', borderRadius: 4, height: 10, overflow: 'hidden' }}>
                              <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.4s ease' }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── Opposing Hitters ── */}
            {opposingHitters.length > 0 && (
              <div style={cardStyle}>
                <div style={cardHeaderStyle}>Opposing Hitters</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr>
                        {Object.keys(opposingHitters[0]).map((col) => (
                          <th key={col} style={thStyle}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {opposingHitters.map((row, i) => (
                        <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                          {Object.entries(row).map(([col, val]) => {
                            const num = parseFloat(String(val));
                            let bg = 'transparent', fg = 'inherit';
                            if (col === 'Average' && !isNaN(num)) { const c = avgColor(num); bg = c.bg; fg = c.fg; }
                            else if (col === 'wOBA' && !isNaN(num)) { const c = wobaColor(num); bg = c.bg; fg = c.fg; }
                            else if (col === 'ISO' && !isNaN(num)) { const c = isoColor(num); bg = c.bg; fg = c.fg; }
                            else if (col === 'K%' && !isNaN(num)) { const c = kpctColor(num); bg = c.bg; fg = c.fg; }
                            // Display batting order as integer (Excel stores as float)
                            const displayVal = col === 'Batting Order' && !isNaN(num) && val !== ''
                              ? String(Math.round(num))
                              : String(val ?? '—');
                            return (
                              <td key={col} style={{ ...tdStyle, background: bg, color: fg, fontWeight: bg !== 'transparent' ? 700 : 400 }}>
                                {displayVal}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}

        {!loading && !error && !matchupData && (
          <div style={{ color: '#999', textAlign: 'center', fontSize: 16, marginTop: 80 }}>
            Select a pitcher to load matchup data.
          </div>
        )}
      </div>
    </div>
  );
}
