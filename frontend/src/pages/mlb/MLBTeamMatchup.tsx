import { useState, useEffect } from 'react';
import { getMLBTodaysMatchups, getMLBTeamMatchup } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import { theme } from '../../theme';

interface TodaysMatchup {
  game_pk: number;
  away_team: string;
  home_team: string;
  label: string;
}
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
interface HandSplit {
  k_pct: number;
  bb_pct: number;
  woba: number;
  iso: number;
}
interface PitcherInfo {
  pitcher: string;
  vs_l: HandSplit | null;
  vs_r: HandSplit | null;
}
interface BullpenKpi {
  pitches: number;
  ip: string;
  level: string;
}
interface RecentPerformance {
  days: number;
  era: number;
  whip: number;
  ip: number;
}
interface BullpenInfo {
  freshness: string;
  kpis: Record<string, BullpenKpi>;
  recent_performance: RecentPerformance | null;
}
interface LineupAverages {
  avg?: number;
  woba?: number;
  iso?: number;
  k_pct?: number;
  bb_pct?: number;
  batters: number;
}
interface HittingWindow {
  woba: number;
  pa: number;
}
interface HittingVsHandedness {
  vs_hand: string;
  season?: HittingWindow;
  last_30_days?: HittingWindow;
}
interface TeamMatchupData {
  team_a: TeamRecord;
  team_b: TeamRecord;
  head_to_head: HeadToHead;
  team_a_pitcher: PitcherInfo | null;
  team_b_pitcher: PitcherInfo | null;
  team_a_bullpen: BullpenInfo;
  team_b_bullpen: BullpenInfo;
  team_a_lineup_vs_b: LineupAverages | null;
  team_b_lineup_vs_a: LineupAverages | null;
  team_a_hitting_vs_b: HittingVsHandedness | null;
  team_b_hitting_vs_a: HittingVsHandedness | null;
}

const freshnessColor = (level: string) =>
  level === 'fresh' ? theme.dataBlue : level === 'tired' ? theme.dataRed : theme.textPrimary;

