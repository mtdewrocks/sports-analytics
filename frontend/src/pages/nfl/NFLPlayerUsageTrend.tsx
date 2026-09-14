import { useState, useEffect } from 'react';
import { getNFLPlayers, getNFLUsageTrend } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import SegmentedToggle from '../../components/SegmentedToggle';
import { TREND_SUBJECT, TREND_CONTEXT } from '../../components/usageColors';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

type Stat = 'targets' | 'carries' | 'air_yards';

interface Point { week: number; value: number; share: number; team_total: number; }
interface Teammate { player: string; series: { week: number; share: number }[]; }
interface TrendResponse {
  player: string;
  stat: Stat;
  team: string | null;
  position: string | null;
  weeks: number[];
  series: Point[];
  teammates: Teammate[];
}

const STAT_LABELS: Record<Stat, string> = {
  targets: 'Targets',
  carries: 'Carries',
  air_yards: 'Air yards',
};

const W = 320;   // viewBox units; the svg scales to its container
const H = 110;
const PAD_L = 4;
const PAD_R = 10;
const PAD_T = 10;
const PAD_B = 8;

export default function NFLPlayerUsageTrend() {
  const [players, setPlayers] = useState<string[]>([]);
  const [player, setPlayer] = useState('');
  const [stat, setStat] = useState<Stat>('targets');
  const [data, setData] = useState<TrendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    getNFLPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
  }, []);

  useEffect(() => {
    if (!player) return;
    setLoading(true);
    setError('');
    getNFLUsageTrend(player, stat)
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load trend.'))
      .finally(() => setLoading(false));
  }, [player, stat]);

  const weeks = data?.weeks ?? [];
  const series = data?.series ?? [];

  // One shared vertical scale across the subject and every teammate line, so
  // the comparison between them is honest. Headroom above the max keeps the
  // end label off the top edge.
  const maxShare = Math.max(
    0.01,
    ...series.map((p) => p.share),
    ...(data?.teammates ?? []).flatMap((t) => t.series.map((p) => p.share)),
  );
  const yMax = Math.min(1, maxShare * 1.18);

  const x = (week: number) => {
    if (weeks.length <= 1) return PAD_L;
    const i = weeks.indexOf(week);
    return PAD_L + (i / (weeks.length - 1)) * (W - PAD_L - PAD_R);
  };
  const y = (share: number) => PAD_T + (1 - share / yMax) * (H - PAD_T - PAD_B);
  const path = (pts: { week: number; share: number }[]) =>
    pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.week).toFixed(1)},${y(p.share).toFixed(1)}`).join(' ');

  const last = series.length > 0 ? series[series.length - 1] : null;
  const first = series.length > 0 ? series[0] : null;
  const maxVolume = Math.max(1, ...series.map((p) => p.team_total));

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 900, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NFL Player Usage Trend</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 18 }}>
        A player's share of his team's usage, week by week — with every teammate drawn
        behind him, because share is zero-sum and a rising line is only meaningful
        against whoever's falling.
      </div>

      <div style={{ marginBottom: 10 }}>
        <SearchDropdown
          players={players}
          value={player}
          onSelect={setPlayer}
          placeholder="Search by first or last name..."
          inputStyle={{ padding: '9px 10px', fontSize: 14 }}
        />
      </div>

      <SegmentedToggle
        value={stat}
        onChange={setStat}
        fullWidth
        options={(Object.keys(STAT_LABELS) as Stat[]).map((s) => ({ value: s, label: STAT_LABELS[s] }))}
        style={{ marginBottom: 16 }}
      />

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {!loading && !error && !player && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 50, fontSize: 15 }}>
          Pick a player to see how his share has moved.
        </div>
      )}

      {!loading && !error && player && series.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 50, fontSize: 15 }}>
          No usage recorded for {player}.
        </div>
      )}

      {!loading && !error && series.length > 0 && (
        <>
          <div style={{ fontSize: 13, color: theme.textPrimary, fontWeight: 700, marginBottom: 2 }}>
            {data?.player}
            <span style={{ color: theme.textMuted, fontWeight: 400, fontSize: 11, marginLeft: 6 }}>
              {data?.position ?? ''} {data?.team ?? ''}
            </span>
          </div>

          <div style={{ fontSize: 10, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '12px 0 3px' }}>
            Share of team {STAT_LABELS[stat].toLowerCase()}
          </div>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            style={{ display: 'block', width: '100%', height: 128 }}
            role="img"
            aria-label={`${data?.player} share of team ${stat} by week, against teammate lines`}
          >
            {[0.25, 0.5, 0.75, 1].map((f) => (
              <line key={f} x1={PAD_L} y1={y(yMax * f)} x2={W - PAD_R} y2={y(yMax * f)}
                    stroke={theme.border} strokeWidth="1" vectorEffect="non-scaling-stroke" />
            ))}
            {(data?.teammates ?? []).map((t) => (
              <path key={t.player} d={path(t.series)} fill="none" stroke={TREND_CONTEXT}
                    strokeWidth="2" vectorEffect="non-scaling-stroke" />
            ))}
            <path d={path(series)} fill="none" stroke={TREND_SUBJECT}
                  strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
            {last && <circle cx={x(last.week)} cy={y(last.share)} r="4"
                             fill={TREND_SUBJECT} stroke={theme.bgPage} strokeWidth="2" />}
          </svg>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: theme.textMuted, fontVariantNumeric: 'tabular-nums' }}>
            <span>{first ? `${(first.share * 100).toFixed(0)}%` : ''}</span>
            <span style={{ color: TREND_SUBJECT, fontWeight: 700 }}>{last ? `${(last.share * 100).toFixed(0)}%` : ''}</span>
          </div>

          {/* Volume gets its own panel sharing the week axis. Never a second
              y-axis on the plot above: the entire point of this page is that
              share and volume move independently, and overlaying them on one
              frame is what hides exactly that. */}
          <div style={{ fontSize: 10, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '14px 0 3px' }}>
            Team {STAT_LABELS[stat].toLowerCase()} that week
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 5, height: 52 }}>
            {series.map((p) => (
              <div
                key={p.week}
                title={`Week ${p.week}: ${p.team_total.toFixed(0)} team ${stat}`}
                style={{
                  flex: 1, background: TREND_CONTEXT, borderRadius: '2px 2px 0 0',
                  height: `${Math.max((p.team_total / maxVolume) * 100, 2)}%`,
                }}
              />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 5, fontSize: 9.5, color: theme.textMuted, marginTop: 3 }}>
            {series.map((p) => (
              <span key={p.week} style={{ flex: 1, textAlign: 'center' }}>W{p.week}</span>
            ))}
          </div>

          <div style={{ background: theme.bgCard, borderRadius: 8, padding: '12px 14px', marginTop: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: theme.textPrimary }}>
                Week {last?.week} read
              </span>
              <span style={{ fontSize: 20, fontWeight: 700, color: TREND_SUBJECT, fontVariantNumeric: 'tabular-nums' }}>
                {last ? `${(last.share * 100).toFixed(0)}%` : '—'}
              </span>
            </div>
            <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 5, fontVariantNumeric: 'tabular-nums' }}>
              {last?.value.toFixed(0)} of the team's {last?.team_total.toFixed(0)}.
              {first && last && (
                <>
                  {' '}Share {last.share >= first.share ? 'up' : 'down'} from {(first.share * 100).toFixed(0)}% in week {first.week},
                  on {last.team_total >= first.team_total ? 'higher' : 'lower'} team volume.
                </>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 14, marginTop: 12, fontSize: 11, color: theme.textSecondary }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 14, height: 2, background: TREND_SUBJECT }} /> {data?.player}
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 14, height: 2, background: TREND_CONTEXT }} /> teammates ({data?.teammates.length ?? 0})
            </span>
          </div>
        </>
      )}
    </div>
  );
}
