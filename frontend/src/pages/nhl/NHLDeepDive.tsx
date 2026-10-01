import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getNHLDeepDive } from '../../api/nhl';
import LoadingSpinner from '../../components/LoadingSpinner';
import SegmentedToggle from '../../components/SegmentedToggle';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';
import { Banner, Card, Empty, ErrorBox, GamePicker, PageShell } from './nhlShared';
import { td, th, useGamePicker } from './nhlUtils';

interface Zone { zone: string; label: string; for: number | null; against: number | null; league: number | null; for_diff: number | null; against_diff: number | null }
interface Quality { hd_share: number | null; avg_distance: number | null; rebounds_pg: number | null; rush_pg: number | null }
interface Dive {
  error?: string; game: { game_id: number; away: string; home: string; date: string };
  attacking: string; defending: string; strength: string; window: number; games_for: number; games_against: number;
  season: string; fallback: boolean; zones: Zone[];
  per_game: { for: number | null; against: number | null; league: number | null };
  quality: { for: Quality; against: Quality };
  periods: Record<string, Record<string, { for: number | null; against: number | null }>>;
  score_state: Record<string, { lead: number | null; tied: number | null; trail: number | null; share_leading: number | null }>;
}

// Bubble centres on a 400 x 340 half rink, net on the right. The shooter's
// left (+y in the data) is the top of the drawing.
const POS: Record<string, [number, number]> = {
  net_front: [344, 170], slot: [304, 170], high_slot: [248, 170], left_circle: [280, 90],
  right_circle: [280, 250], left_point: [120, 50], right_point: [120, 290], wide: [382, 300],
};

