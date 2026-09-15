import { useState, useEffect } from 'react';
import { getNBATeams, getNBATeamUsage } from '../../api/nba';
import LoadingSpinner from '../../components/LoadingSpinner';
import SegmentedToggle from '../../components/SegmentedToggle';
import { STARTER_COLOR, BENCH_COLOR } from '../../components/usageColors';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

type Metric = 'fga' | 'pts' | 'min';
type Scope = 'season' | 'l10';

interface UsagePlayer {
  player: string;
  role: 'starter' | 'bench';
  value: number;
  share: number;
  games: number;
}

interface UsageResponse {
  team: string;
  metric: Metric;
  scope: Scope;
  team_total: number;
  starter_share: number;
  players: UsagePlayer[];
}

const METRIC_OPTIONS: { value: Metric; label: string }[] = [
  { value: 'fga', label: 'Shot Attempts' },
  { value: 'pts', label: 'Points' },
  { value: 'min', label: 'Minutes' },
];

const METRIC_LABEL: Record<Metric, string> = {
  fga: 'shot attempts',
  pts: 'points',
  min: 'minutes',
};

export default function NBATeamUsage() {
  const [teams, setTeams] = useState<string[]>([]);
  const [team, setTeam] = useState('');
  const [scope, setScope] = useState<Scope>('season');
  const [metric, setMetric] = useState<Metric>('fga');
  const [data, setData] = useState<UsageResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    getNBATeams()
      .then((res) => {
        setTeams(res.data);
        if (res.data.length > 0) setTeam(res.data[0]);
      })
      .catch(() => setTeams([]));
  }, []);

  useEffect(() => {
    if (!team) return;
    setLoading(true);
    setError('');
    getNBATeamUsage(team, metric, scope)
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load usage.'))
      .finally(() => setLoading(false));
  }, [team, metric, scope]);

  const rows = data?.players ?? [];
  const topValue = rows.length > 0 ? Math.max(...rows.map((r) => r.value)) : 0;

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 900, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NBA Team Usage</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 18 }}>
        Who a team actually runs through. Bar length is each player's share of the team's
        shots, points, or minutes.
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <select
          value={team}
          onChange={(e) => setTeam(e.target.value)}
          style={{
            flex: isMobile ? '1 1 100%' : undefined, minHeight: 40, padding: '9px 12px',
            fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`,
            background: theme.bgCard, color: theme.textPrimary, boxSizing: 'border-box',
          }}
        >
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value as Scope)}
          style={{
            flex: isMobile ? '1 1 100%' : undefined, minHeight: 40, padding: '9px 12px',
            fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`,
            background: theme.bgCard, color: theme.textPrimary, boxSizing: 'border-box',
          }}
        >
          <option value="season">Season to date</option>
          <option value="l10">Last 10 games</option>
        </select>
      </div>

      <SegmentedToggle
        value={metric}
        onChange={setMetric}
        fullWidth
        options={METRIC_OPTIONS}
        style={{ marginBottom: 14 }}
      />

      {data && rows.length > 0 && (
        <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 14, fontVariantNumeric: 'tabular-nums' }}>
          {data.team_total.toFixed(1)} team {METRIC_LABEL[metric]}/game &middot;{' '}
          {Math.round(data.starter_share * 100)}% by starters
          <span style={{ color: theme.textMuted }}> &middot; rotation players only</span>
        </div>
      )}

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {!loading && !error && rows.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40, fontSize: 15 }}>
          No {METRIC_LABEL[metric]} recorded for {team} in this split.
        </div>
      )}

      {!loading && !error && rows.length > 0 && (
        <>
          <div>
            {rows.map((r) => (
              <div key={r.player} style={{ marginBottom: 11 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
                  <span style={{ fontSize: 13, color: theme.textPrimary, fontWeight: 600 }}>
                    {r.player}
                    <span style={{ color: theme.textMuted, fontSize: 11, marginLeft: 6, fontWeight: 400 }}>
                      {r.role === 'starter' ? 'Starter' : 'Bench'}
                    </span>
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>
                    {(r.share * 100).toFixed(1)}%
                  </span>
                </div>
                {/* Scaled to the leader, not to 100% -- see NFLTeamUsage for the
                    same reasoning: a 22% leader against a full-width track
                    leaves every bar a stub and the ordering unreadable. */}
                <div style={{ height: 9, background: theme.bgCard, borderRadius: '0 3px 3px 0' }}>
                  <div style={{
                    width: topValue > 0 ? `${Math.max((r.value / topValue) * 100, 1.5)}%` : '0%',
                    height: '100%', borderRadius: '0 3px 3px 0',
                    background: r.role === 'starter' ? STARTER_COLOR : BENCH_COLOR,
                  }} />
                </div>
                <div style={{ fontSize: 10.5, color: theme.textMuted, marginTop: 3, fontVariantNumeric: 'tabular-nums' }}>
                  {r.value.toFixed(1)} {METRIC_LABEL[metric]} &middot; {r.games} game{r.games === 1 ? '' : 's'}
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 16, marginTop: 18, fontSize: 11, color: theme.textSecondary }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: STARTER_COLOR }} /> Starter
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: BENCH_COLOR }} /> Bench
            </span>
          </div>

          <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 18, paddingTop: 14, borderTop: `1px solid ${theme.border}`, lineHeight: 1.55 }}>
            Starter/bench is inferred from minutes rank, not a roster pull -- the box-score file
            this reads doesn't carry position or depth-chart data, so this page can't color by
            position the way the NFL one does (yet).
          </div>
        </>
      )}
    </div>
  );
}
