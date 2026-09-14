import { useState, useEffect } from 'react';
import { getNFLUsageTeams, getNFLTeamUsage } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import SegmentedToggle from '../../components/SegmentedToggle';
import { positionColor, POSITION_COLORS, POSITION_OTHER } from '../../components/usageColors';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

type Split = 'all' | 'rz_' | 'third_';
type Metric = 'targets' | 'carries';

interface UsagePlayer {
  player: string;
  player_id: string;
  position?: string | null;
  [key: string]: any;
}

interface SliceTotals {
  targets: number;
  carries: number;
  touches: number;
  pass_pct: number | null;
}

interface UsageResponse {
  team: string;
  week: number | null;
  weeks_available: number[];
  splits_available: string[];
  totals: Record<string, SliceTotals>;
  players: UsagePlayer[];
}

const SPLIT_LABELS: Record<Split, string> = {
  all: 'All',
  rz_: 'Red Zone',
  third_: '3rd Down',
};

/** "" is how the backend prefixes the all-plays columns; "all" is how it
 *  names that slice in splits_available and totals. */
function colPrefix(split: Split): string {
  return split === 'all' ? '' : split;
}

function pct(v: number | null | undefined): string {
  return v == null || isNaN(v) ? '—' : `${(v * 100).toFixed(1)}%`;
}

export default function NFLTeamUsage() {
  const [teams, setTeams] = useState<string[]>([]);
  const [team, setTeam] = useState('');
  const [week, setWeek] = useState<number | 'season'>('season');
  const [split, setSplit] = useState<Split>('all');
  const [metric, setMetric] = useState<Metric>('targets');
  const [data, setData] = useState<UsageResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    getNFLUsageTeams()
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
    getNFLTeamUsage(team, week === 'season' ? undefined : week)
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load usage.'))
      .finally(() => setLoading(false));
  }, [team, week]);

  // Only offer a toggle the loaded file can actually answer. Until the
  // workflow reruns with the third-down split, that column set doesn't exist
  // and the option would silently return zeroes for everyone.
  const available: Split[] = (['all', 'rz_', 'third_'] as Split[]).filter(
    (s) => !data?.splits_available || data.splits_available.includes(s === 'all' ? 'all' : s)
  );
  const activeSplit = available.includes(split) ? split : 'all';

  const p = colPrefix(activeSplit);
  const countCol = `${p}${metric}`;
  const shareCol = metric === 'targets' ? `${p}target_share` : `${p}rush_share`;
  const yardCol = metric === 'targets' ? `${p}receiving_yards` : `${p}rushing_yards`;

  const rows = (data?.players ?? [])
    .map((pl) => ({
      player: pl.player,
      position: pl.position as string | null | undefined,
      count: Number(pl[countCol] ?? 0),
      share: Number(pl[shareCol] ?? 0),
      yards: Number(pl[yardCol] ?? 0),
    }))
    .filter((r) => r.count > 0)
    .sort((a, b) => b.count - a.count);

  const topShare = rows.length > 0 ? Math.max(...rows.map((r) => r.share)) : 0;
  const totals = data?.totals?.[activeSplit === 'all' ? 'all' : activeSplit];

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 900, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NFL Team Usage</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 18 }}>
        Who a team actually feeds. Bar length is each player's share of the team's
        targets or carries; colour is his position group.
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
          value={String(week)}
          onChange={(e) => setWeek(e.target.value === 'season' ? 'season' : Number(e.target.value))}
          style={{
            flex: isMobile ? '1 1 100%' : undefined, minHeight: 40, padding: '9px 12px',
            fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`,
            background: theme.bgCard, color: theme.textPrimary, boxSizing: 'border-box',
          }}
        >
          <option value="season">Season to date</option>
          {(data?.weeks_available ?? []).map((w) => <option key={w} value={w}>Week {w}</option>)}
        </select>
      </div>

      <SegmentedToggle
        value={metric}
        onChange={setMetric}
        fullWidth
        options={[{ value: 'targets', label: 'Targets' }, { value: 'carries', label: 'Carries' }]}
        style={{ marginBottom: 8 }}
      />

      {available.length > 1 && (
        <SegmentedToggle
          value={activeSplit}
          onChange={setSplit}
          fullWidth
          options={available.map((s) => ({ value: s, label: SPLIT_LABELS[s] }))}
          style={{ marginBottom: 14 }}
        />
      )}

      {totals && (
        <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 14, fontVariantNumeric: 'tabular-nums' }}>
          {totals.touches.toFixed(0)} touches
          {totals.pass_pct != null && <> · {totals.pass_pct}% through the air</>}
          <span style={{ color: theme.textMuted }}> · targets + carries by skill players, not team plays</span>
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
          No {metric} recorded for {team} in this split.
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
                      {r.position ?? '—'}
                    </span>
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>
                    {pct(r.share)}
                  </span>
                </div>
                {/* Scaled to the leader, not to 100% -- a 22% leader against a
                    full-width track leaves every bar a stub and the ordering
                    unreadable, which is the whole job of this chart. */}
                <div style={{ height: 9, background: theme.bgCard, borderRadius: '0 3px 3px 0' }}>
                  <div style={{
                    width: topShare > 0 ? `${Math.max((r.share / topShare) * 100, 1.5)}%` : '0%',
                    height: '100%', borderRadius: '0 3px 3px 0',
                    background: positionColor(r.position),
                  }} />
                </div>
                <div style={{ fontSize: 10.5, color: theme.textMuted, marginTop: 3, fontVariantNumeric: 'tabular-nums' }}>
                  {r.count.toFixed(0)} {metric}
                  {r.count > 0 && <> · {(r.yards / r.count).toFixed(1)} yds per</>}
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 14, fontSize: 11, color: theme.textSecondary }}>
            {Object.entries(POSITION_COLORS).map(([pos, color]) => (
              <span key={pos} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: color }} /> {pos}
              </span>
            ))}
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: POSITION_OTHER }} /> other
            </span>
          </div>
        </>
      )}
    </div>
  );
}
