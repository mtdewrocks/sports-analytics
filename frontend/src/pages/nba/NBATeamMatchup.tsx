import { useState, useEffect } from 'react';
import { getNBATeams, getNBATeamMatchup, getNBASchedule } from '../../api/nba';
import LoadingSpinner from '../../components/LoadingSpinner';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

interface StatRow {
  key: string;
  label: string;
  direction: 'high' | 'low';
  kind: 'num' | 'pct';
  value: number | null;
  rank: number | null;
}

interface TeamRecord {
  wins: number;
  losses: number;
  last5: string;
}

interface HeadToHead {
  games: number;
  a_wins: number | null;
  b_wins: number | null;
  last_meeting: { date: string | null; a_pts: number | null; b_pts: number | null };
}

interface MatchupResponse {
  team_a: string;
  team_b: string;
  record_a: TeamRecord | null;
  record_b: TeamRecord | null;
  stats_a: StatRow[];
  stats_b: StatRow[];
  head_to_head: HeadToHead | null;
  season?: string | null;
}

interface Rest {
  last_game: string | null;
  days_rest: number | null;
  back_to_back: boolean;
}

interface ScheduleGame {
  game_id: number;
  tip: string | null;
  state: 'pre' | 'in' | 'post' | string | null;
  status: string | null;
  home: string;
  away: string;
  home_score: number | null;
  away_score: number | null;
  broadcast: string | null;
  home_rest: Rest;
  away_rest: Rest;
  spread?: string | null;
  total?: number | null;
}

interface ScheduleResponse {
  date: string | null;
  is_today?: boolean;
  dates: string[];
  games: ScheduleGame[];
}

function dayLabel(iso: string, todayIso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  const t = new Date(`${todayIso}T12:00:00`);
  const diff = Math.round((d.getTime() - t.getTime()) / 86400000);
  if (diff === 0) return 'Tonight';
  if (diff === 1) return 'Tomorrow';
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

function restLabel(r: Rest | undefined): string | null {
  if (!r || r.days_rest == null) return null;
  if (r.back_to_back) return 'Back-to-back';
  return `${r.days_rest} day${r.days_rest === 1 ? '' : 's'} rest`;
}

function GameStatus({ g }: { g: ScheduleGame }) {
  if (g.state === 'pre') return <>{g.tip || g.status}{g.broadcast ? ` · ${g.broadcast}` : ''}</>;
  if (g.state === 'post') return <>Final · {g.away} {g.away_score}–{g.home_score} {g.home}</>;
  return <>{g.status} · {g.away} {g.away_score ?? 0}–{g.home_score ?? 0} {g.home}</>;
}

function GameChip({ g, selected, onClick }: { g: ScheduleGame; selected: boolean; onClick: () => void }) {
  const rests = [
    { team: g.away, rest: g.away_rest },
    { team: g.home, rest: g.home_rest },
  ].filter((x) => x.rest?.back_to_back);
  return (
    <button
      onClick={onClick}
      style={{
        flex: '0 0 auto', minWidth: 150, textAlign: 'left', cursor: 'pointer',
        padding: '10px 12px', borderRadius: 6, background: selected ? theme.bgCardHover : theme.bgCard,
        border: `1px solid ${selected ? theme.dataBlue : theme.border}`, color: theme.textPrimary,
      }}
    >
      <div style={{ fontSize: 14, fontWeight: 700 }}>{g.away} @ {g.home}</div>
      <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 3 }}><GameStatus g={g} /></div>
      {(g.spread || g.total != null) && g.state === 'pre' && (
        <div style={{ fontSize: 11, color: theme.textPrimary, marginTop: 3, fontVariantNumeric: 'tabular-nums' }}>
          {[g.spread, g.total != null ? `O/U ${g.total}` : null].filter(Boolean).join(' · ')}
        </div>
      )}
      {rests.length > 0 && (
        <div style={{ fontSize: 10, color: theme.warningText, marginTop: 4, fontWeight: 600 }}>
          {rests.map((x) => `${x.team} on back-to-back`).join(' · ')}
        </div>
      )}
    </button>
  );
}