function PitcherSplitTable({ pitcher }: { pitcher: PitcherInfo }) {
  const rows: { label: string; key: keyof HandSplit; digits: number }[] = [
    { label: 'K%', key: 'k_pct', digits: 1 },
    { label: 'BB%', key: 'bb_pct', digits: 1 },
    { label: 'wOBA', key: 'woba', digits: 3 },
    { label: 'ISO', key: 'iso', digits: 3 },
  ];
  return (
    <div>
      <div style={{ color: theme.textPrimary, fontWeight: 700, fontSize: 14 }}>{pitcher.pitcher}</div>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', marginTop: 6 }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', padding: '2px 0', color: theme.textSecondary, fontWeight: 600 }}></th>
            <th style={{ textAlign: 'right', padding: '2px 0', color: theme.textSecondary, fontWeight: 600 }}>vs LHB</th>
            <th style={{ textAlign: 'right', padding: '2px 0', color: theme.textSecondary, fontWeight: 600 }}>vs RHB</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, key, digits }) => (
            <tr key={key}>
              <td style={{ padding: '2px 0', color: theme.textSecondary }}>{label}</td>
              <td style={{ textAlign: 'right', color: theme.textPrimary, fontWeight: 600 }}>
                {pitcher.vs_l?.[key] != null ? pitcher.vs_l[key].toFixed(digits) : '—'}
              </td>
              <td style={{ textAlign: 'right', color: theme.textPrimary, fontWeight: 600 }}>
                {pitcher.vs_r?.[key] != null ? pitcher.vs_r[key].toFixed(digits) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HittingVsHandBlock({ hitting, teamName }: { hitting: HittingVsHandedness | null; teamName: string }) {
  if (!hitting) return null;
  const handLabel = hitting.vs_hand === 'L' ? 'LHP' : 'RHP';
  return (
    <div>
      <div style={{ color: theme.textSecondary, fontSize: 10, textTransform: 'uppercase', marginBottom: 4 }}>
        {teamName} wOBA vs {handLabel}
      </div>
      <div style={{ fontSize: 12, color: theme.textPrimary }}>
        {hitting.season && <>Season: <strong>{hitting.season.woba.toFixed(3)}</strong></>}
        {hitting.last_30_days && <> &middot; L30d: <strong>{hitting.last_30_days.woba.toFixed(3)}</strong></>}
      </div>
    </div>
  );
}

function BullpenBlock({ bullpen }: { bullpen: BullpenInfo }) {
  const perf = bullpen.recent_performance;
  return (
    <div>
      <div style={{ color: theme.textSecondary, fontSize: 10, textTransform: 'uppercase', marginBottom: 4 }}>Bullpen</div>
      <div style={{ fontSize: 12, color: theme.textPrimary }}>
        Fatigue (3d): <strong style={{ color: freshnessColor(bullpen.kpis?.['3_day']?.level ?? '') }}>
          {bullpen.kpis?.['3_day']?.level ? bullpen.kpis['3_day'].level[0].toUpperCase() + bullpen.kpis['3_day'].level.slice(1) : '—'}
        </strong>
        {perf && (
          <>
            {' '}&middot; ERA/WHIP (L{perf.days}d):{' '}
            <strong style={{ color: theme.textPrimary }}>{perf.era.toFixed(2)}/{perf.whip.toFixed(2)}</strong>
          </>
        )}
      </div>
    </div>
  );
}

function LineupBlock({ lineup, teamName, pitcherName }: { lineup: LineupAverages | null; teamName: string; pitcherName?: string }) {
  return (
    <div>
      <div style={{ color: theme.textSecondary, fontSize: 10, textTransform: 'uppercase', marginBottom: 6 }}>
        Today's {teamName} Lineup{pitcherName ? ` vs. ${pitcherName}` : ''}
      </div>
      {lineup ? (
        <>
          <div style={{ fontSize: 11, color: theme.textSecondary, marginBottom: 4 }}>{lineup.batters} batters, straight average</div>
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <tbody>
              <tr><td style={{ padding: '2px 0', color: theme.textSecondary }}>AVG</td><td style={{ textAlign: 'right', color: theme.textPrimary, fontWeight: 600 }}>{lineup.avg?.toFixed(3) ?? '—'}</td></tr>
              <tr><td style={{ padding: '2px 0', color: theme.textSecondary }}>wOBA</td><td style={{ textAlign: 'right', color: theme.textPrimary, fontWeight: 600 }}>{lineup.woba?.toFixed(3) ?? '—'}</td></tr>
              <tr><td style={{ padding: '2px 0', color: theme.textSecondary }}>ISO</td><td style={{ textAlign: 'right', color: theme.textPrimary, fontWeight: 600 }}>{lineup.iso?.toFixed(3) ?? '—'}</td></tr>
              <tr><td style={{ padding: '2px 0', color: theme.textSecondary }}>BB%</td><td style={{ textAlign: 'right', color: theme.textPrimary, fontWeight: 600 }}>{lineup.bb_pct?.toFixed(1) ?? '—'}</td></tr>
              <tr><td style={{ padding: '2px 0', color: theme.textSecondary }}>K%</td><td style={{ textAlign: 'right', color: theme.textPrimary, fontWeight: 600 }}>{lineup.k_pct?.toFixed(1) ?? '—'}</td></tr>
            </tbody>
          </table>
        </>
      ) : (
        <div style={{ background: 'rgba(107,168,240,0.1)', border: `1px solid ${theme.dataBlue}`, borderRadius: 6, padding: '8px 10px', fontSize: 11, color: theme.dataBlue }}>
          Available once today's lineup posts.
        </div>
      )}
    </div>
  );
}

function TeamCard({
  record, pitcher, bullpen, lineup, hitting, opponentPitcherName,
}: {
  record: TeamRecord; pitcher: PitcherInfo | null; bullpen: BullpenInfo;
  lineup: LineupAverages | null; hitting: HittingVsHandedness | null; opponentPitcherName?: string;
}) {
  const diff = record.last_n?.avg_run_diff;
  const diffColor = diff == null ? theme.textPrimary : diff > 0 ? theme.dataBlue : diff < 0 ? theme.dataRed : theme.textPrimary;
  return (
    <div style={{ flex: 1, minWidth: 300, background: theme.bgCard, borderRadius: 8, padding: 18 }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: theme.textPrimary, marginBottom: 2 }}>{record.team}</div>
      {record.wins != null ? (
        <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 12 }}>
          {record.wins}-{record.losses} season
          {record.last_n && (
            <>
              {' '}&middot; Last {record.last_n.games}: {record.last_n.wins}-{record.last_n.losses}
              {diff != null && <> &middot; run diff: <strong style={{ color: diffColor }}>{diff > 0 ? '+' : ''}{diff}</strong></>}
            </>
          )}
        </div>
      ) : (
        <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 12 }}>No completed games found yet.</div>
      )}

      {pitcher && (
        <div style={{ borderTop: `1px solid ${theme.border}`, paddingTop: 10, marginBottom: 10 }}>
          <PitcherSplitTable pitcher={pitcher} />
        </div>
      )}

      {hitting && (
        <div style={{ borderTop: `1px solid ${theme.border}`, paddingTop: 10, marginBottom: 10 }}>
          <HittingVsHandBlock hitting={hitting} teamName={record.team} />
        </div>
      )}

      <div style={{ borderTop: `1px solid ${theme.border}`, paddingTop: 10, marginBottom: 10 }}>
        <BullpenBlock bullpen={bullpen} />
      </div>

      <div style={{ borderTop: `2px dashed ${theme.border}`, paddingTop: 10 }}>
        {!lineup && (
          <div style={{ fontSize: 10, color: theme.textMuted, textTransform: 'uppercase', marginBottom: 6, textAlign: 'center' }}>
            &mdash; pending lineup &mdash;
          </div>
        )}
        <LineupBlock lineup={lineup} teamName={record.team} pitcherName={opponentPitcherName} />
      </div>
    </div>
  );
}

