import { useState, useEffect, useRef } from 'react';
import {
  getMLBGameLogAllPlayers, getMLBGameLog, getMLBPitcherGameLog,
} from '../../api/mlb';
import StatChart from '../../components/StatChart';
import OverCountsTable from '../../components/OverCountsTable';
import StatCard from '../../components/StatCard';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import SegmentedToggle from '../../components/SegmentedToggle';
import FilterPanel from '../../components/FilterPanel';
import { fieldLabelStyle, fieldStyle, usePanelLayout } from '../../components/filterStyles';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

// Same FilterPanel / usePanelLayout / StatChart / OverCountsTable pieces the
// NBA and NFL Game Log pages are built on. The Player search is a single
// combined batter+pitcher list (get_mlb_game_log_all_players()) -- picking
// a name resolves Batter vs. Pitcher mode on its own instead of making the
// user choose a mode first. A small number of pitchers also have some
// logged plate appearances and show up twice, once per type, so they can
// still be picked unambiguously (see playerMeta below). Batter mode has the
// two splits
// that are specifically an MLB thing: Home/Away and vs LHP/vs RHP (the
// opposing starter's throwing hand, matched game-by-game -- see
// _mlb_starting_pitcher_hand() in backend/app/data/mlb.py, the same read
// the Pitcher Matchup page's own vs L / vs R splits come from). Pitcher mode
// (own props -- Ks, earned runs, etc.) only gets Home/Away; a pitcher faces
// a whole lineup of both hands in one game, so "vs LHP/RHP" isn't a
// meaningful split on his own log the way it is on a batter's. A 150+ game
// MLB season also makes "Last 5" too small a window to bother with and
// "Last 25" a genuinely useful one, so the hit-rate table shows Last 10 /
// Last 25 / Season instead of NBA/NFL's Last 5 / Last 10 / Season -- and the
// bar chart, which every game log page renders unscaled, is capped server
// -side to the last 60 games so a full season doesn't turn it into an
// unreadable smear.

const BATTER_STAT_OPTIONS: { value: string; label: string }[] = [
  { value: 'batter_hits', label: 'Hits' },
  { value: 'batter_home_runs', label: 'Home Runs' },
  { value: 'batter_total_bases', label: 'Total Bases' },
  { value: 'batter_rbis', label: 'RBIs' },
  { value: 'batter_runs_scored', label: 'Runs Scored' },
  { value: 'batter_doubles', label: 'Doubles' },
  { value: 'batter_walks', label: 'Walks' },
  { value: 'batter_strikeouts', label: 'Strikeouts' },
  { value: 'batter_stolen_bases', label: 'Stolen Bases' },
  { value: 'batter_singles', label: 'Singles' },
  { value: 'batter_hits_runs_rbis', label: 'Hits + Runs + RBIs' },
];

// Matches MLB_PITCHER_MARKET_STAT in backend/app/data/mlb.py.
const PITCHER_STAT_OPTIONS: { value: string; label: string }[] = [
  { value: 'pitcher_strikeouts', label: 'Strikeouts' },
  { value: 'pitcher_earned_runs', label: 'Earned Runs' },
  { value: 'pitcher_hits_allowed', label: 'Hits Allowed' },
  { value: 'pitcher_walks', label: 'Walks' },
  { value: 'pitcher_outs', label: 'Outs Recorded' },
  { value: 'pitcher_record_a_win', label: 'Record a Win' },
];

type PlayerType = 'batter' | 'pitcher';
type HomeAway = 'all' | 'home' | 'away';
type PitcherHand = 'all' | 'L' | 'R';

// One entry per get_mlb_game_log_all_players() result -- `name` is the
// exact label the respective backend index (batter or pitcher) keys on,
// safe to pass straight through as the `player` query param.
interface PlayerOption {
  name: string;
  types: PlayerType[];
}

interface BatterGame {
  game_date: string;
  opponent: string;
  is_home: boolean;
  at_bats?: number | null;
  hits?: number | null;
  runs?: number | null;
  rbi?: number | null;
  home_runs?: number | null;
  stolen_bases?: number | null;
  opp_pitcher?: string | null;
  opp_pitcher_hand?: 'L' | 'R' | null;
  // Only used to key into pitcher_splits below -- never displayed.
  opp_pitcher_id?: number | null;
  stat_value: number;
}

