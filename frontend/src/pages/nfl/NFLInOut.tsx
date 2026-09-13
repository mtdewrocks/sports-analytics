import { useState, useEffect } from 'react';
import { getNFLPlayers, getNFLTeammates, getNFLInOut } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import BottomSheet, { SheetRow } from '../../components/BottomSheet';
import StatCard from '../../components/StatCard';
import useIsMobile from '../../hooks/useIsMobile';
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
  const isMobile = useIsMobile();
  const [sheetOpen, setSheetOpen] = useState(false);

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
    <div style={{ padding: isMobile ? 16 : 24, overflowY: 'auto', minHeight: 'calc(100vh - 60px)', background: theme.bgPage }}>
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

        {/* Teammate picker -- only shown once anchor player is selected.
            On a phone this opens as a sheet instead of being a 200px scrolling
            box inside the scrolling page: a nested scroll region on touch is
            unusable, because a flick either moves the wrong thing or nothing. */}
        {playerA && (
          isMobile ? (
            <div style={{ width: '100%' }}>
              <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>
                Exclude Teammates
              </label>
              <button
                onClick={() => setSheetOpen(true)}
                disabled={teammates.length === 0}
                style={{
                  width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 12px', minHeight: 42, borderRadius: 4,
                  border: `1px solid ${theme.border}`, background: theme.bgCard,
                  color: theme.textPrimary, fontSize: 13, cursor: 'pointer',
                }}
              >
                <span style={{ color: excluded.length ? theme.textPrimary : theme.textMuted }}>
                  {teammates.length === 0
                    ? 'No teammates found'
                    : excluded.length === 0
                      ? 'Choose teammates…'
                      : excluded.join(', ')}
                </span>
                <span style={{ color: theme.accent, fontWeight: 700, flexShrink: 0, marginLeft: 8 }}>
                  {excluded.length > 0 ? `${excluded.length} ›` : '›'}
                </span>
              </button>
            </div>
          ) : (
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
          )
        )}

        {playerA && (
        <div style={{
          display: 'flex', alignItems: 'flex-end', paddingBottom: 2,
          width: isMobile ? '100%' : undefined,
        }}>
          <button
            onClick={analyze}
            disabled={!playerA || excluded.length === 0 || loading}
            style={{
              padding: '11px 28px',
              width: isMobile ? '100%' : undefined,
              minHeight: 42,
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

      <BottomSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        title="Exclude teammates"
        footer={
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={() => setExcluded([])}
              disabled={excluded.length === 0}
              style={{
                flex: '0 0 auto', padding: '11px 18px', minHeight: 44, borderRadius: 4,
                border: `1px solid ${theme.border}`, background: 'transparent',
                color: theme.textSecondary, fontSize: 14, fontWeight: 600,
                cursor: excluded.length === 0 ? 'not-allowed' : 'pointer',
                opacity: excluded.length === 0 ? 0.5 : 1,
              }}
            >
              Clear
            </button>
            <button
              onClick={() => { setSheetOpen(false); analyze(); }}
              disabled={excluded.length === 0 || loading}
              style={{
                flex: 1, padding: '11px 0', minHeight: 44, borderRadius: 4, border: 'none',
                background: theme.accent, color: 'white', fontSize: 14, fontWeight: 700,
                cursor: excluded.length === 0 || loading ? 'not-allowed' : 'pointer',
                opacity: excluded.length === 0 || loading ? 0.6 : 1,
              }}
            >
              Analyze{excluded.length > 0 ? ` (${excluded.length})` : ''}
            </button>
          </div>
        }
      >
        <input
          type="text"
          placeholder="Filter teammates…"
          value={tmFilter}
          onChange={(e) => setTmFilter(e.target.value)}
          style={{
            width: '100%', boxSizing: 'border-box', padding: '10px 12px', fontSize: 14, minHeight: 42,
            border: `1px solid ${theme.border}`, borderRadius: 4, marginBottom: 6,
            background: theme.bgPage, color: theme.textPrimary,
          }}
        />
        {filteredTeammates.length === 0 ? (
          <div style={{ padding: '12px 2px', color: theme.textSecondary, fontSize: 14 }}>No matches</div>
        ) : (
          filteredTeammates.map((t) => (
            <SheetRow key={t} checked={excluded.includes(t)} onToggle={() => toggleExclude(t)}>
              {t}
            </SheetRow>
          ))
        )}
      </BottomSheet>

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

          {isMobile ? (
            /* The diff is the answer this page exists to give -- the table
               already computes it, it just isn't what your eye lands on. */
            <div>
              {DISPLAY_STATS.map(({ key, label }) => {
                const withVal = data.with?.[key] ?? null;
                const withoutVal = data.without?.[key] ?? null;
                if (withVal === null && withoutVal === null) return null;
                const diff = (withoutVal ?? 0) - (withVal ?? 0);
                const color = diff > 0.5 ? theme.dataBlue : diff < -0.5 ? theme.dataRed : theme.textPrimary;
                return (
                  <StatCard
                    key={key}
                    title={<span style={{ fontWeight: 700 }}>{label}</span>}
                    value={`${diff > 0 ? '+' : ''}${diff.toFixed(1)}`}
                    valueColor={color}
                    meta={[
                      <>{withVal !== null ? withVal.toFixed(1) : '—'} with</>,
                      <>{withoutVal !== null ? withoutVal.toFixed(1) : '—'} without</>,
                    ]}
                  />
                );
              })}
            </div>
          ) : (
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
          )}
          {/* Promoted from boilerplate to a signal: amber only when one of the
              two samples is actually thin enough to mislead. */}
          {(() => {
            const thin = Math.min(data.games_with, data.games_without) < 5;
            return (
              <div style={{ fontSize: 11, color: thin ? theme.warningText : theme.textMuted, marginTop: 10 }}>
                {thin
                  ? `Only ${Math.min(data.games_with, data.games_without)} games in the smaller sample -- read this gently.`
                  : 'A 17-game season means these samples are often small -- check the game counts above before reading too much into a small difference.'}
              </div>
            );
          })()}
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
