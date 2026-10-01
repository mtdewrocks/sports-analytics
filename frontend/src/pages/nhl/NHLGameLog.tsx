import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { getNHLGameLog, getNHLPlayers } from '../../api/nhl';
import FilterPanel from '../../components/FilterPanel';
import LoadingSpinner from '../../components/LoadingSpinner';
import OverCountsTable from '../../components/OverCountsTable';
import ScrollTable from '../../components/ScrollTable';
import SearchDropdown from '../../components/SearchDropdown';
import SegmentedToggle from '../../components/SegmentedToggle';
import StatCard from '../../components/StatCard';
import { fieldLabelStyle, fieldStyle, usePanelLayout } from '../../components/filterStyles';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';
import { Banner, Card, ErrorBox, Pill } from './nhlShared';
import { fmtDate, fmtSv, fmtTime, pctColor, rankColor, rankWords, roleLabel, signed, td, th } from './nhlUtils';

interface PlayerOpt { id: number; label: string; player: string; team: string; pos: string; is_goalie: boolean }
interface Game {
  game_id: number; date: string; game_date: string; opponent: string; opp: string;
  stat_value: number | null; result: 'W' | 'L'; team_result: string; score: string;
  tooltip: { score: string }; toi: string | null; b2b: boolean; playoffs: boolean;
  // skater
  sog?: number; attempts?: number; pp_toi?: string | null; pp_unit?: string | null; line?: string | null;
  linemates?: string | null; opp_goalie?: string | null; opp_goalie_backup?: boolean; ixg?: number | null;
  // goalie
  shots_against?: number; saves?: number; goals_against?: number; save_pct?: number | null;
  decision?: string | null; gsax?: number | null;
  opp_rank?: number | null; opp_rank_label?: string | null;
}
interface OverCount { over: number; total: number; pct: number }
interface Split { label: string; n: number; avg: number | null; over: number; pct: number }
interface Projection { player_id: number | null; name: string | null; status: string; reason: string; is_backup?: boolean }
interface NextGame {
  game_id: number; date: string; start_utc: string | null; label: string; opp: string; is_home: boolean;
  stats_season: string; fallback: boolean;
  opp_goalie?: Projection; projection?: Projection; projected_to_start?: boolean;
  opponent?: { shots_pg: number | null; shots_pg_rank: string | null; shots_allowed_pg: number | null; shots_allowed_rank: number | null; pp_opps_pg: number | null };
  pos_group?: string; shots_allowed_to_pos?: number | null; shots_allowed_to_pos_rank?: string | null;
  role?: { line: string | null; pp_unit: string | null; linemates: string | null; as_of: string };
}
interface LogData {
  error?: string;
  player: { id: number; name: string; team: string; pos: string; is_goalie: boolean };
  stat: string; stat_label: string; season: number; season_label: string; fallback: boolean;
  seasons_available: number[]; threshold: number;
  games: Game[]; over_counts: Record<string, OverCount>; splits: Split[]; next_game: NextGame | null;
}

const SKATER_STATS = [
  ['sog', 'Shots on goal'], ['points', 'Points'], ['goals', 'Goals'], ['assists', 'Assists'],
  ['pp_points', 'Power-play points'], ['attempts', 'Shot attempts'], ['blocks', 'Blocked shots'],
  ['hits', 'Hits'], ['toi_min', 'Time on ice (minutes)'],
];
const GOALIE_STATS = [['saves', 'Saves'], ['shots_against', 'Shots faced'], ['goals_against', 'Goals against'],
  ['save_pct', 'Save %']];
const DEFAULT_LINE: Record<string, string> = {
  sog: '2.5', points: '0.5', goals: '0.5', assists: '0.5', pp_points: '0.5', attempts: '4.5', blocks: '1.5',
  hits: '1.5', toi_min: '18', saves: '25.5', shots_against: '27.5', goals_against: '2.5', save_pct: '0.9',
};

function seasonLabel(s: number) { return `${Math.floor(s / 10000)}-${String(s % 10000).slice(2)}`; }

/** Bars for the stat, with a second row under each bar: time on ice and a
 *  dot for games on the first power-play unit (skaters), or shots faced
 *  (goalies). A short bar without a dot is a role change, not a slump. */