function ordinal(n: number): string {
  const rem100 = n % 100;
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1: return `${n}st`;
    case 2: return `${n}nd`;
    case 3: return `${n}rd`;
    default: return `${n}th`;
  }
}

// Rank position (not the raw number) drives the pill color -- same
// convention as the NFL/MLB Matchup pages: top-10 blue, bottom-10 red
// (bottom 10 of 30 teams = rank >= 21), everything else neutral.
function rankColor(rank: number | null): string {
  if (rank == null) return theme.textSecondary;
  if (rank <= 10) return theme.dataBlue;
  if (rank >= 21) return theme.dataRed;
  return theme.textSecondary;
}

function formatValue(row: StatRow): string {
  if (row.value == null) return '—';
  return row.kind === 'pct' ? `${(row.value * 100).toFixed(1)}%` : row.value.toFixed(1);
}

function StatValue({ row }: { row: StatRow }) {
  const color = rankColor(row.rank);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
      <span style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>
        {formatValue(row)}
      </span>
      {row.rank != null && (
        <span style={{ fontSize: 10, fontWeight: 700, color, border: `1px solid ${color}`, borderRadius: 4, padding: '0 5px' }}>
          {ordinal(row.rank)}
        </span>
      )}
    </div>
  );
}

function TeamHead({ team, record, badgeColor }: { team: string; record: TeamRecord | null; badgeColor: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <span style={{
        width: 30, height: 30, borderRadius: '50%', background: badgeColor, color: theme.bgPage,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontWeight: 800, letterSpacing: '-0.2px',
      }}>
        {team}
      </span>
      {record && (
        <span style={{ fontSize: 10, color: theme.textMuted, fontVariantNumeric: 'tabular-nums' }}>
          {record.wins}-{record.losses} &middot; L5 {record.last5}
        </span>
      )}
    </div>
  );
}

/**
 * Side-by-side comparison table -- one row per stat, both teams' numbers in
 * the same row so you read across rather than scrolling between two cards.
 * Reads the same on a phone as it does on desktop, since it's only two
 * narrow value columns next to a label rather than a wide multi-stat grid --
 * validated with the user against the mockup before this page was built.
 */
