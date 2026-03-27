import React, { useState, useEffect } from 'react';
import { getMLBPitchers, getMLBMatchup } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';

interface MatchupData {
  season_stats?: Record<string, any>[];
  game_logs?: Record<string, any>[];
  hitters?: Record<string, any>[];
  percentile_rankings?: Record<string, any>;
  [key: string]: any;
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  marginBottom: 4,
  fontWeight: 600,
  fontSize: 13,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: 8,
  marginBottom: 16,
  border: '1px solid #ddd',
  borderRadius: 4,
  boxSizing: 'border-box',
};

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
  padding: '12px 20px',
  fontWeight: 700,
  fontSize: 15,
};

export default function MLBMatchup() {
  const [pitchers, setPitchers] = useState<string[]>([]);
  const [selectedPitcher, setSelectedPitcher] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [matchupData, setMatchupData] = useState<MatchupData | null>(null);

  useEffect(() => {
    getMLBPitchers()
      .then((res) => setPitchers(res.data))
      .catch(() => setPitchers([]));
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

  const handlePitcherChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const p = e.target.value;
    setSelectedPitcher(p);
    if (p) fetchMatchup(p);
  };

  const seasonStats = matchupData?.season_stats?.[0];
  const gameLogs = matchupData?.game_logs ?? [];
  const hitters = matchupData?.hitters ?? [];
  const percentiles = matchupData?.percentile_rankings;

  const gameLogColumns = gameLogs.length > 0 ? Object.keys(gameLogs[0]) : [];
  const hitterColumns = hitters.length > 0
    ? ['mlb_name', 'Batting Order', 'gamePosition', 'Bats'].filter((c) => c in hitters[0])
    : [];

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 60px)' }}>
      {/* Sidebar */}
      <div style={{ width: 280, background: '#f8f9fa', padding: 20, height: 'calc(100vh - 60px)', overflowY: 'auto', flexShrink: 0 }}>
        <h3 style={{ marginTop: 0, marginBottom: 20, fontSize: 16, fontWeight: 700, color: '#1a1a2e' }}>MLB Matchup</h3>
        <label style={labelStyle}>Pitcher</label>
        <select style={inputStyle} value={selectedPitcher} onChange={handlePitcherChange}>
          <option value="">-- Select Pitcher --</option>
          {pitchers.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, padding: 24, overflowY: 'auto' }}>
        {loading && <LoadingSpinner />}
        {error && (
          <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b', marginBottom: 16 }}>
            {error}
          </div>
        )}

        {!loading && matchupData && (
          <>
            <h2 style={{ marginTop: 0, marginBottom: 20, color: '#1a1a2e' }}>{selectedPitcher}</h2>

            {/* Season Stats */}
            {seasonStats && (
              <div style={cardStyle}>
                <div style={cardHeaderStyle}>Season Stats</div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <tbody>
                    {Object.entries(seasonStats).map(([key, value], i) => (
                      <tr key={key} style={{ borderBottom: '1px solid #f0f0f0', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                        <td style={{ padding: '8px 16px', fontWeight: 600, color: '#555', textTransform: 'capitalize' }}>
                          {key.replace(/_/g, ' ')}
                        </td>
                        <td style={{ padding: '8px 16px', textAlign: 'right', fontWeight: 700, color: '#1a1a2e' }}>
                          {String(value ?? '—')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Recent Game Logs */}
            {gameLogs.length > 0 && (
              <div style={cardStyle}>
                <div style={cardHeaderStyle}>Recent Game Logs</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#f0f0f0' }}>
                        {gameLogColumns.map((col) => (
                          <th key={col} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#333', whiteSpace: 'nowrap' }}>
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {gameLogs.map((row, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid #f0f0f0', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                          {gameLogColumns.map((col) => (
                            <td key={col} style={{ padding: '7px 12px', whiteSpace: 'nowrap' }}>
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

            {/* Opposing Hitters */}
            {hitters.length > 0 && (
              <div style={cardStyle}>
                <div style={cardHeaderStyle}>Opposing Hitters</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#f0f0f0' }}>
                        {hitterColumns.length > 0
                          ? hitterColumns.map((col) => (
                              <th key={col} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#333' }}>
                                {col}
                              </th>
                            ))
                          : Object.keys(hitters[0]).map((col) => (
                              <th key={col} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#333' }}>
                                {col}
                              </th>
                            ))
                        }
                      </tr>
                    </thead>
                    <tbody>
                      {hitters.map((row, i) => {
                        const cols = hitterColumns.length > 0 ? hitterColumns : Object.keys(row);
                        return (
                          <tr key={i} style={{ borderBottom: '1px solid #f0f0f0', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                            {cols.map((col) => (
                              <td key={col} style={{ padding: '7px 12px' }}>
                                {String(row[col] ?? '—')}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Percentile Rankings */}
            {percentiles && Object.keys(percentiles).length > 0 && (
              <div style={cardStyle}>
                <div style={cardHeaderStyle}>Percentile Rankings</div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <tbody>
                    {Object.entries(percentiles).map(([key, value], i) => (
                      <tr key={key} style={{ borderBottom: '1px solid #f0f0f0', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                        <td style={{ padding: '8px 16px', fontWeight: 600, color: '#555', textTransform: 'capitalize' }}>
                          {key.replace(/_/g, ' ')}
                        </td>
                        <td style={{ padding: '8px 16px', textAlign: 'right', fontWeight: 700, color: '#1a1a2e' }}>
                          {String(value ?? '—')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {!loading && !error && !matchupData && (
          <div style={{ color: '#999', textAlign: 'center', fontSize: 16, marginTop: 60 }}>
            Select a pitcher to load matchup data.
          </div>
        )}
      </div>
    </div>
  );
}
