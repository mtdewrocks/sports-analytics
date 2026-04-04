import { useState, useEffect } from 'react';
import { getNBAPlayers, getNBATeammates, getNBAInOut } from '../../api/nba';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';

interface InOutData {
  player: string;
  exclude: string[];
  games_with: number;
  games_without: number;
  with: Record<string, number | null>;
  without: Record<string, number | null>;
}

const DISPLAY_STATS: { key: string; label: string }[] = [
  { key: 'min',     label: 'MIN' },
  { key: 'pts',     label: 'PTS' },
  { key: 'reb',     label: 'REB' },
  { key: 'ast',     label: 'AST' },
  { key: 'pts_ast', label: 'PTS+AST' },
  { key: 'pts_reb', label: 'PTS+REB' },
  { key: 'pra',     label: 'PTS+REB+AST' },
];

function DiffCell({ value }: { value: number }) {
  const color = value > 0.5 ? '#27ae60' : value < -0.5 ? '#e74c3c' : '#333';
  return (
    <td style={{ padding: '8px 14px', textAlign: 'center', fontWeight: 700, color }}>
      {value > 0 ? '+' : ''}{value.toFixed(1)}
    </td>
  );
}

export default function NBAInOut() {
  const [players, setPlayers] = useState<string[]>([]);
  const [teammates, setTeammates] = useState<string[]>([]);
  const [playerA, setPlayerA] = useState('');
  const [excluded, setExcluded] = useState<string[]>([]);
  const [tmFilter, setTmFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<InOutData | null>(null);

  useEffect(() => {
    getNBAPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
  }, []);

  useEffect(() => {
    if (!playerA) { setTeammates([]); setExcluded([]); setTmFilter(''); setData(null); return; }
    getNBATeammates(playerA)
      .then((res) => setTeammates(res.data))
      .catch(() => setTeammates([]));
    setExcluded([]);
    setTmFilter('');
    setData(null);
  }, [playerA]);

  const toggleExclude = (name: string) => {
    setExcluded((prev) =>
      prev.includes(name) ? prev.filter((p) => p !== name) : [...prev, name]
    );
  };

  const analyze = async () => {
    if (!playerA) return;
    setLoading(true);
    setError('');
    setData(null);
    try {
      const res = await getNBAInOut(playerA, excluded);
      setData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch in/out data.');
    } finally {
      setLoading(false);
    }
  };

  const excludeLabel = excluded.length > 0 ? excluded.join(' & ') : 'excluded players';

  const filteredTeammates = tmFilter
    ? teammates.filter((t) => t.toLowerCase().includes(tmFilter.toLowerCase()))
    : teammates;

  return (
    <div style={{ padding: 24, overflowY: 'auto', minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 8, color: '#1a1a2e' }}>
        In/Out Analysis{playerA ? ` — ${playerA}` : ''}
      </h2>
      <p style={{ color: '#666', fontSize: 13, marginBottom: 24, marginTop: 0 }}>
        Compare an anchor player's stats when specific teammates are in vs. out of the lineup.
        "Without" shows games where <strong>all</strong> selected teammates were absent.
      </p>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start', marginBottom: 28 }}>

        {/* Anchor player */}
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
            Anchor Player
          </label>
          <SearchDropdown
            players={players}
            value={playerA}
            onSelect={setPlayerA}
            placeholder="Search by first or last name..."
          />
        </div>

        {/* Teammate checkbox list */}
        <div style={{ minWidth: 220 }}>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
            Exclude Teammates{excluded.length > 0 ? ` (${excluded.length} selected)` : ''}
          </label>
          <input
            type="text"
            placeholder={playerA ? 'Filter teammates...' : 'Select anchor first'}
            disabled={!playerA || teammates.length === 0}
            value={tmFilter}
            onChange={(e) => setTmFilter(e.target.value)}
            style={{
              width: '100%', boxSizing: 'border-box',
              padding: '7px 10px', fontSize: 13,
              border: '1px solid #ddd', borderRadius: 4,
              marginBottom: 4,
              background: !playerA || teammates.length === 0 ? '#f5f5f5' : 'white',
            }}
          />
          <div style={{
            border: '1px solid #ddd', borderRadius: 4,
            maxHeight: 200, overflowY: 'auto',
            background: !playerA || teammates.length === 0 ? '#f5f5f5' : 'white',
          }}>
            {!playerA || teammates.length === 0 ? (
              <div style={{ padding: '8px 12px', color: '#aaa', fontSize: 13 }}>
                {playerA ? 'No teammates found' : 'Select anchor player first'}
              </div>
            ) : filteredTeammates.length === 0 ? (
              <div style={{ padding: '8px 12px', color: '#aaa', fontSize: 13 }}>No matches</div>
            ) : (
              filteredTeammates.map((t) => (
                <label
                  key={t}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '6px 12px', cursor: 'pointer', fontSize: 13,
                    background: excluded.includes(t) ? '#f0f4ff' : 'transparent',
                    borderBottom: '1px solid #f0f0f0',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={excluded.includes(t)}
                    onChange={() => toggleExclude(t)}
                    style={{ cursor: 'pointer' }}
                  />
                  {t}
                </label>
              ))
            )}
          </div>
          {excluded.length > 0 && (
            <button
              onClick={() => setExcluded([])}
              style={{
                marginTop: 4, fontSize: 12, color: '#999', background: 'none',
                border: 'none', cursor: 'pointer', padding: 0,
              }}
            >
              Clear all
            </button>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 2 }}>
          <button
            onClick={analyze}
            disabled={!playerA || excluded.length === 0 || loading}
            style={{
              padding: '9px 28px',
              background: '#1a1a2e',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              fontWeight: 700,
              fontSize: 14,
              cursor: playerA && excluded.length > 0 && !loading ? 'pointer' : 'not-allowed',
              opacity: playerA && excluded.length > 0 && !loading ? 1 : 0.6,
            }}
          >
            Analyze
          </button>
        </div>
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!loading && data && (
        <>
          <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <div style={{
              background: '#e8f5e9', border: '1px solid #a5d6a7', borderRadius: 6,
              padding: '10px 20px', fontSize: 14,
            }}>
              <span style={{ fontWeight: 700, color: '#2e7d32' }}>With {excludeLabel}: </span>
              <span style={{ color: '#333' }}>{data.games_with} games</span>
            </div>
            <div style={{
              background: '#fce4ec', border: '1px solid #f48fb1', borderRadius: 6,
              padding: '10px 20px', fontSize: 14,
            }}>
              <span style={{ fontWeight: 700, color: '#c62828' }}>Without {excludeLabel}: </span>
              <span style={{ color: '#333' }}>{data.games_without} games</span>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: '#1a1a2e', color: 'white' }}>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Stat</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>With</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>Without</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>Diff</th>
                </tr>
              </thead>
              <tbody>
                {DISPLAY_STATS.map(({ key, label }, i) => {
                  const withVal = data.with?.[key] ?? null;
                  const withoutVal = data.without?.[key] ?? null;
                  if (withVal === null && withoutVal === null) return null;
                  const diff = (withoutVal ?? 0) - (withVal ?? 0);
                  return (
                    <tr key={key} style={{ borderBottom: '1px solid #eee', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                      <td style={{ padding: '8px 14px', fontWeight: 700, color: '#1a1a2e' }}>{label}</td>
                      <td style={{ padding: '8px 14px', textAlign: 'center' }}>
                        {withVal !== null ? withVal.toFixed(1) : '—'}
                      </td>
                      <td style={{ padding: '8px 14px', textAlign: 'center' }}>
                        {withoutVal !== null ? withoutVal.toFixed(1) : '—'}
                      </td>
                      <DiffCell value={diff} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!loading && !error && !data && (
        <div style={{ color: '#999', textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          Select an anchor player, check at least one teammate to exclude, then click "Analyze".
        </div>
      )}
    </div>
  );
}