function RoleTick(props: any) {
  const { x, y, payload, games, goalie } = props;
  const g: Game | undefined = games[payload.index];
  if (!g) return null;
  return (
    <g transform={`translate(${x},${y})`}>
      <text x={0} y={10} textAnchor="middle" fontSize={10} fill={theme.textSecondary}>{g.game_date}</text>
      <text x={0} y={22} textAnchor="middle" fontSize={9} fill={theme.textMuted}>{g.opponent}</text>
      <text x={0} y={35} textAnchor="middle" fontSize={9} fill={theme.textSecondary}>
        {goalie ? `${g.shots_against ?? '—'} SA` : g.toi ?? ''}
      </text>
      {!goalie && (
        <circle cx={0} cy={44} r={3} fill={g.pp_unit === 'PP1' ? theme.textPrimary : 'none'}
          stroke={g.pp_unit === 'PP1' ? theme.textPrimary : theme.textMuted} />
      )}
    </g>
  );
}

function ChartTip({ active, payload, goalie }: any) {
  if (!active || !payload?.length) return null;
  const g: Game = payload[0].payload;
  return (
    <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 4, padding: '8px 12px', fontSize: 12 }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{fmtDate(g.date)} {g.opponent}</div>
      <div>Value: {g.stat_value}</div>
      <div style={{ color: theme.textSecondary }}>{g.team_result} {g.score}</div>
      {goalie ? (
        <div style={{ color: theme.textSecondary }}>{g.shots_against} shots faced · {fmtSv(g.save_pct)}</div>
      ) : (
        <>
          <div style={{ color: theme.textSecondary }}>Time on ice {g.toi} · power play {g.pp_toi ?? '—'}</div>
          <div style={{ color: theme.textSecondary }}>{[g.line, g.pp_unit].filter(Boolean).join(' · ') || 'Role unknown'}</div>
        </>
      )}
    </div>
  );
}

function RoleChart({ games, threshold, goalie }: { games: Game[]; threshold: number; goalie: boolean }) {
  const isMobile = useIsMobile();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (isMobile && ref.current) ref.current.scrollLeft = ref.current.scrollWidth; }, [isMobile, games]);
  const data = games.map((g, i) => ({ ...g, index: i, v: g.stat_value ?? 0 }));
  const chart = (width?: number) => (
    <BarChart width={width} height={width ? 250 : undefined} data={data} margin={{ top: 20, right: 12, left: isMobile ? 0 : 4, bottom: 44 }}>
      <CartesianGrid strokeOpacity={0} />
      <XAxis dataKey="index" interval={0} tickLine={false} axisLine={{ stroke: theme.border }}
        tick={<RoleTick games={games} goalie={goalie} />} />
      <YAxis hide={isMobile} axisLine={{ stroke: theme.border }} tickLine={false} width={32}
        tick={{ fontSize: 11, fill: theme.textSecondary }} />
      <Tooltip content={<ChartTip goalie={goalie} />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
      <ReferenceLine y={threshold} stroke={theme.dataRed} strokeDasharray="5 5"
        label={{ value: `Line: ${threshold}`, fill: theme.dataRed, fontSize: 11, position: 'insideTopRight' }} />
      <Bar dataKey="v" radius={[3, 3, 0, 0]} maxBarSize={30}
        label={{ position: 'top', fontSize: 10, fill: theme.textSecondary }}>
        {data.map((g, i) => <Cell key={i} fill={g.v > threshold ? theme.dataBlue : theme.dataRed} />)}
      </Bar>
    </BarChart>
  );
  if (isMobile) {
    return (
      <div ref={ref} style={{ overflowX: 'auto' }}>
        <div style={{ width: Math.max(8, games.length) * 44 }}>{chart(Math.max(8, games.length) * 44)}</div>
      </div>
    );
  }
  return <ResponsiveContainer width="100%" height={300}>{chart()}</ResponsiveContainer>;
}

