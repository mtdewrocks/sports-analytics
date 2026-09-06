import { useState, useEffect } from 'react';
import { getMLBMatchupTeams, getMLBTeamMatchup } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import { theme } from '../../theme';

interface LastN {
  games: number;
  wins: number;
  losses: number;
  avg_run_diff: number | null;
}
interface TeamRecord {
  team: string;
  wins: number | null;
  losses: number | null;
  last_n: LastN | null;
}
interface HeadToHead {
  team_a: string;
  team_b: string;
  games: number;
  team_a_wins?: number;
  team_b_wins?: number;
  team_a_avg_runs?: number;
  team_b_avg_runs?: number;
}
interface TeamMatchupData {
  team_a: TeamRecord;
  team_b: TeamRecord;
  head_to_head: HeadToHead;
}

function RecordCard({ record }: { record: TeamRecord }) {
  const diff = record.last_n?.avg_run_diff;
  const diffColor = diff == null ? theme.textPrimary : diff > 0 ? theme.dataBlue : diff < 0 ? theme.dataRed : theme.textPrimary;
  return (
    <div style={{ flex: 1, minWidth: 260, background: theme.bgCard, borderRadius: 8, padding: 18 }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: theme.textPrimary, marginBottom: 4 }}>{record.team}</div>
      {record.wins != null ? (
        <>
          <div style={{ fontSize: 14, color: theme.textSecondary, marginBottom: 12 }}>
            {record.wins}-{record.losses} season
          </div>
          {record.last_n && (
            <div style={{ fontSize: 13, color: theme.textPrimary }}>
              Last {record.last_n.games}: <strong>{record.last_n.wins}-{record.last_n.losses}</strong>
              {diff != null && (
                <>
                  {' '}&middot; avg run diff:{' '}
                  <strong style={{ color: diffColor }}>{diff > 0 ? '+' : ''}{diff}</strong>
                </>
              )}
            </div>
          )}
        </>
      ) : (
        <div style={{ fontSize: 13, color: theme.textSecondary }}>No completed games found for this team yet.</div>
      )}
    </div>
  );
}

export default function MLBTeamMatchup() {
  const [teams, setTeams] = useState<string[]>([]);
  const [teamA, setTeamA] = useState('');
  const [teamB, setTeamB] = useState('');
  const [data, setData] = useState<TeamMatchupData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    getMLBMatchupTeams()
      .then((res) => setTeams(res.data))
      .catch(() => setTeams([]));
  }, []);

  useEffect(() => {
    if (!teamA || !teamB || teamA === teamB) { setData(null); return; }
    setLoading(true);
    setError('');
    getMLBTeamMatchup(teamA, teamB)
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load matchup.'))
      .finally(() => setLoading(false));
  }, [teamA, teamB]);

  return (
    <div style={{ padding: 24, maxWidth: 1000, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>MLB Team Matchup</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 20 }}>
        Compare two teams' records, recent form, and head-to-head results this season.
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 24, flexWrap: 'wrap' }}>
        <select
          value={teamA}
          onChange={(e) => setTeamA(e.target.value)}
          style={{ padding: '8px 12px', fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgCard, color: theme.textPrimary, minWidth: 220 }}
        >
          <option value="">Select team...</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span style={{ color: theme.textSecondary, fontSize: 14 }}>vs.</span>
        <select
          value={teamB}
          onChange={(e) => setTeamB(e.target.value)}
          style={{ padding: '8px 12px', fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgCard, color: theme.textPrimary, minWidth: 220 }}
        >
          <option value="">Select team...</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!loading && !error && data && (
        <>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 20 }}>
            <RecordCard record={data.team_a} />
            <RecordCard record={data.team_b} />
          </div>

          <div style={{ background: theme.bgCard, borderRadius: 8, padding: 18, marginBottom: 24 }}>
            <div style={{ color: theme.textSecondary, fontSize: 11, textTransform: 'uppercase', marginBottom: 8 }}>Head-to-Head This Season</div>
            {data.head_to_head.games > 0 ? (
              <div style={{ fontSize: 14, color: theme.textPrimary }}>
                {(() => {
                  const h2h = data.head_to_head;
                  const aWins = h2h.team_a_wins ?? 0;
                  const bWins = h2h.team_b_wins ?? 0;
                  const leader = aWins === bWins ? null : aWins > bWins ? h2h.team_a : h2h.team_b;
                  const record = aWins > bWins ? `${aWins}-${bWins}` : bWins > aWins ? `${bWins}-${aWins}` : `${aWins}-${bWins}`;
                  return leader ? `${leader} leads ${record}` : `Series tied ${aWins}-${bWins}`;
                })()}
                {' '}({data.head_to_head.games} game{data.head_to_head.games === 1 ? '' : 's'}) &middot;{' '}
                avg runs: {data.head_to_head.team_a} {data.head_to_head.team_a_avg_runs}, {data.head_to_head.team_b} {data.head_to_head.team_b_avg_runs}
              </div>
            ) : (
              <div style={{ fontSize: 14, color: theme.textSecondary }}>These teams haven't played each other yet this season.</div>
            )}
          </div>

          <div style={{ background: theme.bgCardHover, borderRadius: 8, padding: '14px 18px', fontSize: 13, color: theme.textSecondary }}>
            Starting pitcher stats, bullpen fatigue and performance, and lineup batting splits are still being built for this page.
          </div>
        </>
      )}

      {!loading && !error && !data && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          Select two different teams to compare.
        </div>
      )}
    </div>
  );
}