function Rink({ zones, side, title, perGame }: { zones: Zone[]; side: 'for' | 'against'; title: string; perGame: number | null }) {
  const diffKey = side === 'for' ? 'for_diff' : 'against_diff';
  const ranked = [...zones].filter((z) => z[diffKey] != null).sort((a, b) => Math.abs(b[diffKey]!) - Math.abs(a[diffKey]!));
  const labelled = new Set(ranked.slice(0, 3).map((z) => z.zone));
  return (
    <figure style={{ margin: 0, minWidth: 0 }}>
      <figcaption style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
        {title} <span style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 400 }}>· {perGame ?? '—'} per game</span>
      </figcaption>
      <svg viewBox="-10 -10 420 360" style={{ width: '100%', maxWidth: 520, height: 'auto', display: 'block' }} role="img"
        aria-label={`${title}: shot locations compared with league average`}>
        <path d="M0,0 H288 A112,112 0 0 1 400,112 V228 A112,112 0 0 1 288,340 H0 Z" fill="#11161d" stroke={theme.borderStrong} strokeWidth={2} />
        <line x1={100} y1={0} x2={100} y2={340} stroke={theme.borderStrong} strokeWidth={4} />
        <line x1={356} y1={18} x2={356} y2={322} stroke={theme.borderStrong} strokeWidth={2} />
        <circle cx={276} cy={82} r={60} fill="none" stroke={theme.borderStrong} strokeWidth={2} />
        <circle cx={276} cy={258} r={60} fill="none" stroke={theme.borderStrong} strokeWidth={2} />
        <path d="M356,146 A24,24 0 0 0 356,194" fill={theme.bgCardHover} stroke={theme.borderStrong} strokeWidth={2} />
        <rect x={356} y={158} width={12} height={24} fill="none" stroke={theme.textSecondary} strokeWidth={2} />
        {zones.map((z) => {
          const d = z[diffKey];
          const [cx, cy] = POS[z.zone] ?? [200, 170];
          if (d == null) return null;
          const r = Math.min(34, 6 + Math.abs(d) * 0.7);
          const more = d > 0;
          return (
            <g key={z.zone}>
              <circle cx={cx} cy={cy} r={r} fill={more ? 'rgba(107,168,240,0.55)' : 'rgba(244,87,63,0.5)'}
                stroke={more ? theme.dataBlue : theme.dataRed}>
                <title>{`${z.label}: ${z[side]} per game vs league ${z.league} (${d > 0 ? '+' : ''}${d}%)`}</title>
              </circle>
              {labelled.has(z.zone) && (
                <text x={cx} y={cy + r + 14} fill={theme.textPrimary} fontSize={12} textAnchor="middle">
                  {z.label} {d > 0 ? '+' : ''}{d}%
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

function summary(d: Dive): string | null {
  const z = Object.fromEntries(d.zones.map((x) => [x.zone, x]));
  const inside = (k: 'for_diff' | 'against_diff') =>
    ((z.slot?.[k] ?? 0) + (z.net_front?.[k] ?? 0)) / 2;
  const f = inside('for_diff'), a = inside('against_diff');
  if (Math.abs(f) < 5 && Math.abs(a) < 5) return null;
  const off = f >= 5 ? `${d.attacking} gets to the slot and net front more than most` : f <= -5 ? `${d.attacking} generates less than most from the slot and net front` : `${d.attacking} is about average from the slot`;
  const def = a <= -5 ? `${d.defending} keeps opponents out of those areas` : a >= 5 ? `${d.defending} gives up more than most there` : `${d.defending} is about average there`;
  return `${off}; ${def}.`;
}

export default function NHLDeepDive() {
  const { slate, gameId, setGameId, loading: slateLoading, error: slateError } = useGamePicker();
  const [attacking, setAttacking] = useState<'away' | 'home'>('away');
  const [strength, setStrength] = useState<'5v5' | 'pp' | 'all'>('5v5');
  const [data, setData] = useState<Dive | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    if (!gameId) return;
    setLoading(true); setError('');
    getNHLDeepDive(gameId, attacking, strength)
      .then((r) => { if (r.data.error) { setError(r.data.error); setData(null); } else setData(r.data); })
      .catch((e) => setError(e?.response?.data?.detail || 'Failed to load the deep dive.'))
      .finally(() => setLoading(false));
  }, [gameId, attacking, strength]);

  const game = slate?.games.find((g) => g.game_id === gameId);
  const awayName = data?.game.away ?? game?.away ?? 'Away';
  const homeName = data?.game.home ?? game?.home ?? 'Home';
  const note = data ? summary(data) : null;

  return (
    <PageShell title="Matchup Deep Dive"
      subtitle="Where each team's shots come from, against where the opponent gives them up — every unblocked shot attempt, by rink area, compared with the league average.">
      {slateError && <ErrorBox>{slateError}</ErrorBox>}
      <GamePicker slate={slate} gameId={gameId} onChange={setGameId} />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
        <SegmentedToggle value={attacking} onChange={setAttacking} fullWidth={isMobile}
          options={[{ value: 'away', label: `${awayName} attacking` }, { value: 'home', label: `${homeName} attacking` }]} />
        <SegmentedToggle value={strength} onChange={setStrength} fullWidth={isMobile}
          options={[{ value: '5v5', label: '5-on-5' }, { value: 'pp', label: 'Power play' }, { value: 'all', label: 'All' }]} />
      </div>
      {(slateLoading || loading) && <LoadingSpinner />}
      {error && <ErrorBox>{error}</ErrorBox>}
      {!slateLoading && slate && slate.games.length === 0 && !gameId && <Empty>No NHL games scheduled in the next two weeks.</Empty>}
      {data && !loading && (
        <>
          {data.fallback && <Banner>Early season — league averages use {data.season} until teams have 5 games.</Banner>}
          <Card style={{ marginBottom: 16 }} title={`Where the shots come from — last ${data.window} games`}
            aside={
              <span style={{ display: 'inline-flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}><span style={{ width: 12, height: 12, borderRadius: 6, background: 'rgba(107,168,240,0.6)', border: `1px solid ${theme.dataBlue}` }} />More than league average</span>
                <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}><span style={{ width: 12, height: 12, borderRadius: 6, background: 'rgba(244,87,63,0.55)', border: `1px solid ${theme.dataRed}` }} />Fewer</span>
                <span>Size = how far from average</span>
              </span>
            }>
            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 24 }}>
              <Rink zones={data.zones} side="for" title={`${data.attacking} shots for`} perGame={data.per_game.for} />
              <Rink zones={data.zones} side="against" title={`${data.defending} shots allowed`} perGame={data.per_game.against} />
            </div>
            {note && <div style={{ marginTop: 10, padding: '10px 14px', borderRadius: 8, background: theme.bgCardHover, fontSize: 13, lineHeight: 1.5 }}>{note}</div>}
            <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 8 }}>
              League average: {data.per_game.league ?? '—'} per team per game. Samples: {data.games_for} {data.attacking} games, {data.games_against} {data.defending} games.
            </div>
          </Card>

          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 16 }}>
            <Card title="Shot quality" style={{ padding: '12px 0 4px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Stat</th><th style={th}>{data.attacking} for</th><th style={th}>{data.defending} allowed</th></tr></thead>
                <tbody>
                  <tr><td style={td}>High-danger share</td><td style={td}>{data.quality.for.hd_share ?? '—'}%</td><td style={td}>{data.quality.against.hd_share ?? '—'}%</td></tr>
                  <tr><td style={td}>Average shot distance</td><td style={td}>{data.quality.for.avg_distance ?? '—'} ft</td><td style={td}>{data.quality.against.avg_distance ?? '—'} ft</td></tr>
                  <tr><td style={td}>Rebound shots per game</td><td style={td}>{data.quality.for.rebounds_pg ?? '—'}</td><td style={td}>{data.quality.against.rebounds_pg ?? '—'}</td></tr>
                  <tr><td style={td}>Rush shots per game</td><td style={td}>{data.quality.for.rush_pg ?? '—'}</td><td style={td}>{data.quality.against.rush_pg ?? '—'}</td></tr>
                </tbody>
              </table>
            </Card>
            <Card title="Goals by period, per game" style={{ padding: '12px 0 4px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Period</th>{Object.keys(data.periods).map((t) => <th key={t} style={th}>{t} for / against</th>)}</tr></thead>
                <tbody>
                  {[['p1', '1st'], ['p2', '2nd'], ['p3', '3rd'], ['ot', 'Overtime']].map(([k, l]) => (
                    <tr key={k}><td style={td}>{l}</td>
                      {Object.keys(data.periods).map((t) => <td key={t} style={td}>{data.periods[t][k]?.for ?? '—'} / {data.periods[t][k]?.against ?? '—'}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card title="Shots on goal per 60, by score" style={{ padding: '12px 0 4px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Game state</th>{Object.keys(data.score_state).map((t) => <th key={t} style={th}>{t}</th>)}</tr></thead>
                <tbody>
                  {[['lead', 'Leading'], ['tied', 'Tied'], ['trail', 'Trailing']].map(([k, l]) => (
                    <tr key={k}><td style={td}>{l}</td>
                      {Object.keys(data.score_state).map((t) => <td key={t} style={td}>{(data.score_state[t] as any)[k] ?? '—'}</td>)}
                    </tr>
                  ))}
                  <tr><td style={td}>Time spent leading</td>
                    {Object.keys(data.score_state).map((t) => <td key={t} style={td}>{data.score_state[t].share_leading ?? '—'}%</td>)}
                  </tr>
                </tbody>
              </table>
            </Card>
          </div>
          <div style={{ display: 'flex', gap: 16, fontSize: 13, marginTop: 14, flexWrap: 'wrap' }}>
            <Link to={`/nhl/team-matchup?game=${data.game.game_id}`} style={{ color: theme.accent }}>Team matchup →</Link>
            <Link to={`/nhl/lines?game=${data.game.game_id}`} style={{ color: theme.accent }}>Lines &amp; power play →</Link>
          </div>
        </>
      )}
    </PageShell>
  );
}
