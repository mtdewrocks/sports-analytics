import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getNHLLines } from '../../api/nhl';
import LoadingSpinner from '../../components/LoadingSpinner';
import SegmentedToggle from '../../components/SegmentedToggle';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';
import { Card, Empty, ErrorBox, GamePicker, PageShell, Pill } from './nhlShared';
import { fmtDate, roleLabel, useGamePicker } from './nhlUtils';

interface Unit {
  unit: string; players: string; player_ids: number[]; games_together: number; minutes_together: number | null;
  gf: number; ga: number; shot_share: number | null; notes: string[]; changed: boolean;
}
interface TeamLines {
  team: string; as_of?: string; units: Unit[]; note?: string; prior_season?: boolean;
  out_since_last?: { player: string; was: string }[];
  goalie?: { name: string | null; status: string; reason: string };
}
interface MatchRow { team: string; unit: string; players: string | null; opp: string; opp_unit: string; opp_players: string | null; share: number | null }
interface LinesData {
  error?: string; game: { game_id: number; away: string; home: string; date: string }; mode: string;
  teams: TeamLines[]; matchups: { game_id: number; date: string; home: string | null; rows: MatchRow[] } | null;
}

const GROUPS: [string, string][] = [['L', 'Forward lines'], ['D', 'Defense pairs'], ['P', 'Power play']];

function TeamColumn({ t }: { t: TeamLines }) {
  const isMobile = useIsMobile();
  return (
    <Card style={{ padding: '10px 0 8px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '4px 16px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 17, fontWeight: 700 }}>{t.team}</span>
        {t.as_of && <span style={{ fontSize: 12, color: theme.textSecondary }}>as of {fmtDate(t.as_of, false)}</span>}
        {t.goalie?.name && (
          <span style={{ marginLeft: 'auto', fontSize: 12, color: theme.textSecondary }}>
            Goalie: {t.goalie.name} <Pill kind={t.goalie.status}>{t.goalie.status}</Pill>
          </span>
        )}
      </div>
      {t.note && <div style={{ padding: '8px 16px', fontSize: 13, color: theme.textSecondary }}>{t.note}</div>}
      {t.prior_season && (
        <div style={{ margin: '6px 16px 2px', padding: '8px 10px', borderRadius: 6, fontSize: 12, background: 'rgba(232,163,61,0.12)', color: theme.warningText }}>
          From last season's final game — this updates after {t.team}'s first game of the season.
        </div>
      )}
      {GROUPS.map(([k, title]) => {
        const units = t.units.filter((u) => u.unit.startsWith(k));
        if (!units.length) return null;
        return (
          <div key={k}>
            <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.6, color: theme.accent, fontWeight: 700, padding: '12px 16px 4px' }}>{title}</div>
            {units.map((u) => (
              <div key={u.unit} style={{
                display: 'grid', gridTemplateColumns: isMobile ? '40px minmax(0,1fr)' : '44px minmax(0,1fr) 190px',
                gap: 10, alignItems: 'center', padding: '8px 16px', borderBottom: `1px solid ${theme.border}`,
              }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: theme.textSecondary }}>{u.unit}</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{u.players}</div>
                  {u.notes.map((n) => (
                    <div key={n} style={{ fontSize: 11, color: theme.warningText, marginTop: 2, display: 'flex', gap: 5, alignItems: 'center' }}>
                      <span style={{ width: 7, height: 7, borderRadius: 4, background: theme.warningText, flexShrink: 0 }} />{n}
                    </div>
                  ))}
                  {isMobile && <UnitStats u={u} />}
                </div>
                {!isMobile && <UnitStats u={u} right />}
              </div>
            ))}
          </div>
        );
      })}
      {t.out_since_last && t.out_since_last.length > 0 && (
        <div style={{ padding: '10px 16px 2px', fontSize: 12, color: theme.textSecondary }}>
          Played the game before but not the last one: {t.out_since_last.map((o) => `${o.player} (${roleLabel(o.was)})`).join(', ')}
        </div>
      )}
    </Card>
  );
}

