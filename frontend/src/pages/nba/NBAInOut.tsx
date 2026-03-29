import { useState, useEffect, useRef } from 'react';
import { getNBAPlayers, getNBATeammates, getNBAInOut } from '../../api/nba';
import LoadingSpinner from '../../components/LoadingSpinner';

interface InOutData {
  player: string;
  exclude: string[];
  games_with: number;
  games_without: number;
  with: Record<string, number | null>;
  without: Record<string, number | null>;
}

const DISPLAY_STATS = ['pts', 'reb', 'ast', 'stl', 'blk', 'tov'];

function DiffCell({ value }: { value: number }) {
  const color = value > 0.5 ? '#27ae60' : value < -0.5 ? '#e74c3c' : '#333';
  return (
    <td style={{ padding: '8px 14px', textAlign: 'center', fontWeight: 700, color }}>
      {value > 0 ? '+' : ''}{value.toFixed(1)}
    </td>
  );
}

interface SearchDropdownProps {
  players: string[];
  value: string;
  onSelect: (p: string) => void;
  placeholder: string;
  disabled?: boolean;
}

function SearchDropdown({ players, value, onSelect, placeholder, disabled }: SearchDropdownProps) {
  const [search, setSearch] = useState(value);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Keep search text in sync if value is cleared externally
  useEffect(() => { setSearch(value); }, [value]);

  const filtered = players.filter((p) =>
    p.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <input
        disabled={disabled}
        style={{
          padding: '8px 12px', border: '1px solid #ddd', borderRadius: 4,
          fontSize: 14, minWidth: 220, width: '100%', boxSizing: 'border-box',
          background: disabled ? '#f5f5f5' : 'white', cursor: disabled ? 'not-allowed' : 'text',
        }}
        placeholder={placeholder}
        value={search}
        onChange={(e) => { setSearch(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && !disabled && search.length > 0 && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
          background: 'white', border: '1px solid #ddd', borderRadius: 4,
          maxHeight: 200, overflowY: 'auto', boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
        }}>
          {filtered.length === 0 ? (
            <div style={{ padding: '8px 12px', color: '#999', fontSize: 13 }}>No players found</div>
          ) : (
            filtered.map((p) => (
              <div
                key={p}
                onMouseDown={() => { onSelect(p); setSearch(p); setOpen(false); }}
                style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 13 }}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#f0f4ff')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'white')}
              >
                {p}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default function NBAInOut() {
  const [players, setPlayers] = useState<string[]>([]);
  const [teammates, setTeammates] = useState<string[]>([]);
  const [playerA, setPlayerA] = useState('');
  const [excludeA, setExcludeA] = useState('');
  const [excludeB, setExcludeB] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<InOutData | null>(null);

  useEffect(() => {
    getNBAPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
  }, []);

  // When anchor changes, load that player's teammates and clear prior selections
  useEffect(() => {
    if (!playerA) { setTeammates([]); setExcludeA(''); setExcludeB(''); setData(null); return; }
    getNBATeammates(playerA)
      .then((res) => setTeammates(res.data))
      .catch(() => setTeammates([]));
    setExcludeA('');
    setExcludeB('');
    setData(null);
  }, [playerA]);

  const analyze = async () => {
    if (!playerA) return;
    setLoading(true);
    setError('');
    setData(null);
    try {
      const exclude = [excludeA, excludeB].filter(Boolean);
      const res = await getNBAInOut(playerA, exclude);
      setData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch in/out data.');
    } finally {
      setLoading(false);
    }
  };

  // Exclude dropdowns show only teammates of the anchor player.
  // Filter out whoever is already selected in the other slot.
  const excludeAOptions = teammates.filter((p) => p !== excludeB);
  const excludeBOptions = teammates.filter((p) => p !== excludeA);

  const excludeLabel = [excludeA, excludeB].filter(Boolean).join(' & ') || 'excluded players';

  return (
    <div style={{ padding: 24, overflowY: 'auto', minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 8, color: '#1a1a2e' }}>
        In/Out Analysis{playerA ? ` — ${playerA}` : ''}
      </h2>
      <p style={{ color: '#666', fontSize: 13, marginBottom: 24, marginTop: 0 }}>
        Compare an anchor player's stats when specific teammates are in vs. out of the lineup.
      </p>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 28 }}>
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

        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
            Exclude Player A
          </label>
          <SearchDropdown
            players={excludeAOptions}
            value={excludeA}
            onSelect={setExcludeA}
            placeholder={playerA ? 'Search teammate...' : 'Select anchor first'}
            disabled={!playerA || teammates.length === 0}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
            Exclude Player B
          </label>
          <SearchDropdown
            players={excludeBOptions}
            value={excludeB}
            onSelect={setExcludeB}
            placeholder={playerA ? 'Search teammate...' : 'Select anchor first'}
            disabled={!playerA || teammates.length === 0}
          />
        </div>

        <button
          onClick={analyze}
          disabled={!playerA || loading}
          style={{
            padding: '9px 28px',
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

      {!loading && data && (
        <>
          {/* Game count context */}
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

          {/* Stats table */}
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
                {DISPLAY_STATS.map((stat, i) => {
                  const withVal = data.with?.[stat] ?? null;
                  const withoutVal = data.without?.[stat] ?? null;
                  if (withVal === null && withoutVal === null) return null;
                  const diff = (withVal ?? 0) - (withoutVal ?? 0);
                  return (
                    <tr key={stat} style={{ borderBottom: '1px solid #eee', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                      <td style={{ padding: '8px 14px', fontWeight: 700, textTransform: 'uppercase', color: '#1a1a2e' }}>
                        {stat}
                      </td>
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
          Select an anchor player and at least one player to exclude, then click "Analyze".
        </div>
      )}
    </div>
  );
}
