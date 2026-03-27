import React, { useState } from 'react';
import { getMLBProps } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';

export default function MLBProps() {
  const [teamFilter, setTeamFilter] = useState('');
  const [playerFilter, setPlayerFilter] = useState('');
  const [marketFilter, setMarketFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [props, setProps] = useState<Record<string, any>[]>([]);

  const search = async () => {
    setLoading(true);
    setError('');
    setProps([]);
    try {
      const params: Record<string, any> = {};
      if (teamFilter) params.team = teamFilter;
      if (playerFilter) params.player = playerFilter;
      if (marketFilter) params.market = marketFilter;
      const res = await getMLBProps(params);
      setProps(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch MLB props.');
    } finally {
      setLoading(false);
    }
  };

  const columns = props.length > 0 ? Object.keys(props[0]) : [];

  const inputStyle: React.CSSProperties = {
    padding: '8px 12px',
    border: '1px solid #ddd',
    borderRadius: 4,
    fontSize: 14,
    minWidth: 160,
  };

  return (
    <div style={{ padding: 24, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 24, color: '#1a1a2e' }}>MLB Props</h2>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 28 }}>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Team</label>
          <input
            type="text"
            style={inputStyle}
            placeholder="e.g. Yankees"
            value={teamFilter}
            onChange={(e) => setTeamFilter(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Player</label>
          <input
            type="text"
            style={inputStyle}
            placeholder="e.g. Aaron Judge"
            value={playerFilter}
            onChange={(e) => setPlayerFilter(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Market</label>
          <input
            type="text"
            style={inputStyle}
            placeholder="e.g. hits"
            value={marketFilter}
            onChange={(e) => setMarketFilter(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
        </div>
        <button
          onClick={search}
          disabled={loading}
          style={{
            padding: '9px 24px',
            background: '#1a1a2e',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            fontWeight: 700,
            fontSize: 14,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.6 : 1,
          }}
        >
          Search
        </button>
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b', marginBottom: 16 }}>
          {error}
        </div>
      )}
      {!loading && props.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#1a1a2e', color: 'white' }}>
                {columns.map((col) => (
                  <th key={col} style={{ padding: '10px 14px', textAlign: 'left', whiteSpace: 'nowrap' }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {props.map((row, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #eee', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                  {columns.map((col) => (
                    <td key={col} style={{ padding: '8px 14px', whiteSpace: 'nowrap' }}>
                      {String(row[col] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 10, fontSize: 13, color: '#999' }}>{props.length} result{props.length !== 1 ? 's' : ''}</div>
        </div>
      )}
      {!loading && !error && props.length === 0 && (
        <div style={{ color: '#999', textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          Use the filters above and click "Search" to find MLB props.
        </div>
      )}
    </div>
  );
}
