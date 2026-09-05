import { useState, useEffect } from 'react';
import { getNFLPlayers, getNFLFantasyMatchupCurrentWeek, getNFLFantasyMatchupSeason } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import { theme } from '../../theme';

const MAX_PLAYERS = 4;
const MIN_PLAYERS = 2;

interface StatRow {
  label: string;
  value: number | null;
  def_rank?: number | null;
  def_ypg?: number | null;
  def_granularity?: string;
}
interface CurrentWeekPlayer {
  player: string;
  error?: string;
  team?: string;
  position?: string;
  opponent?: string;
  is_home?: boolean;
  week?: number;
  stats?: StatRow[];
  game_script?: { implied_situation: string; baseline_pass_pct: number | null; projected_pass_pct: number | null } | null;
}
interface ScheduleRow {
  week: number;
  is_bye: boolean;
  opponent?: string;
  is_home?: boolean;
  def_rank?: number | null;
  def_granularity?: string;
}
interface SeasonPlayer {
  player: string;
  error?: string;
  team?: string;
  position?: string;
  schedule?: ScheduleRow[];
}

function rankColor(rank: number | null | undefined): string {
  if (rank == null) return theme.textSecondary;
  if (rank <= 10) return theme.dataBlue;
  if (rank >= 23) return theme.dataRed;
  return theme.textPrimary;
}

const cardStyle: React.CSSProperties = {
  background: theme.bgCard,
  borderRadius: 8,
  padding: 16,
  flex: '1 1 260px',
  minWidth: 260,
};

