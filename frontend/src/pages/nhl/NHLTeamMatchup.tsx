import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getNHLMatchup } from '../../api/nhl';
import LoadingSpinner from '../../components/LoadingSpinner';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';
import { Banner, Card, Empty, ErrorBox, GamePicker, KV, PageShell, Pill } from './nhlShared';
import { STEEL, fmtDate, fmtSv, fmtTime, ordinal, rankColor, signed, useGamePicker } from './nhlUtils';

interface Goalie {
  player_id: number | null; name: string | null; status: string; reason: string; is_backup?: boolean;
  form: { last5_sv?: number | null; last5_gsax?: number | null; season_sv?: number | null; season_gsax?: number | null;
    season_starts?: number; season_label?: string | null; vs_opp_sv?: number | null; vs_opp_starts?: number };
}
interface Sched {
  rest_days?: number | null; b2b?: boolean; spot?: string; tone?: string; travel?: number | null;
  trip_game?: number; trip_len?: number; first_game?: boolean; games_last6?: number;
}
interface TeamBlock {
  team: string; name: string; record: string | null; last10: string; goalie: Goalie; schedule: Sched;
  injuries: { player: string; position: string | null; status: string; detail: string | null }[];
}
interface Row { key: string; label: string; graded: boolean; away: string | null; away_rank: number | null; home: string | null; home_rank: number | null; edge: string | null }
interface Matchup {
  error?: string;
  game: { game_id: number; away: string; home: string; date: string; start_utc: string | null; venue: string | null };
  season: string; fallback: boolean; away: TeamBlock; home: TeamBlock;
  sections: { title: string; rows: Row[] }[];
  special_teams: { team: string; opp: string; pp_pct: number | null; pp_rank: string; pk_pct: number | null; pk_rank: string; edge: string; expected_pp: number | null }[];
  totals: { label: string; away: string | null; home: string | null }[];
  head_to_head: { date: string; season: string; venue: string; winner: string; score: string }[];
}

function EdgeBar({ a, h }: { a: number | null; h: number | null }) {
  if (a == null || h == null) return null;
  const gap = Math.abs(a - h);
  const lead = Math.min(50, 8 + gap * 1.6);
  const aw = a < h ? 50 + lead / 2 : a > h ? 50 - lead / 2 : 50;
  return (
    <div style={{ width: '100%', maxWidth: 220, height: 5, borderRadius: 3, background: theme.border, display: 'flex', overflow: 'hidden' }}>
      <div style={{ width: `${aw}%`, background: a < h ? STEEL : theme.borderStrong }} />
      <div style={{ width: `${100 - aw}%`, background: h < a ? STEEL : theme.borderStrong }} />
    </div>
  );
}

function GoalieCard({ t }: { t: TeamBlock }) {
  const g = t.goalie;
  const f = g.form ?? {};
  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 12, color: theme.textSecondary }}>{t.team} starting goalie</span>
        <span style={{ marginLeft: 'auto' }}><Pill kind={g.status}>{g.status}</Pill></span>
      </div>
      <div style={{ fontSize: 16, fontWeight: 600, marginTop: 6 }}>{g.name ?? '—'}</div>
      <div style={{ fontSize: 12, color: g.is_backup ? theme.warningText : theme.textSecondary, marginTop: 2 }}>{g.reason}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8, marginTop: 12 }}>
        <div><div style={{ fontSize: 11, color: theme.textSecondary }}>Save % (last 5)</div><div style={{ fontSize: 15, fontWeight: 600 }}>{fmtSv(f.last5_sv)}</div></div>
        <div><div style={{ fontSize: 11, color: theme.textSecondary }}>Saved vs expected ({f.season_label ?? 'season'})</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: f.season_gsax == null ? theme.textPrimary : f.season_gsax >= 0 ? theme.dataBlue : theme.dataRed }}>{signed(f.season_gsax)}</div></div>
        <div><div style={{ fontSize: 11, color: theme.textSecondary }}>vs this team</div><div style={{ fontSize: 15, fontWeight: 600 }}>{f.vs_opp_starts ? fmtSv(f.vs_opp_sv) : '—'}</div></div>
      </div>
    </Card>
  );
}

function schedWords(s: Sched): string {
  if (!s || s.first_game) return 'First game of the season';
  const bits = [s.rest_days != null ? `${s.rest_days} day${s.rest_days === 1 ? '' : 's'} of rest` : null];
  if (s.trip_game) bits.push(`road game ${s.trip_game} of ${s.trip_len}`);
  if (s.travel) bits.push(`${Math.round(s.travel)} miles of travel`);
  return bits.filter(Boolean).join(' · ');
}