// Compact subset of the pitcher's vs-L / vs-R Statcast split (same source
// as the Pitcher Matchup page's own splits table) -- from
// _pitcher_split_stats() in backend/app/data/mlb.py.
interface PitcherSplitStats {
  AVG?: number;
  wOBA?: number;
  SLG?: number;
  'K%'?: number;
  'BB%'?: number;
}
interface PitcherSplitEntry {
  // Which of vs_l/vs_r actually applies to the searched batter against this
  // one pitcher -- null when the batter's own bats hand isn't known (see
  // _mlb_batter_bats_index()'s docstring: coverage is today's slate only).
  resolved_side: 'L' | 'R' | null;
  vs_l: PitcherSplitStats;
  vs_r: PitcherSplitStats;
}

interface BatterOverCount { over: number; total: number; pct: number; }

interface BatterGameData {
  games: BatterGame[];
  over_counts: { last10: BatterOverCount; last25: BatterOverCount; season: BatterOverCount };
  // Keyed by opp_pitcher_id as a string -- one entry per distinct opposing
  // starter shown in `games`, not one per row.
  pitcher_splits: Record<string, PitcherSplitEntry>;
  batter_bats: 'L' | 'R' | 'S' | null;
}

interface PitcherGame {
  game_date: string;
  opponent: string;
  is_home: boolean;
  innings?: number | null;
  hits?: number | null;
  runs?: number | null;
  earned_runs?: number | null;
  home_runs?: number | null;
  walks?: number | null;
  strikeouts?: number | null;
  pitches?: number | null;
  win?: boolean | null;
  loss?: boolean | null;
  is_start?: boolean | null;
  stat_value: number;
}

interface PitcherGameData {
  games: PitcherGame[];
  over_counts: { last10: BatterOverCount; last25: BatterOverCount; season: BatterOverCount };
}

const labelStyle = fieldLabelStyle;
const inputStyle = fieldStyle;

const OVER_COUNTS_PERIODS = [
  { key: 'last10', label: 'Last 10' },
  { key: 'last25', label: 'Last 25' },
  { key: 'season', label: 'Season' },
];

function formatStatLabel(playerType: PlayerType, stat: string): string {
  const options = playerType === 'batter' ? BATTER_STAT_OPTIONS : PITCHER_STAT_OPTIONS;
  return options.find((s) => s.value === stat)?.label ?? stat;
}

function opponentLabel(g: { is_home: boolean; opponent: string }): string {
  return (g.is_home ? 'vs ' : '@ ') + g.opponent;
}

function pitcherLabel(g: BatterGame): string {
  if (!g.opp_pitcher) return '—';
  return g.opp_pitcher_hand ? `${g.opp_pitcher} (${g.opp_pitcher_hand})` : g.opp_pitcher;
}

// Baseball convention: rate stats print without the leading zero (".253",
// not "0.253"); percents keep one decimal and a % sign.
function fmtRate(v?: number): string | null {
  return v == null ? null : v.toFixed(3).replace(/^0/, '');
}
function fmtPct(v?: number): string | null {
  return v == null ? null : `${v.toFixed(1)}%`;
}

function splitLine(s: PitcherSplitStats): string {
  const parts: string[] = [];
  const avg = fmtRate(s.AVG); if (avg) parts.push(`${avg} AVG`);
  const woba = fmtRate(s.wOBA); if (woba) parts.push(`${woba} wOBA`);
  const slg = fmtRate(s.SLG); if (slg) parts.push(`${slg} SLG`);
  const k = fmtPct(s['K%']); if (k) parts.push(`${k} K`);
  const bb = fmtPct(s['BB%']); if (bb) parts.push(`${bb} BB`);
  return parts.join(' · ');
}

