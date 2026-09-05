import { useState, useEffect } from 'react';
import { getNFLPlayers, getNFLTeammates, getNFLInOut } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import { theme } from '../../theme';

interface InOutData {
  player: string;
  exclude: string[];
  games_with: number;
  games_without: number;
  with: Record<string, number | null>;
  without: Record<string, number | null>;
}

const DISPLAY_STATS: { key: string; label: string }[] = [
  { key: 'carries',         label: 'Carries' },
  { key: 'rushing_yards',   label: 'Rush Yds' },
  { key: 'targets',         label: 'Targets' },
  { key: 'receptions',      label: 'Receptions' },
  { key: 'receiving_yards', label: 'Rec Yds' },
];

function DiffCell({ value }: { value: number }) {
  const color = value > 0.5 ? theme.dataBlue : value < -0.5 ? theme.dataRed : theme.textPrimary;
  return (
    <td style={{ padding: '8px 14px', textAlign: 'center', fontWeight: 700, color }}>
      {value > 0 ? '+' : ''}{value.toFixed(1)}
    </td>
  );
}

export default function NFLInOut() {
  const [players, setPlayers] = useState<string[]>([]);
  const [teammates, setTeammates] = useState<string[]>([]);
  const [playerA, setPlayerA] = useState('');
  const [excluded, setExcluded] = useState<string[]>([]);
  const [tmFilter, setTmFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<InOutData | null>(null);

  useEffect(() => {
    getNFLPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
  }, []);

  useEffect(() => {
    if (!playerA) { setTeammates([]); setExcluded([]); setTmFilter(''); setData(null); return; }
    getNFLTeammates(playerA)
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
      const res = await getNFLInOut(playerA, excluded);
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
    <div style={{ padding: 24, overflowY: 'auto', minHeight: 'calc(100vh - 60px)', background: theme.bgPage }}>
      <h2 style={{ marginTop: 0, marginBottom: 8, color: theme.textPrimary }}>
        NFL In/Out Analysis{playerA ? ` — ${playerA}` : ''}
      </h2>
      <p style={{ color: theme.textSecondary, fontSize: 13, marginBottom: 24, marginTop: 0 }}>
        Compare a player's carries/targets/receptions for games a specific teammate played versus games they didn't.
        "Without" shows games where <strong>all</strong> selected teammates were absent.
      </p>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start', marginBottom: 28 }}>

        {/* Anchor player */}
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>
            Player
          </label>
          <SearchDropdown
            players={players}
            value={playerA}
            onSelect={setPlayerA}
            placeholder="Search by first or last name..."
          />
        </div>

        {/* Teammate checkbox list — only shown once anchor player is selected */}
        {playerA && (
          <div style={{ minWidth: 220 }}>
            <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>
              Exclude Teammates{excluded.length > 0 ? ` (${excluded.length} selected)` : ''}
            </label>
            <input
              type="text"
              placeholder="Filter teammates..."
              disabled={teammates.length === 0}
              value={tmFilter}
              onChange={(e) => setTmFilter(e.target.value)}
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '7px 10px', fontSize: 13,
                border: `1px solid ${theme.border}`, borderRadius: 4,
                marginBottom: 4,
                background: teammates.length === 0 ? theme.bgCardHover : theme.bgCard,
                color: theme.textPrimary,
              }}
            />
            <div style={{
              border: `1px solid ${theme.border}`, borderRadius: 4,
              maxHeight: 200, overflowY: 'auto',
              background: teammates.length === 0 ? theme.bgCardHover : theme.bgCard,
            }}>
              {teammates.length === 0 ? (
                <div style={{ padding: '8px 12px', color: theme.textSecondary, fontSize: 13 }}>No teammates found</div>
              ) : filteredTeammates.length === 0 ? (
                <div style={{ padding: '8px 12px', color: theme.textSecondary, fontSize: 13 }}>No matches</div>
              ) : (
                filteredTeammates.map((t) => (
                  <label
                    key={t}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '6px 12px', cursor: 'pointer', fontSize: 13,
                      background: excluded.includes(t) ? theme.bgCardHover : 'transparent',
                      borderBottom: `1px solid ${theme.border}`, color: theme.textPrimary,
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
                  marginTop: 4, fontSize: 12, color: theme.textSecondary, background: 'none',
                  border: 'none', cursor: 'pointer', padding: 0,
                }}
              >
                Clear all
              </button>
            )}
          </div>
        )}

        {playerA && (
        <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 2 }}>
          <button
            onClick={analyze}
            disabled={!playerA || excluded.length === 0 || loading}
            style={{
              padding: '9px 28px',
              background: theme.accent,
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
        )}
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!loading && data && (
        <>
          <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <div style={{
              background: 'rgba(107,168,240,0.12)', border: `1px solid ${theme.dataBlue}`, borderRadius: 6,
              padding: '10px 20px', fontSize: 14,
            }}>
              <span style={{ fontWeight: 700, color: theme.dataBlue }}>With {excludeLabel}: </span>
              <span style={{ color: theme.textPrimary }}>{data.games_with} games</span>
            </div>
            <div style={{
              background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 6,
              padding: '10px 20px', fontSize: 14,
            }}>
              <span style={{ fontWeight: 700, color: theme.dataRed }}>Without {excludeLabel}: </span>
              <span style={{ color: theme.textPrimary }}>{data.games_without} games</span>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
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
                    <tr key={key} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                      <td style={{ padding: '8px 14px', fontWeight: 700, color: theme.textPrimary }}>{label}</td>
                      <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>
                        {withVal !== null ? withVal.toFixed(1) : '—'}
                      </td>
                      <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>
                        {withoutVal !== null ? withoutVal.toFixed(1) : '—'}
                      </td>
                      <DiffCell value={diff} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 10 }}>
            A 17-game season means these samples are often small -- check the game counts above before reading too much into a small difference.
          </div>
        </>
      )}

      {!loading && !error && !data && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          Select a player, check at least one teammate to exclude, then click "Analyze".
        </div>
      )}
    </div>
  );
}
