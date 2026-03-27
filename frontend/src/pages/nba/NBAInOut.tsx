import React, { useState, useEffect } from 'react';
import { getNBAPlayers, getNBAInOut } from '../../api/nba';
import LoadingSpinner from '../../components/LoadingSpinner';

interface InOutRow {
  player: string;
  pts_with: number;
  pts_without: number;
  pts_diff: number;
  reb_with: number;
  reb_without: number;
  reb_diff: number;
  ast_with: number;
  ast_without: number;
  ast_diff: number;
}

function DiffCell({ value }: { value: number }) {
  let color = '#333';
  if (value > 0.5) color = '#27ae60';
  else if (value < -0.5) color = '#e74c3c';
  return (
    <td style={{ padding: '8px 14px', textAlign: 'center', fontWeight: 700, color }}>
      {value > 0 ? '+' : ''}{value.toFixed(1)}
    </td>
  );
}

export default function NBAInOut() {
  const [players, setPlayers] = useState<string[]>([]);
  const [playerA, setPlayerA] = useState('');
  const [excludeA, setExcludeA] = useState('');
  const [excludeB, setExcludeB] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState<InOutRow[]>([]);

  useEffect(() => {
    getNBAPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
  }, []);

  const analyze = async () => {
    if (!playerA) return;
    setLoading(true);
    setError('');
    setResults([]);
    try {
      const exclude = [excludeA, excludeB].filter(Boolean);
      const res = await getNBAInOut(playerA, exclude);
      setResults(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch in/out data.');
    } finally {
      setLoading(false);
    }
  };

  const selectStyle: React.CSSProperties = {
    padding: '8px 12px',
    border: '1px solid #ddd',
    borderRadius: 4,
    fontSize: 14,
    minWidth: 200,
  };

  return (
    <div style={{ padding: 24, overflowY: 'auto', minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 24, color: '#1a1a2e' }}>
        In/Out Analysis{playerA ? ` — ${playerA}` : ''}
      </h2>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 28 }}>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
            Anchor Player
          </label>
          <select style={selectStyle} value={playerA} onChange={(e) => setPlayerA(e.target.value)}>
            <option value="">-- Select Player --</option>
            {players.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
            Exclude Player A
          </label>
          <select style={selectStyle} value={excludeA} onChange={(e) => setExcludeA(e.target.value)}>
            <option value="">-- None --</option>
            {players.filter((p) => p !== playerA && p !== excludeB).map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
            Exclude Player B
          </label>
          <select style={selectStyle} value={excludeB} onChange={(e) => setExcludeB(e.target.value)}>
            <option value="">-- None --</option>
            {players.filter((p) => p !== playerA && p !== excludeA).map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <button
          onClick={analyze}
          disabled={!playerA || loading}
          style={{
            padding: '9px 24px',
            background: '#1a1a2e',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            fontWeight: 700,
            fontSize: 14,
            cursor: playerA && !loading ? 'pointer' : 'not-allowed',
            opacity: playerA && !loading ? 1 : 0.6,
          }}
        >
          Analyze
        </button>
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b', marginBottom: 16 }}>
          {error}
        </div>
      )}
      {!loading && results.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14, minWidth: 700 }}>
            <thead>
              <tr style={{ background: '#1a1a2e', color: 'white' }}>
                <th style={{ padding: '10px 14px', textAlign: 'left' }}>Player</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>PTS With</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>PTS W/O</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>PTS Diff</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>REB With</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>REB W/O</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>REB Diff</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>AST With</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>AST W/O</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>AST Diff</th>
              </tr>
            </thead>
            <tbody>
              {results.map((row, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #eee', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                  <td style={{ padding: '8px 14px', fontWeight: 600 }}>{row.player}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'center' }}>{row.pts_with?.toFixed(1)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'center' }}>{row.pts_without?.toFixed(1)}</td>
                  <DiffCell value={row.pts_diff} />
                  <td style={{ padding: '8px 14px', textAlign: 'center' }}>{row.reb_with?.toFixed(1)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'center' }}>{row.reb_without?.toFixed(1)}</td>
                  <DiffCell value={row.reb_diff} />
                  <td style={{ padding: '8px 14px', textAlign: 'center' }}>{row.ast_with?.toFixed(1)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'center' }}>{row.ast_without?.toFixed(1)}</td>
                  <DiffCell value={row.ast_diff} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!loading && !error && results.length === 0 && (
        <div style={{ color: '#999', textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          Select an anchor player and click "Analyze" to view in/out splits.
        </div>
      )}
    </div>
  );
}