// The opposing pitcher's split line for this specific batter -- resolved to
// one side (vs L or vs R, whichever this batter actually hits from against
// this pitcher) when his bats hand is known, or both sides compactly when
// it isn't (see PitcherSplitEntry's comment on resolved_side). null when
// there's nothing to show at all.
function pitcherSplitLabel(g: BatterGame, splitsByPitcher: Record<string, PitcherSplitEntry>): string | null {
  if (g.opp_pitcher_id == null) return null;
  const entry = splitsByPitcher[String(g.opp_pitcher_id)];
  if (!entry) return null;
  const { resolved_side, vs_l, vs_r } = entry;
  if (resolved_side === 'L' && Object.keys(vs_l).length > 0) return `vs L: ${splitLine(vs_l)}`;
  if (resolved_side === 'R' && Object.keys(vs_r).length > 0) return `vs R: ${splitLine(vs_r)}`;
  const lPart = Object.keys(vs_l).length > 0 ? `L ${fmtRate(vs_l.AVG) ?? '—'}/${fmtRate(vs_l.wOBA) ?? '—'}w` : null;
  const rPart = Object.keys(vs_r).length > 0 ? `R ${fmtRate(vs_r.AVG) ?? '—'}/${fmtRate(vs_r.wOBA) ?? '—'}w` : null;
  const both = [lPart, rPart].filter(Boolean).join(' · ');
  return both || null;
}

// Compact box-score line for the mobile card view -- the desktop table
// shows AB/R/H/RBI/HR/SB as their own columns; on a phone that's too many
// columns, so they collapse into one string instead. HR/SB only show up
// when they're non-zero to keep the common case (a single or an out) short.
function boxLine(g: BatterGame): string | null {
  if (g.at_bats == null || g.hits == null) return null;
  const parts = [`${g.at_bats} AB`, `${g.runs ?? 0} R`, `${g.hits} H`, `${g.rbi ?? 0} RBI`];
  if (g.home_runs) parts.push(`${g.home_runs} HR`);
  if (g.stolen_bases) parts.push(`${g.stolen_bases} SB`);
  return parts.join(', ');
}

// Same idea for a pitcher's own box line.
function pitcherBoxLine(g: PitcherGame): string | null {
  if (g.innings == null) return null;
  const parts = [`${g.innings} IP`, `${g.hits ?? 0} H`, `${g.runs ?? 0} R`, `${g.earned_runs ?? 0} ER`, `${g.walks ?? 0} BB`, `${g.strikeouts ?? 0} SO`];
  if (g.home_runs) parts.push(`${g.home_runs} HR`);
  return parts.join(', ');
}

function decisionLabel(g: PitcherGame): string | null {
  if (g.win) return 'W';
  if (g.loss) return 'L';
  return null;
}

