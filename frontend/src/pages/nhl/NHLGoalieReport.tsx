import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getNHLGoalieReport } from '../../api/nhl';
import ChipRow from '../../components/ChipRow';
import LoadingSpinner from '../../components/LoadingSpinner';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';
import { Banner, Card, Empty, ErrorBox, KV, PageShell, Pill } from './nhlShared';
import { fmtDate, fmtSv, fmtTime, groupTitle, signed } from './nhlUtils';

interface GoalieCardData {
  team: string; opp: string; is_home: boolean; player_id: number | null; name: string | null;
  status: string; reason: string; is_backup?: boolean;
  form: {
    last5_sv?: number | null; last5_gsax?: number | null; last5_faced?: number | null; last5_saves?: number[];
    season_sv?: number | null; season_gsax?: number | null; season_starts?: number; season_label?: string | null;
    vs_opp_sv?: number | null; vs_opp_starts?: number;
  };
  opponent: { shots_pg?: number | null; shots_pg_rank?: string | null; cf5_p60?: number | null; cf5_p60_rank?: string | null; pp_opps_pg?: number | null };
}
interface ReportGame { game_id: number; label: string; start_utc: string | null; state: string | null; goalies: GoalieCardData[] }
interface Report {
  error?: string; date: string; is_today: boolean; season: string; fallback: boolean;
  counts: Record<string, number>; games: ReportGame[];
}

const gsaxColor = (v?: number | null) => (v == null ? theme.textPrimary : v >= 0 ? theme.dataBlue : theme.dataRed);

function GoalieCard({ g }: { g: GoalieCardData }) {
  const isMobile = useIsMobile();
  const f = g.form ?? {};
  const o = g.opponent ?? {};
  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{g.name ?? 'Unknown'}</div>
          <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 2 }}>{g.team} · {g.is_home ? 'Home' : 'Away'} vs {g.opp}</div>
        </div>
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <Pill kind={g.status}>{g.status}</Pill>
          <div style={{ fontSize: 11, color: g.is_backup ? theme.warningText : theme.textSecondary, marginTop: 4, maxWidth: 190 }}>{g.reason}</div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: isMobile ? 0 : 16 }}>
        <div>
          <div style={groupTitle}>Form · last 5 starts</div>
          <KV k="Save %" v={fmtSv(f.last5_sv)} />
          <KV k="Saved vs expected" v={signed(f.last5_gsax)} vStyle={{ color: gsaxColor(f.last5_gsax), fontWeight: 600 }} />
          <KV k="Shots faced per game" v={f.last5_faced ?? '—'} />
        </div>
        <div>
          <div style={groupTitle}>Season{f.season_label ? ` · ${f.season_label}` : ''}</div>
          <KV k="Save %" v={fmtSv(f.season_sv)} />
          <KV k="Saved vs expected" v={signed(f.season_gsax)} vStyle={{ color: gsaxColor(f.season_gsax), fontWeight: 600 }} />
          <KV k={`vs ${g.opp}`} v={f.vs_opp_starts ? `${fmtSv(f.vs_opp_sv)} in ${f.vs_opp_starts}` : '—'} />
        </div>
        <div>
          <div style={groupTitle}>{g.opp} shot volume</div>
          <KV k="Shots per game" v={o.shots_pg != null ? `${o.shots_pg} · ${o.shots_pg_rank} most` : '—'} />
          <KV k="5-on-5 attempts per 60" v={o.cf5_p60 != null ? `${o.cf5_p60} · ${o.cf5_p60_rank}` : '—'} />
          <KV k="Power plays per game" v={o.pp_opps_pg ?? '—'} />
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, borderTop: `1px solid ${theme.border}`, marginTop: 12, paddingTop: 10, fontSize: 13, flexWrap: 'wrap' }}>
        <span style={{ color: theme.textSecondary, fontSize: 12 }}>
          Saves, last 5: {f.last5_saves && f.last5_saves.length ? f.last5_saves.join(', ') : '—'}
        </span>
        {g.player_id && (
          <Link to={`/nhl/game-log?player=${g.player_id}`} style={{ marginLeft: 'auto', color: theme.accent, padding: '6px 0' }}>Goalie game log →</Link>
        )}
      </div>
    </Card>
  );
}

export default function NHLGoalieReport() {
  const [data, setData] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const isMobile = useIsMobile();

  useEffect(() => {
    getNHLGoalieReport()
      .then((r) => { if (r.data.error) setError(r.data.error); else setData(r.data); })
      .catch((e) => setError(e?.response?.data?.detail || 'Failed to load the goalie report.'))
      .finally(() => setLoading(false));
  }, []);

  const games = (data?.games ?? []).map((g) => ({
    ...g,
    goalies: g.goalies.filter((c) => filter === 'all' || (filter === 'confirmed' ? c.status === 'Confirmed'
      : filter === 'backup' ? c.is_backup : c.status === 'Projected')),
  })).filter((g) => g.goalies.length);

  return (
    <PageShell
      title="Goalie Report"
      subtitle={<>
        Every starting goalie on the slate, with form, the shot volume he's about to face, and his recent saves.
        Starters are <b>projected</b> from each team's rotation (recent starts and back-to-backs) and switch to
        {' '}<b>confirmed</b> once the game starts — morning-skate announcements aren't in the free data yet.
      </>}
    >
      {loading && <LoadingSpinner />}
      {error && <ErrorBox>{error}</ErrorBox>}
      {data && (
        <>
          {data.fallback && <Banner>Early season — opponent shot numbers are {data.season} until teams have 5 games.</Banner>}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>{data.is_today ? 'Tonight' : fmtDate(data.date)}</span>
            <span style={{ fontSize: 13, color: theme.textSecondary }}>
              {data.games.length} game{data.games.length === 1 ? '' : 's'} · Confirmed {data.counts.Confirmed ?? 0} · Projected {data.counts.Projected ?? 0}
            </span>
          </div>
          <ChipRow value={filter} onChange={setFilter} style={{ marginBottom: 16 }} chips={[
            { key: 'all', label: 'All goalies' }, { key: 'projected', label: 'Projected' },
            { key: 'confirmed', label: 'Confirmed' }, { key: 'backup', label: 'Backups projected' },
          ]} />
          {games.length === 0 && <Empty>No goalies match that filter.</Empty>}
          {games.map((g) => (
            <section key={g.game_id} style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 15, fontWeight: 700 }}>{g.label}</span>
                <span style={{ fontSize: 12, color: theme.textSecondary }}>{fmtTime(g.start_utc)}</span>
                <Link to={`/nhl/team-matchup?game=${g.game_id}`} style={{ marginLeft: 'auto', fontSize: 13, color: theme.accent }}>Team matchup →</Link>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
                {g.goalies.map((c) => <GoalieCard key={c.team} g={c} />)}
              </div>
            </section>
          ))}
        </>
      )}
    </PageShell>
  );
}