function CurrentWeekCard({ p }: { p: CurrentWeekPlayer }) {
  if (p.error) {
    return (
      <div style={cardStyle}>
        <div style={{ color: theme.textPrimary, fontWeight: 700, marginBottom: 8 }}>{p.player}</div>
        <div style={{ color: theme.textSecondary, fontSize: 13 }}>{p.error}</div>
      </div>
    );
  }
  return (
    <div style={cardStyle}>
      <div style={{ color: theme.textPrimary, fontWeight: 700, fontSize: 15 }}>{p.player}</div>
      <div style={{ color: theme.textSecondary, fontSize: 11, marginBottom: 10 }}>
        {p.position} &middot; {p.team} {p.opponent ? (p.is_home ? 'vs.' : '@') : ''} {p.opponent ?? '(no upcoming game)'}
      </div>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <tbody>
          {(p.stats ?? []).map((s) => (
            <tr key={s.label}>
              <td style={{ padding: '3px 0', color: theme.textSecondary }}>{s.label}</td>
              <td style={{ textAlign: 'right', color: theme.textPrimary, fontWeight: 600 }}>{s.value ?? '—'}</td>
              <td style={{ textAlign: 'right', paddingLeft: 8, color: rankColor(s.def_rank), fontWeight: 600 }}>
                {s.def_rank != null ? `${s.def_rank}${s.def_granularity && s.def_granularity !== 'team' ? '*' : ''}` : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {p.game_script && (
        <div style={{ marginTop: 12, paddingTop: 10, borderTop: `1px solid ${theme.border}` }}>
          <div style={{ color: theme.textSecondary, fontSize: 10, textTransform: 'uppercase', marginBottom: 4 }}>Projected Script</div>
          <div style={{ color: theme.textPrimary, fontSize: 13 }}>
            {p.game_script.implied_situation.replace('_', ' ')} &middot;{' '}
            <span style={{ color: theme.dataBlue, fontWeight: 700 }}>{p.game_script.projected_pass_pct ?? '—'}% pass rate</span>
          </div>
        </div>
      )}
    </div>
  );
}

function SeasonCard({ p }: { p: SeasonPlayer }) {
  if (p.error) {
    return (
      <div style={cardStyle}>
        <div style={{ color: theme.textPrimary, fontWeight: 700, marginBottom: 8 }}>{p.player}</div>
        <div style={{ color: theme.textSecondary, fontSize: 13 }}>{p.error}</div>
      </div>
    );
  }
  return (
    <div style={{ ...cardStyle, minWidth: 220, flex: '1 1 220px' }}>
      <div style={{ color: theme.textPrimary, fontWeight: 700, fontSize: 15, marginBottom: 2 }}>{p.player}</div>
      <div style={{ color: theme.textSecondary, fontSize: 11, marginBottom: 10 }}>{p.position} &middot; {p.team}</div>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ color: theme.textSecondary, textAlign: 'left' }}>
            <th style={{ padding: '4px 0', fontWeight: 600 }}>Wk</th>
            <th style={{ fontWeight: 600 }}>Opp</th>
            <th style={{ textAlign: 'right', fontWeight: 600 }}>Rank</th>
          </tr>
        </thead>
        <tbody>
          {(p.schedule ?? []).map((row) =>
            row.is_bye ? (
              <tr key={row.week} style={{ borderTop: `1px solid ${theme.border}` }}>
                <td style={{ padding: '4px 0', color: theme.textMuted }}>{row.week}</td>
                <td colSpan={2} style={{ color: theme.textMuted, fontStyle: 'italic' }}>BYE</td>
              </tr>
            ) : (
              <tr key={row.week} style={{ borderTop: `1px solid ${theme.border}` }}>
                <td style={{ padding: '4px 0', color: theme.textSecondary }}>{row.week}</td>
                <td style={{ color: theme.textPrimary }}>{row.is_home ? 'vs' : '@'} {row.opponent}</td>
                <td style={{ textAlign: 'right', color: rankColor(row.def_rank), fontWeight: 600 }}>
                  {row.def_rank ?? '—'}{row.def_granularity && row.def_granularity !== 'team' ? '*' : ''}
                </td>
              </tr>
            )
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function NFLFantasyMatchup() {
  const [allPlayers, setAllPlayers] = useState<string[]>([]);
  const [loadingPlayers, setLoadingPlayers] = useState(true);
  const [slots, setSlots] = useState<(string | null)[]>([null, null]);
  const [mode, setMode] = useState<'current_week' | 'season'>('current_week');
  const [data, setData] = useState<{ players: (CurrentWeekPlayer | SeasonPlayer)[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoadingPlayers(true);
    getNFLPlayers()
      .then((res) => {
        setAllPlayers(res.data);
        // Automatically start with two players selected, rather than an
        // empty comparison with nothing to show on first load.
        if (res.data.length >= 2) {
          setSlots([res.data[0], res.data[1]]);
        }
      })
      .catch(() => setAllPlayers([]))
      .finally(() => setLoadingPlayers(false));
  }, []);

  const filledSlots = slots.filter((s): s is string => !!s);

  useEffect(() => {
    if (filledSlots.length < MIN_PLAYERS) return;
    setLoading(true);
    setError('');
    const call = mode === 'current_week' ? getNFLFantasyMatchupCurrentWeek : getNFLFantasyMatchupSeason;
    call(filledSlots)
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load comparison.'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, JSON.stringify(filledSlots)]);

  const updateSlot = (i: number, player: string) => {
    const next = [...slots];
    next[i] = player;
    setSlots(next);
  };
  const removeSlot = (i: number) => {
    setSlots(slots.filter((_, idx) => idx !== i));
  };
  const addSlot = () => {
    if (slots.length < MAX_PLAYERS) setSlots([...slots, null]);
  };

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NFL Fantasy Matchup</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 20 }}>
        Compare 2-4 players side by side to help decide who to start.
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {slots.map((slot, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, background: theme.bgCard, borderRadius: 6, padding: '4px 8px' }}>
              {loadingPlayers ? (
                <div style={{ color: theme.textSecondary, fontSize: 12, padding: '4px 8px' }}>Loading...</div>
              ) : (
                <div style={{ width: 190 }}>
                  <SearchDropdown
                    players={allPlayers}
                    value={slot ?? ''}
                    onSelect={(p) => updateSlot(i, p)}
                    placeholder={`Player ${i + 1}`}
                    inputStyle={{ padding: '6px 8px', fontSize: 12, width: '100%', boxSizing: 'border-box', border: 'none', background: 'transparent' }}
                  />
                </div>
              )}
              {slots.length > MIN_PLAYERS && (
                <button
                  onClick={() => removeSlot(i)}
                  style={{ background: 'none', border: 'none', color: theme.textMuted, cursor: 'pointer', fontSize: 14, padding: '0 4px' }}
                  title="Remove player"
                >
                  &times;
                </button>
              )}
            </div>
          ))}
          {slots.length < MAX_PLAYERS && (
            <button
              onClick={addSlot}
              style={{ background: theme.accent, color: 'white', border: 'none', borderRadius: 6, padding: '8px 14px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}
            >
              + Add Player
            </button>
          )}
        </div>

        <div style={{ display: 'flex', gap: 4, background: theme.bgCard, borderRadius: 6, padding: 3, marginLeft: 'auto' }}>
          <button
            onClick={() => setMode('current_week')}
            style={{
              padding: '6px 14px', fontSize: 12, fontWeight: 700, borderRadius: 4, border: 'none', cursor: 'pointer',
              background: mode === 'current_week' ? theme.bgCardHover : 'transparent',
              color: mode === 'current_week' ? theme.textPrimary : theme.textSecondary,
            }}
          >
            Current Week
          </button>
          <button
            onClick={() => setMode('season')}
            style={{
              padding: '6px 14px', fontSize: 12, fontWeight: 700, borderRadius: 4, border: 'none', cursor: 'pointer',
              background: mode === 'season' ? theme.bgCardHover : 'transparent',
              color: mode === 'season' ? theme.textPrimary : theme.textSecondary,
            }}
          >
            Season
          </button>
        </div>
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!loading && !error && data && (
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
          {mode === 'current_week'
            ? (data.players as CurrentWeekPlayer[]).map((p) => <CurrentWeekCard key={p.player} p={p} />)
            : (data.players as SeasonPlayer[]).map((p) => <SeasonCard key={p.player} p={p} />)}
        </div>
      )}

      <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 16 }}>
        * = position-specific defensive rank (e.g. rushing yards allowed to RBs specifically). No asterisk = team-level rank, used as a fallback where a position-specific split isn't available yet.
      </div>
    </div>
  );
}