export default function NHLTeamMatchup() {
  const { slate, gameId, setGameId, loading: slateLoading, error: slateError } = useGamePicker();
  const [data, setData] = useState<Matchup | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    if (!gameId) return;
    setLoading(true); setError('');
    getNHLMatchup(gameId)
      .then((r) => { if (r.data.error) { setError(r.data.error); setData(null); } else setData(r.data); })
      .catch((e) => setError(e?.response?.data?.detail || 'Failed to load the matchup.'))
      .finally(() => setLoading(false));
  }, [gameId]);

  const a = data?.away, h = data?.home;

  return (
    <PageShell title="NHL Team Matchup">
      {slateError && <ErrorBox>{slateError}</ErrorBox>}
      <GamePicker slate={slate} gameId={gameId} onChange={setGameId} />
      {(slateLoading || loading) && <LoadingSpinner />}
      {error && <ErrorBox>{error}</ErrorBox>}
      {!slateLoading && slate && slate.games.length === 0 && !gameId && <Empty>No NHL games scheduled in the next two weeks.</Empty>}

      {data && a && h && !loading && (
        <>
          {data.fallback && <Banner>Early season — team stats are {data.season} until teams have 5 games. Ranks are out of 32.</Banner>}

          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'minmax(0,1fr) auto minmax(0,1fr)', alignItems: 'center', gap: isMobile ? 10 : 24 }}>
              <div>
                <div style={{ fontSize: isMobile ? 16 : 24, fontWeight: 700 }}>{a.name}</div>
                <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 4 }}>{a.record ?? '—'} · Last 10: {a.last10} · Away</div>
              </div>
              {!isMobile && (
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: 1 }}>{a.team} <span style={{ color: theme.textSecondary, fontWeight: 400 }}>@</span> {h.team}</div>
                  <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 6 }}>{fmtDate(data.game.date)} · {fmtTime(data.game.start_utc)}{data.game.venue ? ` · ${data.game.venue}` : ''}</div>
                </div>
              )}
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: isMobile ? 16 : 24, fontWeight: 700 }}>{h.name}</div>
                <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 4 }}>{h.record ?? '—'} · Last 10: {h.last10} · Home</div>
              </div>
            </div>
            {isMobile && <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 8 }}>{fmtDate(data.game.date)} · {fmtTime(data.game.start_utc)}{data.game.venue ? ` · ${data.game.venue}` : ''}</div>}
          </Card>

          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 16, marginBottom: 16 }}>
            <GoalieCard t={a} />
            <GoalieCard t={h} />
            <Card title="Schedule spot">
              {[a, h].map((t) => (
                <div key={t.team} style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 600 }}>{t.team}</span>
                    {t.schedule.spot && <Pill kind={t.schedule.tone ?? 'neutral'}>{t.schedule.spot}</Pill>}
                  </div>
                  <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 3 }}>{schedWords(t.schedule)}</div>
                </div>
              ))}
              <KV k="Home last change" v={h.team} />
              <Link to={`/nhl/schedule-spots`} style={{ fontSize: 12, color: theme.accent }}>All schedule spots →</Link>
            </Card>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(0, 1.6fr) minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
            <Card style={{ padding: '6px 0 4px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '70px minmax(0,1fr) 70px' : '110px 56px minmax(0,1fr) 56px 110px', gap: 8, padding: '8px 16px', borderBottom: `1px solid ${theme.borderStrong}`, fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, color: theme.textSecondary, fontWeight: 600 }}>
                <span>{a.team}</span>{!isMobile && <span>Rank</span>}<span style={{ textAlign: 'center' }}>Stat</span>{!isMobile && <span style={{ textAlign: 'right' }}>Rank</span>}<span style={{ textAlign: 'right' }}>{h.team}</span>
              </div>
              {data.sections.map((sec) => (
                <div key={sec.title}>
                  <div style={{ padding: '12px 16px 6px', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.6, color: theme.accent, fontWeight: 700, borderBottom: `1px solid ${theme.border}` }}>{sec.title}</div>
                  {sec.rows.map((r) => (
                    <div key={r.key} style={{ display: 'grid', gridTemplateColumns: isMobile ? '70px minmax(0,1fr) 70px' : '110px 56px minmax(0,1fr) 56px 110px', gap: 8, alignItems: 'center', padding: '9px 16px', borderBottom: `1px solid ${theme.border}`, fontSize: 13 }}>
                      <span>
                        <span style={{ fontWeight: 600, fontSize: 14 }}>{r.away ?? '—'}</span>
                        {isMobile && <span style={{ display: 'block', fontSize: 11, color: rankColor(r.away_rank, r.graded) }}>{ordinal(r.away_rank)}</span>}
                      </span>
                      {!isMobile && <span style={{ fontSize: 12, fontWeight: 600, color: rankColor(r.away_rank, r.graded) }}>{ordinal(r.away_rank)}</span>}
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, textAlign: 'center' }}>
                        <span>{r.label}</span>
                        {r.graded && <EdgeBar a={r.away_rank} h={r.home_rank} />}
                        <span style={{ fontSize: 11, color: theme.textSecondary }}>{r.graded ? (r.edge === 'Even' ? 'Even' : r.edge ? `${r.edge} edge` : '') : 'Style stat'}</span>
                      </div>
                      {!isMobile && <span style={{ textAlign: 'right', fontSize: 12, fontWeight: 600, color: rankColor(r.home_rank, r.graded) }}>{ordinal(r.home_rank)}</span>}
                      <span style={{ textAlign: 'right' }}>
                        <span style={{ fontWeight: 600, fontSize: 14 }}>{r.home ?? '—'}</span>
                        {isMobile && <span style={{ display: 'block', fontSize: 11, color: rankColor(r.home_rank, r.graded) }}>{ordinal(r.home_rank)}</span>}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
              <div style={{ padding: '10px 16px', fontSize: 11, color: theme.textSecondary }}>
                {data.season} regular season. Rank colour: top 10 blue, bottom 10 red. Expected goals come from this site's own model.
              </div>
            </Card>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <Card title="Special teams clash">
                {data.special_teams.filter((s) => s.team).map((s) => (
                  <div key={s.team} style={{ padding: '10px 12px', borderRadius: 8, background: theme.bgCardHover, marginBottom: 10 }}>
                    <KV k={`${s.team} power play`} v={`${s.pp_pct ?? '—'}% · ${s.pp_rank}`} />
                    <KV k={`${s.opp} penalty kill`} v={`${s.pk_pct ?? '—'}% · ${s.pk_rank}`} />
                    <div style={{ fontSize: 12, fontWeight: 600, marginTop: 4, color: s.edge === 'Even' ? theme.textSecondary : theme.dataBlue }}>
                      {s.edge === 'Even' ? 'Even' : `Edge: ${s.edge}`}
                    </div>
                  </div>
                ))}
                <div style={{ fontSize: 12, color: theme.textSecondary }}>
                  Expected power plays: {data.special_teams.map((s) => `${s.team} ${s.expected_pp ?? '—'}`).join(' · ')}
                  {' '}(chances drawn vs the opponent's times shorthanded)
                </div>
              </Card>

              <Card title="Totals and first period" aside={data.season}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead><tr>
                    <th style={{ textAlign: 'left', fontSize: 11, color: theme.textSecondary, fontWeight: 600, padding: '4px 0' }}>In their games</th>
                    <th style={{ textAlign: 'right', fontSize: 11, color: theme.textSecondary, fontWeight: 600 }}>{a.team}</th>
                    <th style={{ textAlign: 'right', fontSize: 11, color: theme.textSecondary, fontWeight: 600 }}>{h.team}</th>
                  </tr></thead>
                  <tbody>
                    {data.totals.map((t) => (
                      <tr key={t.label}>
                        <td style={{ padding: '6px 0', borderTop: `1px solid ${theme.border}` }}>{t.label}</td>
                        <td style={{ textAlign: 'right', borderTop: `1px solid ${theme.border}` }}>{t.away ?? '—'}</td>
                        <td style={{ textAlign: 'right', borderTop: `1px solid ${theme.border}` }}>{t.home ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>

              <Card title="Head-to-head" aside="last two seasons">
                {data.head_to_head.length === 0 ? (
                  <div style={{ fontSize: 13, color: theme.textSecondary }}>No meetings yet.</div>
                ) : data.head_to_head.map((g) => (
                  <KV key={g.date} k={`${new Date(`${g.date}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} · at ${g.venue}`} v={`${g.winner} ${g.score}`} />
                ))}
              </Card>

              <Card title="Injuries">
                {[a, h].map((t) => (
                  <div key={t.team} style={{ marginBottom: 8 }}>
                    {t.injuries.length === 0 ? <KV k={t.team} v="None reported" /> : t.injuries.map((i) => (
                      <div key={i.player} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 13, padding: '3px 0' }}>
                        <span>{t.team} · {i.player}{i.position ? ` (${i.position})` : ''}</span>
                        <Pill kind={/out|ir/i.test(i.status) ? 'tired' : 'neutral'}>{i.status}</Pill>
                      </div>
                    ))}
                  </div>
                ))}
              </Card>

              <div style={{ display: 'flex', gap: 16, fontSize: 13, flexWrap: 'wrap' }}>
                <Link to={`/nhl/lines?game=${data.game.game_id}`} style={{ color: theme.accent }}>Lines &amp; power play →</Link>
                <Link to={`/nhl/deep-dive?game=${data.game.game_id}`} style={{ color: theme.accent }}>Deep dive →</Link>
                <Link to="/nhl/goalie-report" style={{ color: theme.accent }}>Goalie report →</Link>
              </div>
            </div>
          </div>
        </>
      )}
    </PageShell>
  );
}