export default function NBATeamMatchup() {
  const [teams, setTeams] = useState<string[]>([]);
  const [teamA, setTeamA] = useState('');
  const [teamB, setTeamB] = useState('');
  const [data, setData] = useState<MatchupResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  const [schedule, setSchedule] = useState<ScheduleResponse | null>(null);
  const [todayIso, setTodayIso] = useState('');
  const [selectedGame, setSelectedGame] = useState<number | null>(null);

  const pickGame = (g: ScheduleGame) => {
    setSelectedGame(g.game_id);
    setTeamA(g.away);
    setTeamB(g.home);
  };

  const loadDay = (day?: string) => {
    getNBASchedule(day)
      .then((res) => {
        const sch: ScheduleResponse = res.data;
        setSchedule(sch);
        if (!day) {
          // the default load picks "today, or the next day with games"; remember
          // the real today so the day tabs label correctly
          const now = new Date();
          const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
          setTodayIso(`${et.getFullYear()}-${String(et.getMonth() + 1).padStart(2, '0')}-${String(et.getDate()).padStart(2, '0')}`);
        }
        const first = sch.games.find((g) => g.state !== 'post') || sch.games[0];
        if (first) pickGame(first);
      })
      .catch(() => setSchedule(null));
  };

  useEffect(() => {
    // Teams fill the manual dropdowns; the schedule (if there are games)
    // picks the first matchup of the night instead of the first two teams.
    getNBATeams()
      .then((res) => {
        setTeams(res.data);
        setTeamA((cur) => cur || res.data[0] || '');
        setTeamB((cur) => cur || res.data[1] || '');
      })
      .catch(() => setTeams([]));
    loadDay();
  }, []);

  useEffect(() => {
    if (!teamA || !teamB) return;
    setLoading(true);
    setError('');
    getNBATeamMatchup(teamA, teamB)
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load matchup.'))
      .finally(() => setLoading(false));
  }, [teamA, teamB]);

  const sameTeam = teamA && teamB && teamA === teamB;

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 700, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NBA Team Matchup</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 18 }}>
        Pick one of tonight's games, or any two teams, for season-to-date offense, defense
        and rest.
      </div>

      {schedule && schedule.dates.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', gap: 6, marginBottom: 10, overflowX: 'auto' }}>
            {schedule.dates.map((d) => (
              <button
                key={d}
                onClick={() => loadDay(d)}
                style={{
                  flex: '0 0 auto', padding: '5px 10px', borderRadius: 14, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  background: d === schedule.date ? theme.accent : 'transparent',
                  color: d === schedule.date ? theme.bgPage : theme.textSecondary,
                  border: `1px solid ${d === schedule.date ? theme.accent : theme.border}`,
                }}
              >
                {todayIso ? dayLabel(d, todayIso) : d}
              </button>
            ))}
          </div>
          {schedule.games.length === 0 ? (
            <div style={{ fontSize: 13, color: theme.textSecondary }}>No games on this day.</div>
          ) : (
            <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
              {schedule.games.map((g) => (
                <GameChip key={g.game_id} g={g} selected={g.game_id === selectedGame} onClick={() => pickGame(g)} />
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ fontSize: 12, color: theme.textMuted, marginBottom: 6 }}>
        {schedule?.games.length ? 'Or compare any two teams' : 'Pick two teams'}
      </div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 18, flexWrap: 'wrap' }}>
        <select
          value={teamA}
          onChange={(e) => { setSelectedGame(null); setTeamA(e.target.value); }}
          style={{
            flex: isMobile ? '1 1 100%' : undefined, minHeight: 40, padding: '9px 12px',
            fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`,
            background: theme.bgCard, color: theme.textPrimary, boxSizing: 'border-box',
          }}
        >
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select
          value={teamB}
          onChange={(e) => { setSelectedGame(null); setTeamB(e.target.value); }}
          style={{
            flex: isMobile ? '1 1 100%' : undefined, minHeight: 40, padding: '9px 12px',
            fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`,
            background: theme.bgCard, color: theme.textPrimary, boxSizing: 'border-box',
          }}
        >
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {sameTeam && !loading && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40, fontSize: 15 }}>
          Pick two different teams to compare.
        </div>
      )}

      {!loading && !error && !sameTeam && data && (
        <>
          {(() => {
            const g = schedule?.games.find((x) => x.game_id === selectedGame);
            if (!g) return null;
            const items = [
              { team: g.away, label: restLabel(g.away_rest), b2b: g.away_rest?.back_to_back },
              { team: g.home, label: restLabel(g.home_rest), b2b: g.home_rest?.back_to_back },
            ].filter((x) => x.label);
            if (!items.length) return null;
            return (
              <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12, color: theme.textSecondary, marginBottom: 10 }}>
                <span style={{ color: theme.textMuted }}>Rest:</span>
                {items.map((x) => (
                  <span key={x.team}>
                    {x.team} <b style={{ color: x.b2b ? theme.warningText : theme.textPrimary }}>{x.label}</b>
                  </span>
                ))}
              </div>
            );
          })()}
          <table style={{ width: '100%', borderCollapse: 'collapse', background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, overflow: 'hidden' }}>
            <colgroup>
              <col style={{ width: '42%' }} />
              <col />
              <col />
            </colgroup>
            <thead>
              <tr style={{ background: theme.bgCardHover }}>
                <th style={{ textAlign: 'left', padding: '10px 8px 10px 12px', borderBottom: `1px solid ${theme.border}`, fontSize: 12, color: theme.textSecondary, fontWeight: 600 }}>
                  Stat
                </th>
                <th style={{ padding: '10px 8px', borderBottom: `1px solid ${theme.border}` }}>
                  <TeamHead team={data.team_a} record={data.record_a} badgeColor={theme.accent} />
                </th>
                <th style={{ padding: '10px 8px', borderBottom: `1px solid ${theme.border}` }}>
                  <TeamHead team={data.team_b} record={data.record_b} badgeColor={theme.dataBlue} />
                </th>
              </tr>
            </thead>
            <tbody>
              {data.stats_a.map((sa, i) => {
                const sb = data.stats_b[i];
                let advNode: React.ReactNode = null;
                if (sa.value != null && sb && sb.value != null) {
                  if (sa.value === sb.value) {
                    advNode = <div style={{ fontSize: 10, fontWeight: 600, color: theme.textMuted, marginTop: 3 }}>Even</div>;
                  } else {
                    const aBetter = sa.direction === 'high' ? sa.value > sb.value : sa.value < sb.value;
                    const winner = aBetter ? data.team_a : data.team_b;
                    const color = aBetter ? theme.accent : theme.dataBlue;
                    advNode = (
                      <div style={{ fontSize: 10, fontWeight: 700, color, marginTop: 3, letterSpacing: '0.1px' }}>
                        Advantage: {winner}
                      </div>
                    );
                  }
                }
                return (
                  <tr key={sa.key} style={{ borderBottom: i === data.stats_a.length - 1 ? 'none' : `1px solid ${theme.border}` }}>
                    <td style={{ padding: '10px 8px 10px 12px', verticalAlign: 'top', textAlign: 'left', fontSize: 12, color: theme.textSecondary, paddingTop: 11 }}>
                      {sa.label}
                      {advNode}
                    </td>
                    <td style={{ padding: '10px 8px', verticalAlign: 'top', textAlign: 'center' }}>
                      <StatValue row={sa} />
                    </td>
                    <td style={{ padding: '10px 8px', verticalAlign: 'top', textAlign: 'center' }}>
                      <StatValue row={sb} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '14px 16px', marginTop: 12, fontSize: 12.5 }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.4px', color: theme.textMuted, marginBottom: 8 }}>
              Head-to-head since last season
            </div>
            {!data.head_to_head ? (
              <div style={{ color: theme.textSecondary }}>No meetings between these teams yet this season.</div>
            ) : (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: theme.textSecondary, padding: '3px 0' }}>
                  <span>Meetings</span><b style={{ color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>{data.head_to_head.games}</b>
                </div>
                {data.head_to_head.a_wins != null && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: theme.textSecondary, padding: '3px 0' }}>
                    <span>{data.team_a} wins</span><b style={{ color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>{data.head_to_head.a_wins}</b>
                  </div>
                )}
                {data.head_to_head.b_wins != null && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: theme.textSecondary, padding: '3px 0' }}>
                    <span>{data.team_b} wins</span><b style={{ color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>{data.head_to_head.b_wins}</b>
                  </div>
                )}
                {data.head_to_head.last_meeting.a_pts != null && data.head_to_head.last_meeting.b_pts != null && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: theme.textSecondary, padding: '3px 0' }}>
                    <span>Last meeting</span>
                    <b style={{ color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>
                      {data.team_a} {data.head_to_head.last_meeting.a_pts} &ndash; {data.team_b} {data.head_to_head.last_meeting.b_pts}
                    </b>
                  </div>
                )}
              </>
            )}
          </div>

          <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 18, paddingTop: 14, borderTop: `1px solid ${theme.border}`, lineHeight: 1.55 }}>
            Offense is each team's own box-score totals; defense is the same file read the
            other way -- summing what opponents put up in games against them. The rank pill
            and the "Advantage" line answer two different questions on purpose: rank is
            against the whole league, Advantage is against the specific opponent in the
            other column, and two top-10 teams can still be lopsided against each other on
            a given stat.
          </div>
        </>
      )}
    </div>
  );
}