export default function MLBTeamMatchup() {
  const [matchups, setMatchups] = useState<TodaysMatchup[]>([]);
  const [selectedPk, setSelectedPk] = useState<string>('');
  const [data, setData] = useState<TeamMatchupData | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMatchups, setLoadingMatchups] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getMLBTodaysMatchups()
      .then((res) => {
        setMatchups(res.data);
        if (res.data.length > 0) setSelectedPk(String(res.data[0].game_pk));
      })
      .catch(() => setMatchups([]))
      .finally(() => setLoadingMatchups(false));
  }, []);

  const selected = matchups.find((m) => String(m.game_pk) === selectedPk);

  useEffect(() => {
    if (!selected) { setData(null); return; }
    setLoading(true);
    setError('');
    getMLBTeamMatchup(selected.away_team, selected.home_team)
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load matchup.'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPk]);

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>MLB Team Matchup</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 20 }}>
        Compare today's actual matchups -- records, recent form, starting pitchers, bullpen, and (once posted) lineup splits.
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 24, flexWrap: 'wrap' }}>
        {loadingMatchups ? (
          <div style={{ color: theme.textSecondary, fontSize: 14 }}>Loading today's matchups...</div>
        ) : matchups.length === 0 ? (
          <div style={{ color: theme.textSecondary, fontSize: 14 }}>No games found for today yet.</div>
        ) : (
          <select
            value={selectedPk}
            onChange={(e) => setSelectedPk(e.target.value)}
            style={{ padding: '8px 12px', fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgCard, color: theme.textPrimary, minWidth: 280 }}
          >
            {matchups.map((m) => <option key={m.game_pk} value={m.game_pk}>{m.label}</option>)}
          </select>
        )}
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
            <TeamCard
              record={data.team_a}
              pitcher={data.team_a_pitcher}
              bullpen={data.team_a_bullpen}
              lineup={data.team_a_lineup_vs_b}
              hitting={data.team_a_hitting_vs_b}
              opponentPitcherName={data.team_b_pitcher?.pitcher}
            />
            <TeamCard
              record={data.team_b}
              pitcher={data.team_b_pitcher}
              bullpen={data.team_b_bullpen}
              lineup={data.team_b_lineup_vs_a}
              hitting={data.team_b_hitting_vs_a}
              opponentPitcherName={data.team_a_pitcher?.pitcher}
            />
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
        </>
      )}

      {!loading && !error && !data && !loadingMatchups && matchups.length > 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          Select a matchup above.
        </div>
      )}
    </div>
  );
}
