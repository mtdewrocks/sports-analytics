import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getNHLScheduleSpots } from '../../api/nhl';
import LoadingSpinner from '../../components/LoadingSpinner';
import ScrollTable from '../../components/ScrollTable';
import StatCard from '../../components/StatCard';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';
import { Card, Empty, ErrorBox, KV, PageShell, Pill } from './nhlShared';
import { fmtDate, td, th } from './nhlUtils';

interface SpotRow {
  game_id: number; game: string; team: string; opp: string;
  rest_days: number | null; b2b: boolean; spot: string; tone: string; games_last6: number;
  travel: number | null; tz_shift: number | null; trip_game: number; trip_len: number; first_game: boolean;
  goalie: string | null; goalie_status: string | null; goalie_backup: boolean; history: string | null;
}
interface Edge { game: string; tag: string; tone: string; head: string; body: string }
interface Trend { season: string; games: number; win_pct: number | null; ga_vs_avg: number | null; backup_pct: number | null; six_plus_pct: number | null }
interface Spots { error?: string; date: string; is_today: boolean; rows: SpotRow[]; edges: Edge[]; trend: Trend | null; history_season: string }

function tz(v: number | null): string {
  if (!v) return '—';
  return `${Math.abs(v)} ${v > 0 ? 'east' : 'west'}`;
}
function trip(r: SpotRow): string {
  return r.trip_game ? `Game ${r.trip_game} of ${r.trip_len}` : 'Home';
}
function rest(r: SpotRow): string {
  return r.first_game ? 'First game' : r.rest_days == null ? '—' : String(r.rest_days);
}

export default function NHLScheduleSpots() {
  const [data, setData] = useState<Spots | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    getNHLScheduleSpots()
      .then((r) => { if (r.data.error) setError(r.data.error); else setData(r.data); })
      .catch((e) => setError(e?.response?.data?.detail || 'Failed to load schedule spots.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <PageShell title="Schedule Spots"
      subtitle="Rest, travel and back-to-backs for every team on the slate. Tired teams give up more goals, and the second night of a back-to-back is when backup goalies start.">
      {loading && <LoadingSpinner />}
      {error && <ErrorBox>{error}</ErrorBox>}
      {data && (
        <>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>{data.is_today ? 'Tonight' : fmtDate(data.date)}</div>
          {data.rows.length === 0 && <Empty>No games on this date.</Empty>}

          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14, marginBottom: 16 }}>
            {data.edges.map((e) => (
              <Card key={e.game + e.tag}>
                <div style={{ fontSize: 12, color: theme.textSecondary }}>{e.game}</div>
                <div style={{ fontSize: 15, fontWeight: 600, marginTop: 4 }}>{e.head}</div>
                <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 6, lineHeight: 1.45 }}>{e.body}</div>
                <div style={{ marginTop: 10 }}><Pill kind={e.tone}>{e.tag}</Pill></div>
              </Card>
            ))}
            {data.trend && (
              <Card title={`Second night of a back-to-back vs a rested team, ${data.trend.season}`}>
                <KV k="Win rate" v={data.trend.win_pct != null ? `${data.trend.win_pct}%` : '—'} />
                <KV k="Goals allowed vs their average" v={data.trend.ga_vs_avg != null ? `${data.trend.ga_vs_avg > 0 ? '+' : ''}${data.trend.ga_vs_avg}` : '—'} />
                <KV k="Backup goalie started" v={data.trend.backup_pct != null ? `${data.trend.backup_pct}%` : '—'} />
                <KV k="Six or more total goals" v={data.trend.six_plus_pct != null ? `${data.trend.six_plus_pct}%` : '—'} />
                <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 6 }}>{data.trend.games} games</div>
              </Card>
            )}
          </div>

          {data.rows.length > 0 && (isMobile ? (
            <div>
              {data.rows.map((r) => (
                <StatCard key={`${r.game_id}-${r.team}`} title={<span><b>{r.team}</b> · {r.game}</span>}
                  value={<Pill kind={r.tone}>{r.spot}</Pill>}
                  meta={[`Rest ${rest(r)}`, r.travel ? `${Math.round(r.travel)} mi` : null, r.tz_shift ? `${tz(r.tz_shift)} time zone` : null, trip(r)]}
                  metaSecondary={[r.goalie ? `Goalie: ${r.goalie}${r.goalie_backup ? ' (backup)' : ''}` : null,
                    r.history ? `Last season in this spot: ${r.history}` : null]} />
              ))}
            </div>
          ) : (
            <Card style={{ padding: '6px 0 4px' }} title={<span style={{ paddingLeft: 16 }}>Every team</span>}
              aside={<span style={{ paddingRight: 16 }}>Travel = arena-to-arena miles since the last game</span>}>
              <ScrollTable>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr>
                    <th style={th}>Game</th><th style={th}>Team</th><th style={th}>Days of rest</th><th style={th}>Spot</th>
                    <th style={th}>Games, last 6 days</th><th style={th}>Travel</th><th style={th}>Time zones</th>
                    <th style={th}>Road trip</th><th style={th}>Projected goalie</th>
                    <th style={th}>In this spot, {data.history_season}</th>
                  </tr></thead>
                  <tbody>
                    {data.rows.map((r, i) => (
                      <tr key={`${r.game_id}-${r.team}`} style={i % 2 === 0 ? { borderTop: `2px solid ${theme.borderStrong}` } : undefined}>
                        <td style={td}>{i % 2 === 0 ? <Link to={`/nhl/team-matchup?game=${r.game_id}`} style={{ color: theme.accent }}>{r.game}</Link> : ''}</td>
                        <td style={{ ...td, fontWeight: 600 }}>{r.team}</td>
                        <td style={td}>{rest(r)}</td>
                        <td style={td}><Pill kind={r.tone}>{r.spot}</Pill></td>
                        <td style={td}>{r.games_last6}</td>
                        <td style={td}>{r.travel ? `${Math.round(r.travel)} mi` : '—'}</td>
                        <td style={td}>{tz(r.tz_shift)}</td>
                        <td style={td}>{trip(r)}</td>
                        <td style={td}>{r.goalie ?? '—'}{r.goalie_backup ? <span style={{ color: theme.warningText }}> (backup)</span> : ''}</td>
                        <td style={{ ...td, color: theme.textSecondary }}>{r.history ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ScrollTable>
            </Card>
          ))}
        </>
      )}
    </PageShell>
  );
}
