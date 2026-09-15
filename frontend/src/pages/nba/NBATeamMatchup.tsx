import { useState, useEffect } from 'react';
import { getNBATeams, getNBATeamMatchup } from '../../api/nba';
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

  useEffect(() => {
    getNBATeams()
      .then((res) => {
        setTeams(res.data);
        if (res.data.length > 0) setTeamA(res.data[0]);
        if (res.data.length > 1) setTeamB(res.data[1]);
      })
      .catch(() => setTeams([]));
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
        Season-to-date offense and defense for both teams, straight from the same box-score
        file -- no separate team-stats pipeline needed.
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 18, flexWrap: 'wrap' }}>
        <select
          value={teamA}
          onChange={(e) => setTeamA(e.target.value)}
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
          onChange={(e) => setTeamB(e.target.value)}
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
              Head-to-head this season
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