function NextGameCard({ ng, goalie }: { ng: NextGame; goalie: boolean }) {
  const isMobile = useIsMobile();
  const o = ng.opponent;
  const cols = isMobile ? 'repeat(2, minmax(0, 1fr))' : 'repeat(4, minmax(0, 1fr))';
  const proj = goalie ? ng.projection : ng.opp_goalie;
  return (
    <Card style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <span style={{ fontSize: 11, letterSpacing: 0.5, textTransform: 'uppercase', color: theme.accent, fontWeight: 700 }}>Next game</span>
        <span style={{ fontSize: 15, fontWeight: 600 }}>{fmtDate(ng.date)} · {ng.label} · {fmtTime(ng.start_utc)}</span>
        <Link to={`/nhl/team-matchup?game=${ng.game_id}`} style={{ marginLeft: 'auto', fontSize: 13, color: theme.accent }}>Team matchup →</Link>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 14 }}>
        <div>
          <div style={{ fontSize: 12, color: theme.textSecondary }}>{goalie ? 'Projected starter' : 'Opposing goalie'}</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginTop: 2 }}>{proj?.name ?? '—'}</div>
          <div style={{ marginTop: 4, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            {proj && <Pill kind={proj.status}>{proj.status}</Pill>}
            {goalie && ng.projected_to_start === false && <Pill kind="warn">Not projected to start</Pill>}
            {!goalie && proj?.is_backup && <Pill kind="warn">Backup</Pill>}
          </div>
          <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 3 }}>{proj?.reason}</div>
        </div>
        {goalie ? (
          <div>
            <div style={{ fontSize: 12, color: theme.textSecondary }}>{ng.opp} shots per game</div>
            <div style={{ fontSize: 14, fontWeight: 600, marginTop: 2 }}>{o?.shots_pg ?? '—'} · {o?.shots_pg_rank} most</div>
            <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 3 }}>{o?.pp_opps_pg ?? '—'} power plays per game</div>
          </div>
        ) : (
          <div>
            <div style={{ fontSize: 12, color: theme.textSecondary }}>{ng.opp} shots allowed per game</div>
            <div style={{ fontSize: 14, fontWeight: 600, marginTop: 2 }}>
              {o?.shots_allowed_pg ?? '—'}{' '}
              <span style={{ color: rankColor(o?.shots_allowed_rank != null ? 33 - o.shots_allowed_rank : null) }}>
                · {rankWords(o?.shots_allowed_rank, 'fewest')}
              </span>
            </div>
            {ng.shots_allowed_to_pos != null && (
              <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 3 }}>
                to {ng.pos_group}: {ng.shots_allowed_to_pos} per game ({ng.shots_allowed_to_pos_rank} fewest)
              </div>
            )}
          </div>
        )}
        {!goalie && (
          <div>
            <div style={{ fontSize: 12, color: theme.textSecondary }}>Role in last game</div>
            <div style={{ fontSize: 14, fontWeight: 600, marginTop: 2 }}>
              {[roleLabel(ng.role?.line), ng.role?.pp_unit].filter(Boolean).join(' · ') || '—'}
            </div>
            {ng.role?.linemates && <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 3 }}>with {ng.role.linemates}</div>}
          </div>
        )}
        <div>
          <div style={{ fontSize: 12, color: theme.textSecondary }}>Opponent stats</div>
          <div style={{ fontSize: 13, marginTop: 2 }}>{ng.stats_season} season{ng.fallback ? ' (last season until 5 games)' : ''}</div>
          <Link to={`/nhl/lines?game=${ng.game_id}`} style={{ fontSize: 12, color: theme.accent }}>Lines &amp; power play →</Link>
        </div>
      </div>
    </Card>
  );
}