export default function MLBGameLog() {
  const [playerType, setPlayerType] = useState<PlayerType>('batter');
  // Dropdown display strings, and what each one resolves to. Usually a
  // label is just the player's plain name; the handful of pitchers who
  // also have some logged plate appearances get two labels ("X (Batter)" /
  // "X (Pitcher)") so either can be picked unambiguously -- see the effect
  // below and get_mlb_game_log_all_players()'s docstring.
  const [playerLabels, setPlayerLabels] = useState<string[]>([]);
  const [playerMeta, setPlayerMeta] = useState<Record<string, { name: string; type: PlayerType }>>({});
  const [selectedLabel, setSelectedLabel] = useState('');
  const [selectedPlayer, setSelectedPlayer] = useState('');
  const [selectedStat, setSelectedStat] = useState('batter_hits');
  const [thresholdStr, setThresholdStr] = useState('');
  const [homeAway, setHomeAway] = useState<HomeAway>('all');
  const [pitcherHand, setPitcherHand] = useState<PitcherHand>('all');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [batterData, setBatterData] = useState<BatterGameData | null>(null);
  const [pitcherData, setPitcherData] = useState<PitcherGameData | null>(null);
  const isMobile = useIsMobile();
  const panelLayout = usePanelLayout();

  // One combined fetch on mount -- the search box covers batters and
  // pitchers together, so there's no toggle to re-trigger this off of.
  useEffect(() => {
    getMLBGameLogAllPlayers()
      .then((res) => {
        const labels: string[] = [];
        const meta: Record<string, { name: string; type: PlayerType }> = {};
        (res.data as PlayerOption[]).forEach(({ name, types }) => {
          if (types.length > 1) {
            // Ambiguous name (both a batter and a pitcher entry) -- give it
            // two distinct, disambiguated labels rather than picking one
            // for the user.
            types.forEach((t) => {
              const label = `${name} (${t === 'batter' ? 'Batter' : 'Pitcher'})`;
              labels.push(label);
              meta[label] = { name, type: t };
            });
          } else if (types.length === 1) {
            labels.push(name);
            meta[name] = { name, type: types[0] };
          }
        });
        labels.sort((a, b) => a.localeCompare(b));
        setPlayerLabels(labels);
        setPlayerMeta(meta);
      })
      .catch(() => { setPlayerLabels([]); setPlayerMeta({}); });
  }, []);

  // Picking a player from the combined list resolves Batter vs. Pitcher on
  // its own. Only reset the stat dropdown and the vs-LHP/RHP filter when
  // the newly-picked player is a different type than whatever was selected
  // before -- picking another player of the SAME type keeps the current
  // stat/threshold/filters exactly as they were, which the old toggle-first
  // flow couldn't do (switching the toggle always reset everything).
  const handleSelectPlayer = (label: string) => {
    setSelectedLabel(label);
    const meta = playerMeta[label];
    if (!meta) {
      setSelectedPlayer('');
      return;
    }
    setSelectedPlayer(meta.name);
    if (meta.type !== playerType) {
      setPlayerType(meta.type);
      setSelectedStat(meta.type === 'batter' ? 'batter_hits' : 'pitcher_strikeouts');
      setPitcherHand('all');
    }
    setError('');
  };

  // Guards an older request's response landing after a newer one's -- matters
  // now that a fetch can fire on its own (the toggle effect below) rather
  // than only from a single button click at a time.
  const requestIdRef = useRef(0);

  const fetchStats = async () => {
    if (!selectedPlayer) return;
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError('');
    setBatterData(null);
    setPitcherData(null);
    try {
      const threshold = parseFloat(thresholdStr) || 0;
      const params: Record<string, any> = { player: selectedPlayer, stat: selectedStat, threshold };
      if (homeAway !== 'all') params.home_away = homeAway;
      if (playerType === 'batter') {
        if (pitcherHand !== 'all') params.pitcher_hand = pitcherHand;
        const res = await getMLBGameLog(params);
        if (requestId === requestIdRef.current) setBatterData(res.data);
      } else {
        const res = await getMLBPitcherGameLog(params);
        if (requestId === requestIdRef.current) setPitcherData(res.data);
      }
    } catch (err: any) {
      if (requestId === requestIdRef.current) setError(err?.response?.data?.detail || 'Failed to fetch game log.');
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  };

  // Home/Away and vs L/R are toggles, not text fields mid-edit -- a click is
  // a complete "show me this split now" intent, so (once a player has
  // already been searched at least once) flipping either one re-fetches on
  // its own instead of waiting for a second press of Get Stats. Same idea as
  // the NFL Game Log's Season toggle. No-ops before the first fetch, so
  // landing on the page with the toggles at their defaults never fires a
  // request nobody asked for.
  useEffect(() => {
    if (batterData || pitcherData) fetchStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [homeAway, pitcherHand]);

  const gameData = playerType === 'batter' ? batterData : pitcherData;
  const recentBatterGames = batterData ? batterData.games.slice(-25).reverse() : [];
  const recentPitcherGames = pitcherData ? pitcherData.games.slice(-25).reverse() : [];
  const threshold = parseFloat(thresholdStr) || 0;
  const statOptions = playerType === 'batter' ? BATTER_STAT_OPTIONS : PITCHER_STAT_OPTIONS;

  return (
    <div style={panelLayout}>
      <FilterPanel
        title="MLB Game Log"
        action={{
          label: 'Get Stats',
          onClick: fetchStats,
          disabled: !selectedPlayer || loading,
        }}
      >
        <label style={labelStyle}>Player</label>
        <div style={{ marginBottom: 16 }}>
          <SearchDropdown
            players={playerLabels}
            value={selectedLabel}
            onSelect={handleSelectPlayer}
            placeholder="Search any batter or pitcher..."
            inputStyle={{ padding: 8 }}
          />
        </div>

        <label style={labelStyle}>Stat</label>
        <select style={inputStyle} value={selectedStat} onChange={(e) => setSelectedStat(e.target.value)}>
          {statOptions.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>

        <label style={labelStyle}>Threshold</label>
        <input
          type="number"
          min={0}
          step={1}
          style={inputStyle}
          placeholder="e.g. 1"
          value={thresholdStr}
          onFocus={(e) => e.target.select()}
          onChange={(e) => setThresholdStr(e.target.value)}
        />

        <label style={labelStyle}>Home / Away</label>
        <div style={{ marginBottom: playerType === 'batter' ? 16 : 4 }}>
          <SegmentedToggle
            value={homeAway}
            onChange={setHomeAway}
            fullWidth
            options={[
              { value: 'all', label: 'All' },
              { value: 'home', label: 'Home' },
              { value: 'away', label: 'Away' },
            ]}
          />
        </div>

        {/* Not shown in pitcher mode -- a pitcher faces a whole lineup of
            both hands in one game, so vs-LHP/vs-RHP isn't a meaningful split
            on his own log the way it is on a batter facing one starter. */}
        {playerType === 'batter' && (
          <>
            <label style={labelStyle}>Opposing Pitcher</label>
            <div style={{ marginBottom: 4 }}>
              <SegmentedToggle
                value={pitcherHand}
                onChange={setPitcherHand}
                fullWidth
                options={[
                  { value: 'all', label: 'All' },
                  { value: 'L', label: 'vs LHP' },
                  { value: 'R', label: 'vs RHP' },
                ]}
              />
            </div>
          </>
        )}
      </FilterPanel>

      {/* Main Content */}
      <div style={{ flex: 1, padding: isMobile ? 16 : 24, overflowY: 'auto', background: theme.bgPage }}>
        {loading && <LoadingSpinner />}
        {error && (
          <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
            {error}
          </div>
        )}
        {!loading && !error && gameData && (
          <>
            <h2 style={{ marginTop: 0, color: theme.textPrimary }}>
              {selectedPlayer} — {formatStatLabel(playerType, selectedStat)} (Line: {threshold})
              {homeAway !== 'all' && (
                <span style={{ color: theme.textSecondary, fontWeight: 400, fontSize: 16 }}>
                  {' '}· {homeAway === 'home' ? 'Home Only' : 'Away Only'}
                </span>
              )}
              {playerType === 'batter' && pitcherHand !== 'all' && (
                <span style={{ color: theme.textSecondary, fontWeight: 400, fontSize: 16 }}>
                  {' '}· vs {pitcherHand === 'L' ? 'LHP' : 'RHP'} Only
                </span>
              )}
            </h2>

            {gameData.games.length === 0 ? (
              <div style={{ color: theme.textSecondary, marginTop: 20 }}>
                No games match this filter combination yet.
              </div>
            ) : (
              <>
                {/* Capped to the last 60 games server-side already -- a full
                    150+ game season plotted unscaled would be an unreadable
                    smear of bars, and the hit-rate table below already covers
                    the true full season regardless of this cap. */}
                <StatChart games={gameData.games} threshold={threshold} stat={formatStatLabel(playerType, selectedStat)} />
                <OverCountsTable
                  over_counts={gameData.over_counts}
                  threshold={threshold}
                  stat={formatStatLabel(playerType, selectedStat)}
                  periods={OVER_COUNTS_PERIODS}
                />

                <h3 style={{ marginTop: 28, marginBottom: 12, color: theme.textPrimary }}>Recent Games (Last 25)</h3>

                {playerType === 'batter' && batterData ? (
                  isMobile ? (
                    <div>
                      {recentBatterGames.map((g, i) => (
                        <StatCard
                          key={i}
                          title={g.game_date}
                          titleAside={opponentLabel(g)}
                          value={g.stat_value}
                          valueColor={g.stat_value >= threshold ? theme.dataBlue : theme.dataRed}
                          footer={formatStatLabel(playerType, selectedStat)}
                          meta={[
                            boxLine(g),
                            pitcherLabel(g) !== '—' ? pitcherLabel(g) : null,
                            pitcherSplitLabel(g, batterData.pitcher_splits),
                          ]}
                        />
                      ))}
                    </div>
                  ) : (
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                      <thead>
                        <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                          <th style={{ padding: '10px 14px', textAlign: 'left' }}>Date</th>
                          <th style={{ padding: '10px 14px', textAlign: 'left' }}>Opponent</th>
                          <th style={{ padding: '10px 14px', textAlign: 'left' }}>Opposing Pitcher</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>AB</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>R</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>H</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>RBI</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>HR</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>SB</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>{formatStatLabel(playerType, selectedStat)}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recentBatterGames.map((g, i) => (
                          <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgPage : theme.bgCard, color: theme.textPrimary }}>
                            <td style={{ padding: '8px 14px' }}>{g.game_date}</td>
                            <td style={{ padding: '8px 14px' }}>{opponentLabel(g)}</td>
                            <td style={{ padding: '8px 14px', color: theme.textSecondary }}>
                              <div>{pitcherLabel(g)}</div>
                              {pitcherSplitLabel(g, batterData.pitcher_splits) && (
                                <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 1 }}>
                                  {pitcherSplitLabel(g, batterData.pitcher_splits)}
                                </div>
                              )}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.at_bats ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.runs ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.hits ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.rbi ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.home_runs ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.stolen_bases ?? '—'}
                            </td>
                            <td style={{
                              padding: '8px 14px',
                              textAlign: 'center',
                              fontWeight: 700,
                              color: g.stat_value >= threshold ? theme.dataBlue : theme.dataRed,
                            }}>
                              {g.stat_value}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )
                ) : null}

                {playerType === 'pitcher' && pitcherData ? (
                  isMobile ? (
                    <div>
                      {recentPitcherGames.map((g, i) => (
                        <StatCard
                          key={i}
                          title={g.game_date}
                          titleAside={`${opponentLabel(g)}${decisionLabel(g) ? ` (${decisionLabel(g)})` : ''}`}
                          value={g.stat_value}
                          valueColor={g.stat_value >= threshold ? theme.dataBlue : theme.dataRed}
                          footer={formatStatLabel(playerType, selectedStat)}
                          meta={[pitcherBoxLine(g)]}
                        />
                      ))}
                    </div>
                  ) : (
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                      <thead>
                        <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                          <th style={{ padding: '10px 14px', textAlign: 'left' }}>Date</th>
                          <th style={{ padding: '10px 14px', textAlign: 'left' }}>Opponent</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>Dec</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>IP</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>H</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>R</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>ER</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>BB</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>SO</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>HR</th>
                          <th style={{ padding: '10px 14px', textAlign: 'center' }}>{formatStatLabel(playerType, selectedStat)}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recentPitcherGames.map((g, i) => (
                          <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgPage : theme.bgCard, color: theme.textPrimary }}>
                            <td style={{ padding: '8px 14px' }}>{g.game_date}</td>
                            <td style={{ padding: '8px 14px' }}>{opponentLabel(g)}</td>
                            <td style={{
                              padding: '8px 14px', textAlign: 'center', fontWeight: 600,
                              color: g.win ? theme.dataBlue : g.loss ? theme.dataRed : theme.textMuted,
                            }}>
                              {decisionLabel(g) ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.innings ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.hits ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.runs ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.earned_runs ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.walks ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.strikeouts ?? '—'}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                              {g.home_runs ?? '—'}
                            </td>
                            <td style={{
                              padding: '8px 14px',
                              textAlign: 'center',
                              fontWeight: 700,
                              color: g.stat_value >= threshold ? theme.dataBlue : theme.dataRed,
                            }}>
                              {g.stat_value}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )
                ) : null}
              </>
            )}
          </>
        )}
        {!loading && !error && !gameData && (
          <div style={{ color: theme.textSecondary, marginTop: 60, textAlign: 'center', fontSize: 16, background: theme.bgPage, minHeight: '100%' }}>
            Select a player and click "Get Stats" to view game log.
          </div>
        )}
      </div>
    </div>
  );
}