function UnitStats({ u, right }: { u: Unit; right?: boolean }) {
  const pp = u.unit.startsWith('PP');
  return (
    <div style={{ fontSize: 12, color: theme.textSecondary, textAlign: right ? 'right' : 'left', lineHeight: 1.4, marginTop: right ? 0 : 3 }}>
      {u.minutes_together ?? 0} min together{pp ? ' on the power play' : ''} · {u.games_together} of last 10 games<br />
      <span style={{ color: theme.textPrimary }}>
        Goals {u.gf}–{u.ga}{u.shot_share != null ? ` · shot share ${u.shot_share}%` : ''}
      </span>
    </div>
  );
}

export default function NHLLines() {
  const { slate, gameId, setGameId, loading: slateLoading, error: slateError } = useGamePicker();
  const [mode, setMode] = useState<'last' | 'common'>('last');
  const [data, setData] = useState<LinesData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    if (!gameId) return;
    setLoading(true); setError('');
    getNHLLines(gameId, mode)
      .then((r) => { if (r.data.error) { setError(r.data.error); setData(null); } else setData(r.data); })
      .catch((e) => setError(e?.response?.data?.detail || 'Failed to load lines.'))
      .finally(() => setLoading(false));
  }, [gameId, mode]);

  return (
    <PageShell title="Lines & Power Play"
      subtitle="Built from each game's shift chart, so it shows who actually played together — not a projected lineup. Lines and pairs are 5-on-5; minutes, goals and shot share are for that exact group over each team's last 10 games. Amber notes flag changes since the game before.">
      {slateError && <ErrorBox>{slateError}</ErrorBox>}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <GamePicker slate={slate} gameId={gameId} onChange={setGameId} />
        <div style={{ marginBottom: 16, marginLeft: isMobile ? 0 : 'auto', width: isMobile ? '100%' : undefined }}>
          <SegmentedToggle value={mode} onChange={setMode} fullWidth={isMobile}
            options={[{ value: 'last', label: 'Last game' }, { value: 'common', label: 'Most common, last 5' }]} />
        </div>
      </div>
      {(slateLoading || loading) && <LoadingSpinner />}
      {error && <ErrorBox>{error}</ErrorBox>}
      {!slateLoading && slate && slate.games.length === 0 && !gameId && <Empty>No NHL games scheduled in the next two weeks.</Empty>}
      {data && !loading && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 16, alignItems: 'start', marginBottom: 16 }}>
            {data.teams.map((t) => <TeamColumn key={t.team} t={t} />)}
          </div>
          {data.matchups && data.matchups.rows.length > 0 && (
            <Card title="Who played against whom" aside={`Last meeting, ${fmtDate(data.matchups.date, false)}${data.matchups.home ? ` at ${data.matchups.home} (home team gets last change)` : ''}`}>
              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
                {data.matchups.rows.map((r, i) => (
                  <div key={i} style={{ background: theme.bgCardHover, borderRadius: 8, padding: '10px 12px' }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{r.team} {roleLabel(r.unit)} vs {r.opp} {roleLabel(r.opp_unit)}</div>
                    <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 4, lineHeight: 1.45 }}>
                      {r.share != null ? `${r.share}% of their 5-on-5 time. ` : ''}{r.players} faced {r.opp_players}.
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
          <div style={{ display: 'flex', gap: 16, fontSize: 13, marginTop: 14, flexWrap: 'wrap' }}>
            <Link to={`/nhl/team-matchup?game=${data.game.game_id}`} style={{ color: theme.accent }}>Team matchup →</Link>
            <Link to={`/nhl/deep-dive?game=${data.game.game_id}`} style={{ color: theme.accent }}>Deep dive →</Link>
          </div>
        </>
      )}
    </PageShell>
  );
}