export default function NHLGameLog() {
  const [players, setPlayers] = useState<PlayerOpt[]>([]);
  const [label, setLabel] = useState('');
  const [stat, setStat] = useState('sog');
  const [line, setLine] = useState('2.5');
  const [season, setSeason] = useState<number | null>(null);
  const [homeAway, setHomeAway] = useState('all');
  const [ppRole, setPpRole] = useState('all');
  const [minToi, setMinToi] = useState('');
  const [oppGoalie, setOppGoalie] = useState('all');
  const [rest, setRest] = useState('all');
  const [startsOnly, setStartsOnly] = useState(true);
  const [data, setData] = useState<LogData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tableScope, setTableScope] = useState<'last10' | 'season'>('last10');
  const [chartScope, setChartScope] = useState<'last20' | 'season'>('last20');
  const isMobile = useIsMobile();
  const panelLayout = usePanelLayout();
  const [params] = useSearchParams();
  const [autoFetch, setAutoFetch] = useState(false);

  useEffect(() => {
    getNHLPlayers().then((r) => {
      const list: PlayerOpt[] = Array.isArray(r.data) ? r.data : [];
      setPlayers(list);
      // linked from another page (e.g. the Goalie Report): /nhl/game-log?player=<id>
      const pid = Number(params.get('player'));
      const hit = pid ? list.find((p) => p.id === pid) : undefined;
      if (hit) {
        setLabel(hit.label);
        const s = hit.is_goalie ? 'saves' : 'sog';
        setStat(s); setLine(DEFAULT_LINE[s]);
        setAutoFetch(true);
      }
    }).catch(() => setPlayers([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const selected = useMemo(() => players.find((p) => p.label === label) ?? null, [players, label]);
  const isGoalie = !!selected?.is_goalie;
  const statOptions = isGoalie ? GOALIE_STATS : SKATER_STATS;

  // switching between a skater and a goalie resets the stat to one that exists
  useEffect(() => {
    const keys = statOptions.map(([k]) => k);
    if (!keys.includes(stat)) { setStat(keys[0]); setLine(DEFAULT_LINE[keys[0]]); }
    setSeason(null);
  }, [selected?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchLog = async () => {
    if (!selected) return;
    setLoading(true); setError(''); setData(null);
    try {
      const params: Record<string, any> = {
        player_id: selected.id, stat, threshold: parseFloat(line) || 0, home_away: homeAway, rest,
      };
      if (season) params.season = season;
      if (isGoalie) params.starts_only = startsOnly;
      else {
        params.pp_role = ppRole; params.opp_goalie = oppGoalie;
        if (parseFloat(minToi) > 0) params.min_toi = parseFloat(minToi);
      }
      const res = await getNHLGameLog(params);
      if (res.data.error) setError(res.data.error);
      else setData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to fetch game log.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (autoFetch && selected) { setAutoFetch(false); fetchLog(); }
  }, [autoFetch, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  const threshold = data?.threshold ?? (parseFloat(line) || 0);
  const chartGames = data ? (chartScope === 'last20' ? data.games.slice(-20) : data.games) : [];
  const tableGames = data ? [...(tableScope === 'last10' ? data.games.slice(-10) : data.games)].reverse() : [];
  const goalie = !!data?.player.is_goalie;
  const seg = (value: string, set: (v: string) => void, options: [string, string][]) => (
    <div style={{ marginBottom: 16 }}>
      <SegmentedToggle fullWidth size="sm" value={value} onChange={set}
        options={options.map(([v, l]) => ({ value: v, label: l }))} />
    </div>
  );

  return (
    <div style={panelLayout}>
      <FilterPanel
        title="NHL Game Log"
        moreLabel="Home/away, role, rest"
        action={{ label: 'Get Stats', onClick: fetchLog, disabled: !selected || loading }}
        more={
          <>
            <label style={fieldLabelStyle}>Home / Away</label>
            {seg(homeAway, setHomeAway, [['all', 'All'], ['home', 'Home'], ['away', 'Away']])}
            <label style={fieldLabelStyle}>Rest</label>
            {seg(rest, setRest, [['all', 'All'], ['b2b', 'Back-to-back'], ['rested', 'Not B2B']])}
            {isGoalie ? (
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 16, cursor: 'pointer' }}>
                <input type="checkbox" checked={startsOnly} onChange={(e) => setStartsOnly(e.target.checked)} />
                Starts only (leave out relief appearances)
              </label>
            ) : (
              <>
                <label style={fieldLabelStyle}>Power-play role</label>
                {seg(ppRole, setPpRole, [['all', 'All'], ['pp1', 'PP1 only'], ['not_pp1', 'Not PP1']])}
                <label style={fieldLabelStyle}>Opposing goalie</label>
                {seg(oppGoalie, setOppGoalie, [['all', 'All'], ['starter', 'Starter'], ['backup', 'Backup']])}
                <label style={fieldLabelStyle} htmlFor="nhl-toi">Minimum time on ice (minutes)</label>
                <input id="nhl-toi" type="number" min={0} max={30} step={1} style={fieldStyle} placeholder="e.g. 17"
                  value={minToi} onChange={(e) => setMinToi(e.target.value)} />
              </>
            )}
          </>
        }
      >
        {data && data.seasons_available.length > 1 && (
          <>
            <label style={fieldLabelStyle}>Season</label>
            {seg(String(season ?? data.season), (v) => setSeason(Number(v)),
              data.seasons_available.map((s) => [String(s), seasonLabel(s)] as [string, string]))}
          </>
        )}
        <label style={fieldLabelStyle}>Player</label>
        <div style={{ marginBottom: 16 }}>
          <SearchDropdown players={players.map((p) => p.label)} value={label} onSelect={setLabel}
            placeholder="Search skaters and goalies..." inputStyle={{ padding: 8 }} />
        </div>
        <label style={fieldLabelStyle} htmlFor="nhl-stat">Stat</label>
        <select id="nhl-stat" style={fieldStyle} value={stat}
          onChange={(e) => { setStat(e.target.value); setLine(DEFAULT_LINE[e.target.value] ?? line); }}>
          {statOptions.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <label style={fieldLabelStyle} htmlFor="nhl-line">Line</label>
        <input id="nhl-line" type="number" step={0.5} style={fieldStyle} value={line}
          onFocus={(e) => e.target.select()} onChange={(e) => setLine(e.target.value)} />
      </FilterPanel>

      <div style={{ flex: 1, padding: isMobile ? 16 : 24, overflowY: 'auto', background: theme.bgPage, minWidth: 0 }}>
        {loading && <LoadingSpinner />}
        {error && <ErrorBox>{error}</ErrorBox>}
        {!loading && !error && !data && (
          <div style={{ color: theme.textSecondary, marginTop: 60, textAlign: 'center', fontSize: 16 }}>
            Pick a skater or goalie and click "Get Stats".
          </div>
        )}
        {!loading && data && (
          <>
            {data.fallback && (
              <Banner>
                Showing {data.season_label} — {data.player.name} has fewer than 5 games this season. Switch seasons
                in the filters once he does.
              </Banner>
            )}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
              <h2 style={{ margin: 0, color: theme.textPrimary }}>{data.player.name}</h2>
              <span style={{ color: theme.textSecondary, fontSize: 14 }}>
                {data.player.team} · {data.season_label} · {data.stat_label} · Line {threshold}
              </span>
            </div>

            {data.next_game && <NextGameCard ng={data.next_game} goalie={goalie} />}

            <Card title={`${data.stat_label} by game`} style={{ marginBottom: 16 }}
              aside={
                <SegmentedToggle size="sm" value={chartScope} onChange={setChartScope}
                  options={[{ value: 'last20', label: 'Last 20' }, { value: 'season', label: 'Season' }]} />
              }>
              {data.games.length === 0 ? (
                <div style={{ color: theme.textSecondary, fontSize: 13 }}>No games match these filters.</div>
              ) : (
                <>
                  <RoleChart games={chartGames} threshold={threshold} goalie={goalie} />
                  <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 4 }}>
                    {goalie
                      ? 'Under each bar: shots faced.'
                      : 'Under each bar: time on ice. A filled dot means he was on the first power-play unit — a low bar without one is a role change, not a slump.'}
                  </div>
                </>
              )}
            </Card>

            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 16, marginBottom: 16 }}>
              <Card style={{ paddingTop: 2 }}>
                <OverCountsTable over_counts={data.over_counts} threshold={threshold} stat={data.stat_label}
                  periods={[
                    { key: 'last5', label: 'Last 5' }, { key: 'last10', label: 'Last 10' },
                    { key: 'last20', label: 'Last 20' }, { key: 'season', label: 'Season' },
                    ...(goalie ? [] : [{ key: 'pp1', label: 'Season, first-unit power play games' }]),
                  ]} />
              </Card>
              <Card title="Splits (season, before filters)">
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr><th style={th}>Split</th><th style={th}>Games</th><th style={th}>Average</th><th style={th}>Over {threshold}</th></tr></thead>
                  <tbody>
                    {data.splits.map((s) => (
                      <tr key={s.label}>
                        <td style={{ ...td, whiteSpace: 'normal' }}>{s.label}</td><td style={td}>{s.n}</td>
                        <td style={td}>{goalie && data.stat === 'save_pct' ? fmtSv(s.avg) : s.avg}</td>
                        <td style={{ ...td, fontWeight: 700, color: pctColor(s.pct) }}>{Math.round(s.pct * 100)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </div>

            <Card title="Game by game" aside={
              <SegmentedToggle size="sm" value={tableScope} onChange={setTableScope}
                options={[{ value: 'last10', label: 'Last 10' }, { value: 'season', label: 'Season' }]} />
            }>
              {isMobile ? (
                <div>
                  {tableGames.map((g) => (
                    <StatCard key={g.game_id} title={`${fmtDate(g.date, false)} · ${g.opponent}`}
                      titleAside={`${g.team_result} ${g.score}`}
                      value={goalie && data.stat === 'save_pct' ? fmtSv(g.stat_value) : g.stat_value}
                      valueColor={(g.stat_value ?? 0) > threshold ? theme.dataBlue : theme.dataRed}
                      meta={goalie ? [
                        `Shots faced ${g.shots_against}`, `Goals against ${g.goals_against}`,
                        `Save % ${fmtSv(g.save_pct)}`, g.gsax != null ? `Saved vs expected ${signed(g.gsax)}` : null,
                      ] : [
                        `Time on ice ${g.toi}`, `Power play ${g.pp_toi ?? '—'}`, g.pp_unit ?? 'No PP unit',
                        g.line ? `Line ${g.line}` : null,
                      ]}
                      metaSecondary={goalie ? [g.opp_rank_label ? `${g.opp}: ${g.opp_rank_label}` : null] : [
                        `Shot attempts ${g.attempts}`, g.opp_goalie ? `vs ${g.opp_goalie}${g.opp_goalie_backup ? ' (backup)' : ''}` : null,
                        g.opp_rank_label ? `${g.opp} shots allowed: ${g.opp_rank_label}` : null,
                      ]}
                    />
                  ))}
                </div>
              ) : (
                <ScrollTable>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      {goalie ? (
                        <tr>
                          <th style={th}>Date</th><th style={th}>Opponent</th><th style={th}>Result</th>
                          <th style={th}>{data.stat_label}</th><th style={th}>Shots faced</th><th style={th}>Saves</th>
                          <th style={th}>Goals against</th><th style={th}>Save %</th><th style={th}>Saved vs expected</th>
                          <th style={th}>Opponent shot rank</th><th style={th}>Back-to-back</th>
                        </tr>
                      ) : (
                        <tr>
                          <th style={th}>Date</th><th style={th}>Opponent</th><th style={th}>Result</th>
                          <th style={th}>{data.stat_label}</th><th style={th}>Shot attempts</th><th style={th}>Time on ice</th>
                          <th style={th}>Power-play time</th><th style={th}>Unit</th><th style={th}>Line</th>
                          <th style={th}>Linemates</th><th style={th}>Opposing goalie</th><th style={th}>Opponent shots allowed</th>
                        </tr>
                      )}
                    </thead>
                    <tbody>
                      {tableGames.map((g) => {
                        const over = (g.stat_value ?? 0) > threshold;
                        const val = goalie && data.stat === 'save_pct' ? fmtSv(g.stat_value) : g.stat_value;
                        const resColor = g.team_result === 'W' ? theme.dataBlue : g.team_result === 'L' ? theme.dataRed : theme.textSecondary;
                        return goalie ? (
                          <tr key={g.game_id}>
                            <td style={td}>{fmtDate(g.date, false)}{g.playoffs ? ' · Playoffs' : ''}</td>
                            <td style={td}>{g.opponent}</td>
                            <td style={{ ...td, color: resColor, fontWeight: 600 }}>{g.team_result} {g.score}</td>
                            <td style={{ ...td, fontWeight: 700, color: over ? theme.dataBlue : theme.dataRed }}>{val}</td>
                            <td style={td}>{g.shots_against}</td><td style={td}>{g.saves}</td><td style={td}>{g.goals_against}</td>
                            <td style={td}>{fmtSv(g.save_pct)}</td>
                            <td style={{ ...td, color: (g.gsax ?? 0) >= 0 ? theme.dataBlue : theme.dataRed }}>{signed(g.gsax)}</td>
                            <td style={td}>{g.opp_rank_label ?? '—'}</td>
                            <td style={td}>{g.b2b ? 'Yes' : ''}</td>
                          </tr>
                        ) : (
                          <tr key={g.game_id}>
                            <td style={td}>{fmtDate(g.date, false)}{g.playoffs ? ' · Playoffs' : ''}</td>
                            <td style={td}>{g.opponent}</td>
                            <td style={{ ...td, color: resColor, fontWeight: 600 }}>{g.team_result} {g.score}</td>
                            <td style={{ ...td, fontWeight: 700, color: over ? theme.dataBlue : theme.dataRed }}>{val}</td>
                            <td style={td}>{g.attempts}</td><td style={td}>{g.toi}</td><td style={td}>{g.pp_toi ?? '—'}</td>
                            <td style={td}>{g.pp_unit ?? '—'}</td><td style={td}>{g.line ?? '—'}</td>
                            <td style={{ ...td, color: theme.textSecondary }}>{g.linemates ?? '—'}</td>
                            <td style={td}>{g.opp_goalie ?? '—'}{g.opp_goalie_backup ? <span style={{ color: theme.warningText }}> (backup)</span> : ''}</td>
                            {/* few shots allowed = a tough matchup for a shooter, so the scale is flipped */}
                            <td style={{ ...td, color: rankColor(g.opp_rank ? 33 - g.opp_rank : null) }}>{g.opp_rank_label ?? '—'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </ScrollTable>
              )}
            </Card>
            <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 10 }}>
              Lines and power-play units come from each game's shift chart (who was actually on the ice together).
              Data: NHL public API, updated each morning.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

