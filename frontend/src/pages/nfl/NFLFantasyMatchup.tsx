import { useState, useEffect } from 'react';
import { getNFLPlayers, getNFLFantasyMatchupCurrentWeek, getNFLFantasyMatchupSeason } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import SegmentedToggle from '../../components/SegmentedToggle';
import ScrollTable from '../../components/ScrollTable';
import { stickyColStyle } from '../../components/tableStyles';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

const MAX_PLAYERS = 4;
const MIN_PLAYERS = 2;

interface StatRow {
  label: string;
  value: number | null;
}
interface MatchupContextLine {
  label: string;
  value: number | null;
  rank: number | null;
  rank_word: string;
  granularity?: string;
  favorable: boolean | null;
}
interface MatchupContext {
  opp_defense: MatchupContextLine[];
  opp_pass_rush: MatchupContextLine | null;
  own_pass_block: MatchupContextLine | null;
}
interface TeamRecord {
  wins: number;
  losses: number;
  ties: number;
}
interface CurrentWeekPlayer {
  player: string;
  error?: string;
  team?: string;
  position?: string;
  team_record?: TeamRecord | null;
  opponent?: string;
  opponent_record?: TeamRecord | null;
  is_home?: boolean;
  week?: number;
  stats?: StatRow[];
  matchup_context?: MatchupContext | null;
  game_script?: { implied_situation: string; implied_total: number | null; baseline_pass_pct: number | null; projected_pass_pct: number | null } | null;
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

function formatRecord(record?: TeamRecord | null): string {
  if (!record) return '';
  return record.ties > 0 ? `${record.wins}-${record.losses}-${record.ties}` : `${record.wins}-${record.losses}`;
}

function favorableColor(favorable: boolean | null): string {
  if (favorable === true) return theme.dataBlue;
  if (favorable === false) return theme.dataRed;
  return theme.textPrimary;
}

function ContextLine({ line }: { line: MatchupContextLine }) {
  const asterisk = line.granularity && line.granularity !== 'team' ? '*' : '';
  return (
    <div style={{ fontSize: 12, color: theme.textPrimary, marginBottom: 3 }}>
      {line.label}:{' '}
      <span style={{ color: favorableColor(line.favorable), fontWeight: 600 }}>
        {line.value ?? '—'} ({line.rank != null ? `${line.rank}${asterisk} ${line.rank_word}` : '—'})
      </span>
    </div>
  );
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
        {p.position} &middot; {p.team} ({formatRecord(p.team_record)}) {p.opponent ? (p.is_home ? 'vs.' : '@') : ''} {p.opponent ? `${p.opponent} (${formatRecord(p.opponent_record)})` : '(no upcoming game)'}
      </div>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <tbody>
          {(p.stats ?? []).map((s) => (
            <tr key={s.label}>
              <td style={{ padding: '3px 0', color: theme.textSecondary }}>{s.label}</td>
              <td style={{ textAlign: 'right', color: theme.textPrimary, fontWeight: 600 }}>{s.value ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {p.matchup_context && (
        <div style={{ marginTop: 12, paddingTop: 10, borderTop: `1px solid ${theme.border}` }}>
          <div style={{ color: theme.textSecondary, fontSize: 10, textTransform: 'uppercase', marginBottom: 6 }}>Matchup Context</div>
          {p.matchup_context.opp_defense.map((line) => <ContextLine key={line.label} line={line} />)}
          {p.matchup_context.opp_pass_rush && <ContextLine line={p.matchup_context.opp_pass_rush} />}
          {p.matchup_context.own_pass_block && <ContextLine line={p.matchup_context.own_pass_block} />}
        </div>
      )}
      {p.game_script && (
        <div style={{ marginTop: 12, paddingTop: 10, borderTop: `1px solid ${theme.border}` }}>
          <div style={{ color: theme.textSecondary, fontSize: 10, textTransform: 'uppercase', marginBottom: 4 }}>Projected Script</div>
          <div style={{ color: theme.textPrimary, fontSize: 13 }}>
            {p.game_script.implied_situation.replace('_', ' ')} &middot;{' '}
            <span style={{ color: theme.dataBlue, fontWeight: 700 }}>{p.game_script.projected_pass_pct ?? '—'}% pass rate</span>
            {p.game_script.implied_total != null && (
              <> &middot; <span style={{ color: theme.textPrimary, fontWeight: 700 }}>{p.game_script.implied_total} projected team points (this game)</span></>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Season mode's backend still returns a raw rank rather than an explicit
// favorable boolean (unlike Current Week mode's matchup_context) -- kept
// as its own small helper rather than reusing favorableColor, since a raw
// yards-allowed rank direction isn't guaranteed to generalize the same way
// once other rank types get added to Season mode later.
function seasonRankColor(rank: number | null | undefined): string {
  if (rank == null) return theme.textSecondary;
  if (rank <= 10) return theme.dataRed;
  if (rank >= 23) return theme.dataBlue;
  return theme.textPrimary;
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
                <td style={{ textAlign: 'right', color: seasonRankColor(row.def_rank), fontWeight: 600 }}>
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

// ---------------------------------------------------------------- mobile
//
// The desktop layout is N cards side by side; at phone width those wrap into a
// vertical stack, which turns a comparison into a scroll-and-remember exercise.
// So on mobile the axes swap: stat labels stick to the left edge and the
// players become columns that scroll sideways. Row-by-row comparison survives
// at any slot count, which the stacked cards can't do.

interface CompareRow {
  key: string;
  label: string;
  cells: React.ReactNode[];
}

/** "Ja'Marr Chase" -> "J. Chase", so four columns can fit at all. */
function shortName(name: string): string {
  const parts = name.trim().split(' ');
  if (parts.length < 2) return name;
  return `${parts[0][0]}. ${parts.slice(1).join(' ')}`;
}

function contextLines(p: CurrentWeekPlayer): MatchupContextLine[] {
  return [
    ...(p.matchup_context?.opp_defense ?? []),
    p.matchup_context?.opp_pass_rush,
    p.matchup_context?.own_pass_block,
  ].filter((l): l is MatchupContextLine => !!l);
}

function buildCurrentWeekRows(players: CurrentWeekPlayer[]): CompareRow[] {
  const rows: CompareRow[] = [
    {
      key: 'pos', label: 'Pos · Team',
      cells: players.map((p) => (p.error ? '—' : `${p.position ?? '—'} · ${p.team ?? '—'}`)),
    },
    {
      key: 'opp', label: 'Opponent',
      cells: players.map((p) => {
        if (p.error) return '—';
        if (!p.opponent) return <span style={{ color: theme.textMuted }}>no game</span>;
        return `${p.is_home ? 'vs' : '@'} ${p.opponent}`;
      }),
    },
  ];

  // Union of labels in order of first appearance -- a QB and a WR don't have
  // the same stat rows, and dropping either player's rows would be worse than
  // a few dashes.
  const statLabels: string[] = [];
  players.forEach((p) => (p.stats ?? []).forEach((s) => {
    if (!statLabels.includes(s.label)) statLabels.push(s.label);
  }));
  statLabels.forEach((label) => rows.push({
    key: `stat:${label}`, label,
    cells: players.map((p) => {
      const s = (p.stats ?? []).find((x) => x.label === label);
      return s ? (s.value ?? '—') : '—';
    }),
  }));

  const ctxLabels: string[] = [];
  players.forEach((p) => contextLines(p).forEach((l) => {
    if (!ctxLabels.includes(l.label)) ctxLabels.push(l.label);
  }));
  ctxLabels.forEach((label) => rows.push({
    key: `ctx:${label}`, label,
    cells: players.map((p) => {
      const l = contextLines(p).find((x) => x.label === label);
      if (!l) return '—';
      const asterisk = l.granularity && l.granularity !== 'team' ? '*' : '';
      return (
        <span style={{ color: favorableColor(l.favorable), fontWeight: 600 }}>
          {l.value ?? '—'}
          {l.rank != null && (
            <span style={{ fontWeight: 400, fontSize: 10, color: theme.textMuted }}> ({l.rank}{asterisk})</span>
          )}
        </span>
      );
    }),
  }));

  if (players.some((p) => p.game_script)) {
    rows.push({
      key: 'pass', label: 'Proj. pass rate',
      cells: players.map((p) => (
        p.game_script?.projected_pass_pct != null
          ? <span style={{ color: theme.dataBlue, fontWeight: 700 }}>{p.game_script.projected_pass_pct}%</span>
          : '—'
      )),
    });
    rows.push({
      key: 'total', label: 'Proj. team pts',
      cells: players.map((p) => p.game_script?.implied_total ?? '—'),
    });
    rows.push({
      key: 'script', label: 'Script',
      cells: players.map((p) => p.game_script?.implied_situation.replace('_', ' ') ?? '—'),
    });
  }

  return rows;
}

function buildSeasonRows(players: SeasonPlayer[]): CompareRow[] {
  const weeks = Array.from(
    new Set(players.flatMap((p) => (p.schedule ?? []).map((r) => r.week)))
  ).sort((a, b) => a - b);

  return weeks.map((w) => ({
    key: `w${w}`,
    label: `Wk ${w}`,
    cells: players.map((p) => {
      const r = (p.schedule ?? []).find((x) => x.week === w);
      if (!r) return '—';
      if (r.is_bye) return <span style={{ color: theme.textMuted, fontStyle: 'italic' }}>BYE</span>;
      return (
        <>
          {r.is_home ? 'vs' : '@'} {r.opponent}{' '}
          <span style={{ color: seasonRankColor(r.def_rank), fontWeight: 700 }}>
            {r.def_rank ?? '—'}{r.def_granularity && r.def_granularity !== 'team' ? '*' : ''}
          </span>
        </>
      );
    }),
  }));
}

function CompareTable({ players, rows }: { players: { player: string; error?: string }[]; rows: CompareRow[] }) {
  const colWidth = 118;

  return (
    <ScrollTable>
      <table style={{
        borderCollapse: 'collapse', fontSize: 12.5,
        minWidth: 104 + players.length * colWidth,
        fontVariantNumeric: 'tabular-nums',
      }}>
        <thead>
          <tr>
            <th style={{
              ...stickyColStyle(theme.bgCardHover),
              width: 104, minWidth: 104, textAlign: 'left',
              padding: '9px 10px', fontSize: 11, color: theme.textSecondary, fontWeight: 600,
            }} />
            {players.map((p) => (
              <th key={p.player} style={{
                width: colWidth, minWidth: colWidth, textAlign: 'left',
                padding: '9px 10px', fontSize: 12, color: theme.textPrimary, fontWeight: 700,
                background: theme.bgCardHover, whiteSpace: 'nowrap',
              }}>
                {shortName(p.player)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const bg = i % 2 === 0 ? theme.bgCard : theme.bgPage;
            return (
              <tr key={row.key} style={{ borderTop: `1px solid ${theme.border}` }}>
                <th style={{
                  ...stickyColStyle(bg),
                  textAlign: 'left', padding: '8px 10px', fontSize: 11,
                  color: theme.textSecondary, fontWeight: 600,
                }}>
                  {row.label}
                </th>
                {row.cells.map((cell, j) => (
                  <td key={j} style={{ padding: '8px 10px', background: bg, color: theme.textPrimary }}>
                    {cell}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollTable>
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
  const isMobile = useIsMobile();

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
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 1200, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NFL Fantasy Matchup</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 20 }}>
        Compare 2-4 players side by side to help decide who to start.
      </div>

      <div style={{
        display: 'flex', alignItems: isMobile ? 'stretch' : 'center',
        flexDirection: isMobile ? 'column' : 'row',
        gap: isMobile ? 12 : 16, marginBottom: 20, flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {slots.map((slot, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 4, background: theme.bgCard,
              borderRadius: 6, padding: '4px 8px',
              flex: isMobile ? '1 1 100%' : undefined,
            }}>
              {loadingPlayers ? (
                <div style={{ color: theme.textSecondary, fontSize: 12, padding: '4px 8px' }}>Loading...</div>
              ) : (
                <div style={{ width: isMobile ? '100%' : 190 }}>
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
              style={{
                background: theme.accent, color: 'white', border: 'none', borderRadius: 6,
                padding: '8px 14px', fontSize: 12, fontWeight: 700, cursor: 'pointer', minHeight: 38,
                flex: isMobile ? '1 1 100%' : undefined,
              }}
            >
              + Add Player
            </button>
          )}
        </div>

        {/* On mobile the mode switch loses its marginLeft:'auto' and goes
            full-width -- it's the second most-used control on this page. */}
        <SegmentedToggle
          value={mode}
          onChange={setMode}
          fullWidth={isMobile}
          style={isMobile ? undefined : { marginLeft: 'auto' }}
          options={[
            { value: 'current_week', label: 'Current Week' },
            { value: 'season', label: 'Season' },
          ]}
        />
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!loading && !error && data && (
        isMobile ? (
          <CompareTable
            players={data.players}
            rows={mode === 'current_week'
              ? buildCurrentWeekRows(data.players as CurrentWeekPlayer[])
              : buildSeasonRows(data.players as SeasonPlayer[])}
          />
        ) : (
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            {mode === 'current_week'
              ? (data.players as CurrentWeekPlayer[]).map((p) => <CurrentWeekCard key={p.player} p={p} />)
              : (data.players as SeasonPlayer[]).map((p) => <SeasonCard key={p.player} p={p} />)}
          </div>
        )
      )}

      <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 16 }}>
        * = yards allowed to this specific position only. "Total Team" lines (no asterisk) show the full team defensive total for comparison, since the position-specific number alone can look unfamiliar without it.
      </div>
    </div>
  );
}
