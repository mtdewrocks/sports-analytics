import React, { useState, useEffect, useRef } from 'react';
import { getNFLGameLogPlayers, getNFLStats, getNFLGameLog, getNFLPositionVsDefense } from '../../api/nfl';
import StatChart from '../../components/StatChart';
import OverCountsTable from '../../components/OverCountsTable';
import WinLossBreakdownTable from '../../components/WinLossBreakdownTable';
import GameCard from '../../components/GameCard';
import StatCard from '../../components/StatCard';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import SegmentedToggle from '../../components/SegmentedToggle';
import FilterPanel from '../../components/FilterPanel';
import { fieldLabelStyle, fieldStyle, usePanelLayout } from '../../components/filterStyles';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

interface Game {
  week?: number;
  opponent?: string;
  stat_value: number;
  game_date?: string;
  season?: number;
  result?: 'W' | 'L' | 'T' | null;
  def_ypg_season?: number | null;
  def_ypg_rank_season?: number | null;
  def_ypa_season?: number | null;
  def_ypa_rank_season?: number | null;
  def_ypg_last4?: number | null;
  def_ypg_rank_last4?: number | null;
  def_ypa_last4?: number | null;
  def_ypa_rank_last4?: number | null;
  def_is_fallback?: boolean;
  tooltip?: Record<string, number | string | null>;
}

interface UpcomingGame {
  week: number;
  opponent: string;
  def_ypg_current?: number | null;
  def_ypg_rank_current?: number | null;
  def_ypa_current?: number | null;
  def_ypa_rank_current?: number | null;
}

// "Position vs. Defense" -- how other players at the same position have
// fared against the player's next opponent this season. Only ever fetched
// for the positions in _POSITION_GROUP_MAP in backend/app/data/nfl.py;
// anything else just never gets a player_position the effect below will
// act on.
interface PvdRow {
  week: number;
  player: string;
  team: string;
  matchup: string;
  carries: number;
  rushing_yards: number;
  rushing_tds: number;
  targets: number;
  receptions: number;
  receiving_yards: number;
  receiving_tds: number;
  // Only populated (non-zero) on QB rows.
  attempts: number;
  completions: number;
  passing_yards: number;
  passing_tds: number;
  passing_interceptions: number;
}
interface PvdExcluded extends PvdRow {
  reason: string;
}
interface PvdData {
  rows: PvdRow[];
  excluded: PvdExcluded[];
}

interface OverCount {
  over: number;
  total: number;
  pct: number;
}

interface WinLossSummary {
  games: number;
  avg: number | null;
  hit: number;
  total: number;
  pct: number;
}
interface GameData {
  games: Game[];
  upcoming: UpcomingGame[];
  over_counts: {
    last5: OverCount;
    last10: OverCount;
    season: OverCount;
  };
  win_loss_breakdown?: {
    W: WinLossSummary;
    L: WinLossSummary;
  };
  player_position?: string | null;
}

// Now shared with the other five pages that had a filter sidebar -- see
// components/FilterPanel.
const labelStyle = fieldLabelStyle;
const inputStyle = fieldStyle;

// Same absolute-tier convention as the Matchup page: top 10 of 32 teams,
// bottom 10, middle 12 -- rather than comparing anything to an opponent.
function rankColor(rank: number | null | undefined): string {
  if (rank == null) return theme.textPrimary;
  if (rank <= 10) return theme.dataBlue;
  if (rank >= 23) return theme.dataRed;
  return theme.textPrimary;
}

function formatStatLabel(stat: string): string {
  return stat
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

function ordinal(n: number): string {
  const rem100 = n % 100;
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1: return `${n}st`;
    case 2: return `${n}nd`;
    case 3: return `${n}rd`;
    default: return `${n}th`;
  }
}

const TOOLTIP_LABELS: Record<string, string> = {
  completions: 'Completions',
  attempts: 'Attempts',
  carries: 'Carries',
  targets: 'Targets',
  receptions: 'Receptions',
  score: 'Score',
};

function formatTooltip(tooltip?: Record<string, number | string | null>): string {
  if (!tooltip || Object.keys(tooltip).length === 0) return '';
  return Object.entries(tooltip)
    .map(([key, val]) => `${TOOLTIP_LABELS[key] ?? key}: ${val ?? '—'}`)
    .join(' \u00b7 ');
}

const POSITION_PLURAL: Record<string, string> = { RB: 'RBs', WR: 'WRs', TE: 'TEs', QB: 'QBs' };

// One line per excluded player in the "Show N filtered out" disclosure --
// same workload numbers the include/exclude decision was actually made on
// (attempts for QB, carries/targets for RB, targets/yards for WR/TE), so
// the rule is checkable rather than just asserted.
function formatExcluded(item: PvdExcluded, position: string): string {
  const stats = position === 'QB'
    ? `${item.attempts} att, ${item.completions} cmp, ${item.passing_yards} yds`
    : position === 'RB'
    ? `${item.carries} att, ${item.rushing_yards} yds, ${item.targets} tgt`
    : `${item.targets} tgt, ${item.receiving_yards} yds`;
  return `Wk${item.week} ${item.team} — ${item.player} (${position}): ${stats} — ${item.reason}`;
}

type RankMode = 'season' | 'last4';

// Extend when a new season starts -- matches SEASONS in
// backend/app/get_nfl_player_box_stats.py, the two seasons that script
// actually pulls and keeps in the same file.
const CURRENT_SEASON = 2026;
const SEASON_OPTIONS = [
  { value: String(CURRENT_SEASON), label: String(CURRENT_SEASON) },
  { value: String(CURRENT_SEASON - 1), label: String(CURRENT_SEASON - 1) },
];

export default function NFLGameLog() {
  const [players, setPlayers] = useState<string[]>([]);
  const [stats, setStats] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState('');
  const [selectedStat, setSelectedStat] = useState('');
  const [season, setSeason] = useState(String(CURRENT_SEASON));
  const [thresholdStr, setThresholdStr] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [gameData, setGameData] = useState<GameData | null>(null);
  const [rankMode, setRankMode] = useState<RankMode>('season');
  const [winLoss, setWinLoss] = useState<'' | 'W' | 'L'>('');
  const [marginOperator, setMarginOperator] = useState<'' | '<' | '>'>('');
  const [marginValueStr, setMarginValueStr] = useState('');
  const [pvdData, setPvdData] = useState<PvdData | null>(null);
  const [pvdLoading, setPvdLoading] = useState(false);
  const [showExcluded, setShowExcluded] = useState(false);
  const isMobile = useIsMobile();
  const panelLayout = usePanelLayout();

  useEffect(() => {
    getNFLGameLogPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
    getNFLStats()
      .then((res) => {
        setStats(res.data);
        if (res.data.length > 0) setSelectedStat(res.data[0]);
      })
      .catch(() => setStats([]));
  }, []);

  // Guards against an older request's response landing after a newer one's
  // -- only matters now that a fetch can fire on its own (the season effect
  // below) rather than only from one button click at a time, e.g. flipping
  // the season toggle twice in quick succession.
  const requestIdRef = useRef(0);

  const fetchStats = async () => {
    if (!selectedPlayer || !selectedStat) return;
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError('');
    setGameData(null);
    try {
      const threshold = parseFloat(thresholdStr) || 0;
      const marginValue = parseFloat(marginValueStr);
      const res = await getNFLGameLog({
        player: selectedPlayer, stat: selectedStat, threshold, season,
        win_loss: winLoss || undefined,
        margin_operator: marginOperator && !isNaN(marginValue) ? marginOperator : undefined,
        margin_value: marginOperator && !isNaN(marginValue) ? marginValue : undefined,
      });
      if (requestId === requestIdRef.current) setGameData(res.data);
    } catch (err: any) {
      if (requestId === requestIdRef.current) setError(err?.response?.data?.detail || 'Failed to fetch game log.');
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  };

  // Season is the one filter that re-fetches on its own instead of waiting
  // for Get Stats -- flipping 2026/2025 is a single deliberate click with an
  // obvious "show me the other season" intent, unlike Player/Stat/Threshold,
  // which stay behind the button since they're usually mid-edit when they
  // change. No-ops until a player and stat are actually chosen (also true
  // on first mount, before either default has loaded), so this never fires
  // a request for a page nobody has used yet.
  useEffect(() => {
    fetchStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season]);

  // Position vs. Defense: scoped to the very next game on the schedule
  // (gameData.upcoming[0]) and the selected player's own position, which
  // the backend already resolved trade-aware in get_game_log(). Fires
  // automatically once gameData lands -- no separate button, since it's
  // just supporting detail for the "Upcoming" section, not a filter the
  // user configures. exclude_player drops the selected player out of
  // their own results, for the divisional-rematch case where they'd
  // otherwise show up against their own upcoming opponent from an earlier
  // meeting this season.
  const pvdRequestIdRef = useRef(0);
  const nextGame = gameData?.upcoming?.[0];
  const pvdPosition = gameData?.player_position;

  useEffect(() => {
    setShowExcluded(false);
    if (!nextGame?.opponent || !pvdPosition) {
      setPvdData(null);
      return;
    }
    const requestId = ++pvdRequestIdRef.current;
    setPvdLoading(true);
    getNFLPositionVsDefense(nextGame.opponent, pvdPosition, selectedPlayer)
      .then((res) => {
        if (requestId === pvdRequestIdRef.current) setPvdData(res.data);
      })
      .catch(() => {
        if (requestId === pvdRequestIdRef.current) setPvdData(null);
      })
      .finally(() => {
        if (requestId === pvdRequestIdRef.current) setPvdLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nextGame?.opponent, nextGame?.week, pvdPosition, selectedPlayer]);

  // Whether this stat has any defensive context at all -- a player's own
  // defensive stats (sacks, tackles) have no mapped opponent context, so
  // the extra columns and toggle simply don't render for those.
  const hasDefContext = !!gameData?.games.some((g) => g.def_ypg_rank_season != null)
    || !!gameData?.upcoming.some((g) => g.def_ypg_rank_current != null);

  // Visible columns for whatever supplementary stats apply to the
  // selected stat (e.g. Carries for rushing yards, Completions/Attempts
  // for passing yards) -- "score" stays out of this and remains a
  // chart-hover-only detail, since that was a separate, earlier decision
  // this doesn't reopen. Shown as real columns rather than a hover-only
  // tooltip, since hover doesn't exist at all on a touch device.
  const extraStatKeys = Object.keys(gameData?.games[0]?.tooltip ?? {}).filter((k) => k !== 'score');

  return (
    <div style={panelLayout}>
      <FilterPanel
        title="NFL Game Log"
        moreLabel="Team Result, Margin"
        action={{
          label: 'Get Stats',
          onClick: fetchStats,
          disabled: !selectedPlayer || !selectedStat || loading,
        }}
        more={
          <>
            <label style={labelStyle}>Team Result</label>
            <select
              style={inputStyle}
              value={winLoss}
              onChange={(e) => setWinLoss(e.target.value as '' | 'W' | 'L')}
            >
              <option value="">All Games</option>
              <option value="W">Wins Only</option>
              <option value="L">Losses Only</option>
            </select>

            <label style={labelStyle}>Margin (point differential)</label>
            <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
              <button
                onClick={() => { setMarginOperator('<'); setMarginValueStr('7'); }}
                style={{
                  flex: 1, padding: '8px 0', fontSize: 12, borderRadius: 4, cursor: 'pointer', minHeight: 36,
                  border: `1px solid ${theme.border}`, background: theme.bgPage, color: theme.textSecondary,
                }}
              >
                Close Game (&lt;7)
              </button>
              <button
                onClick={() => { setMarginOperator('>'); setMarginValueStr('14'); }}
                style={{
                  flex: 1, padding: '8px 0', fontSize: 12, borderRadius: 4, cursor: 'pointer', minHeight: 36,
                  border: `1px solid ${theme.border}`, background: theme.bgPage, color: theme.textSecondary,
                }}
              >
                Blowout (&gt;14)
              </button>
            </div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
              <select
                style={{ ...inputStyle, marginBottom: 0, width: 70, flexShrink: 0 }}
                value={marginOperator}
                onChange={(e) => setMarginOperator(e.target.value as '' | '<' | '>')}
              >
                <option value="">Any</option>
                <option value="<">&lt;</option>
                <option value=">">&gt;</option>
              </select>
              <input
                type="number"
                min={0}
                step={1}
                style={{ ...inputStyle, marginBottom: 0 }}
                placeholder="points"
                value={marginValueStr}
                disabled={!marginOperator}
                onFocus={(e) => e.target.select()}
                onChange={(e) => setMarginValueStr(e.target.value)}
              />
            </div>
            <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 16 }}>
              Applies to any game decided by this margin, win or loss -- independent of the Team Result filter above.
            </div>
          </>
        }
      >
        <label style={labelStyle}>Season</label>
        <div style={{ marginBottom: 16 }}>
          <SegmentedToggle options={SEASON_OPTIONS} value={season} onChange={setSeason} fullWidth />
        </div>

        <label style={labelStyle}>Player</label>
        <div style={{ marginBottom: 16 }}>
          <SearchDropdown
            players={players}
            value={selectedPlayer}
            onSelect={setSelectedPlayer}
            placeholder="Search by first or last name..."
            inputStyle={{ padding: 8 }}
          />
        </div>

        <label style={labelStyle}>Stat</label>
        <select style={inputStyle} value={selectedStat} onChange={(e) => setSelectedStat(e.target.value)}>
          <option value="">-- Select Stat --</option>
          {stats.map((s) => <option key={s} value={s}>{formatStatLabel(s)}</option>)}
        </select>

        <label style={labelStyle}>Threshold</label>
        <input
          type="number"
          min={0}
          step={1}
          style={inputStyle}
          placeholder="e.g. 250"
          value={thresholdStr}
          onFocus={(e) => e.target.select()}
          onChange={(e) => setThresholdStr(e.target.value)}
        />

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
              {selectedPlayer} — {formatStatLabel(selectedStat)} (Line: {parseFloat(thresholdStr) || 0})
              <span style={{ color: theme.textSecondary, fontWeight: 400, fontSize: 16 }}> · {season} Season</span>
              {winLoss && <span style={{ color: theme.textSecondary, fontWeight: 400, fontSize: 16 }}> · {winLoss === 'W' ? 'Wins Only' : 'Losses Only'}</span>}
              {marginOperator && marginValueStr && (
                <span style={{ color: theme.textSecondary, fontWeight: 400, fontSize: 16 }}> · Margin {marginOperator} {marginValueStr}</span>
              )}
            </h2>
            <StatChart games={gameData.games} threshold={parseFloat(thresholdStr) || 0} stat={selectedStat} />
            <OverCountsTable over_counts={gameData.over_counts} threshold={parseFloat(thresholdStr) || 0} stat={selectedStat} />
            {gameData.win_loss_breakdown && (
              <WinLossBreakdownTable
                breakdown={gameData.win_loss_breakdown}
                threshold={parseFloat(thresholdStr) || 0}
                stat={selectedStat}
              />
            )}

            {/* On a phone the toggle gets its own full-width row under the
                heading rather than being squeezed beside it. */}
            <div style={{
              display: 'flex', alignItems: isMobile ? 'stretch' : 'center',
              flexDirection: isMobile ? 'column' : 'row',
              gap: isMobile ? 8 : 0,
              justifyContent: 'space-between', marginTop: 28, marginBottom: 12,
            }}>
              <h3 style={{ margin: 0, color: theme.textPrimary }}>Recent Games</h3>
              {hasDefContext && (
                <SegmentedToggle
                  value={rankMode}
                  onChange={setRankMode}
                  fullWidth={isMobile}
                  options={[
                    { value: 'season', label: 'Season' },
                    { value: 'last4', label: 'Last 4 Games' },
                  ]}
                />
              )}
            </div>

            {isMobile ? (
              <div>
                {gameData.games.map((g, i) => {
                  const ypgRank = rankMode === 'season' ? g.def_ypg_rank_season : g.def_ypg_rank_last4;
                  return (
                    <GameCard
                      key={i}
                      week={g.week}
                      gameDate={g.game_date}
                      result={g.result}
                      opponent={g.opponent}
                      statLabel={formatStatLabel(selectedStat)}
                      statValue={g.stat_value}
                      threshold={parseFloat(thresholdStr) || 0}
                      extraStats={extraStatKeys.map((key) => ({ label: TOOLTIP_LABELS[key] ?? key, value: g.tooltip?.[key] ?? null }))}
                      defRank={hasDefContext && ypgRank != null ? {
                        label: 'Opp D rank:', value: ordinal(ypgRank), color: rankColor(ypgRank), isFallback: g.def_is_fallback,
                      } : null}
                    />
                  );
                })}
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Week</th>
                    <th style={{ padding: '10px 14px', textAlign: 'center' }}>Result</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Opponent</th>
                    <th style={{ padding: '10px 14px', textAlign: 'center' }}>{formatStatLabel(selectedStat)}</th>
                    {extraStatKeys.map((key) => (
                      <th key={key} style={{ padding: '10px 14px', textAlign: 'center' }}>{TOOLTIP_LABELS[key] ?? key}</th>
                    ))}
                    {hasDefContext && (
                      <>
                        <th style={{ padding: '10px 14px', textAlign: 'right' }}>Opp D Rank (Yds/G)</th>
                        <th style={{ padding: '10px 14px', textAlign: 'right' }}>Opp D Rank (Yds/Att)</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {gameData.games.map((g, i) => {
                    const ypgRank = rankMode === 'season' ? g.def_ypg_rank_season : g.def_ypg_rank_last4;
                    const ypaRank = rankMode === 'season' ? g.def_ypa_rank_season : g.def_ypa_rank_last4;
                    return (
                      <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgPage : theme.bgCard, color: theme.textPrimary }}>
                        <td style={{ padding: '8px 14px' }}>{g.week ?? g.game_date ?? '—'}</td>
                        <td style={{
                          padding: '8px 14px', textAlign: 'center', fontWeight: 700,
                          color: g.result === 'W' ? theme.dataBlue : g.result === 'L' ? theme.dataRed : theme.textSecondary,
                        }}>
                          {g.result ?? '—'}
                        </td>
                        <td style={{ padding: '8px 14px' }}>{g.opponent ?? '—'}</td>
                        <td
                          title={formatTooltip(g.tooltip)}
                          style={{
                            padding: '8px 14px',
                            textAlign: 'center',
                            fontWeight: 700,
                            color: g.stat_value > (parseFloat(thresholdStr) || 0) ? theme.dataBlue : theme.dataRed,
                            cursor: g.tooltip && Object.keys(g.tooltip).length > 0 ? 'help' : undefined,
                            textDecoration: g.tooltip && Object.keys(g.tooltip).length > 0 ? 'underline dotted' : undefined,
                            textUnderlineOffset: 3,
                          }}
                        >
                          {g.stat_value}
                        </td>
                        {extraStatKeys.map((key) => (
                          <td key={key} style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>
                            {g.tooltip?.[key] ?? '—'}
                          </td>
                        ))}
                        {hasDefContext && (
                          <>
                            <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: rankColor(ypgRank) }}>
                              {ypgRank != null ? ordinal(ypgRank) : '—'}
                              {g.def_is_fallback && <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 400 }}> (prior yr)</span>}
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: rankColor(ypaRank) }}>
                              {ypaRank != null ? ordinal(ypaRank) : '—'}
                              {g.def_is_fallback && <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 400 }}> (prior yr)</span>}
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}

            {gameData.upcoming.length > 0 && (
              <>
                <h3 style={{ marginTop: 28, marginBottom: 12, color: theme.textPrimary }}>Upcoming</h3>

                {pvdPosition && nextGame && (
                  <div style={{
                    marginTop: 4, marginBottom: 22, borderRadius: 8,
                    border: '1px solid rgba(29,158,117,0.35)', background: 'rgba(29,158,117,0.04)',
                    padding: '16px 18px 18px',
                  }}>
                    <h4 style={{ fontSize: 14, margin: '0 0 2px', color: theme.textPrimary }}>
                      Week {nextGame.week} — at {nextGame.opponent}
                    </h4>
                    <div style={{ fontSize: 12.5, color: theme.textMuted, marginBottom: 12 }}>
                      {POSITION_PLURAL[pvdPosition] ?? pvdPosition} vs. {nextGame.opponent} this season, most recent first — the detail behind the W{nextGame.week} row below.
                    </div>

                    {pvdLoading && <div style={{ fontSize: 13, color: theme.textSecondary }}>Loading…</div>}

                    {!pvdLoading && pvdData && pvdData.rows.length === 0 && (
                      <div style={{ fontSize: 13, color: theme.textSecondary }}>
                        No {POSITION_PLURAL[pvdPosition] ?? pvdPosition} have faced {nextGame.opponent} yet this season.
                      </div>
                    )}

                    {!pvdLoading && pvdData && pvdData.rows.length > 0 && (
                      isMobile ? (
                        <div>
                          {pvdData.rows.map((r, i) => (
                            <div key={i} style={{
                              padding: '10px 0', borderBottom: i < pvdData.rows.length - 1 ? `1px solid ${theme.border}` : 'none',
                            }}>
                              <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 2 }}>
                                Week {r.week} — {r.matchup}
                              </div>
                              <div style={{ fontWeight: 700, color: theme.dataBlue, marginBottom: 2 }}>{r.player} <span style={{ fontWeight: 400, color: theme.textSecondary, fontSize: 12 }}>{r.team}</span></div>
                              <div style={{ fontSize: 13, color: theme.textPrimary }}>
                                {pvdPosition === 'QB'
                                  ? `${r.attempts} att, ${r.completions} cmp, ${r.passing_yards} pass yds, ${r.passing_tds} TD, ${r.passing_interceptions} INT${r.rushing_yards ? ` · ${r.rushing_yards} rush yds` : ''}`
                                  : pvdPosition === 'RB'
                                  ? `${r.carries} att, ${r.rushing_yards} rush yds, ${r.rushing_tds} TD · ${r.targets} tgt, ${r.receptions} rec, ${r.receiving_yards} rec yds`
                                  : `${r.targets} tgt, ${r.receptions} rec, ${r.receiving_yards} rec yds, ${r.receiving_tds} TD`}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                          <thead>
                            <tr>
                              <th style={{ padding: '9px 12px', textAlign: 'left', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Week</th>
                              <th style={{ padding: '9px 12px', textAlign: 'left', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Player</th>
                              <th style={{ padding: '9px 12px', textAlign: 'left', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Team</th>
                              {pvdPosition === 'RB' && (
                                <>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Att</th>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Rush Yds</th>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Rush TD</th>
                                </>
                              )}
                              {pvdPosition === 'QB' ? (
                                <>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Att</th>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Cmp</th>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Pass Yds</th>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Pass TD</th>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>INT</th>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Rush Yds</th>
                                </>
                              ) : (
                                <>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Tgt</th>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Rec</th>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Rec Yds</th>
                                  <th style={{ padding: '9px 12px', textAlign: 'center', background: theme.bgCardHover, color: theme.textPrimary, fontWeight: 600 }}>Rec TD</th>
                                </>
                              )}
                            </tr>
                          </thead>
                          <tbody>
                            {(() => {
                              const elements: React.ReactElement[] = [];
                              let lastWeekKey: string | null = null;
                              pvdData.rows.forEach((r, i) => {
                                const weekKey = `${r.week}-${r.matchup}`;
                                if (weekKey !== lastWeekKey) {
                                  lastWeekKey = weekKey;
                                  const colSpan = pvdPosition === 'RB' ? 10 : pvdPosition === 'QB' ? 9 : 7;
                                  elements.push(
                                    <tr key={`div-${weekKey}`}>
                                      <td colSpan={colSpan} style={{
                                        padding: '6px 12px', background: theme.bgPage, color: theme.textMuted,
                                        fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.04em',
                                        borderBottom: `1px solid ${theme.border}`,
                                      }}>
                                        Week {r.week} — {r.matchup}
                                      </td>
                                    </tr>
                                  );
                                }
                                elements.push(
                                  <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: theme.bgPage }}>
                                    <td style={{ padding: '8px 14px', color: theme.textPrimary }}>{r.week}</td>
                                    <td style={{ padding: '8px 14px', fontWeight: 600, color: theme.dataBlue }}>{r.player}</td>
                                    <td style={{ padding: '8px 14px', color: theme.textSecondary }}>{r.team}</td>
                                    {pvdPosition === 'RB' && (
                                      <>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.carries}</td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.rushing_yards}</td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.rushing_tds}</td>
                                      </>
                                    )}
                                    {pvdPosition === 'QB' ? (
                                      <>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.attempts}</td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.completions}</td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.passing_yards}</td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.passing_tds}</td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.passing_interceptions}</td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.rushing_yards}</td>
                                      </>
                                    ) : (
                                      <>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.targets}</td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.receptions}</td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.receiving_yards}</td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.receiving_tds}</td>
                                      </>
                                    )}
                                  </tr>
                                );
                              });
                              return elements;
                            })()}
                          </tbody>
                        </table>
                      )
                    )}

                    {!pvdLoading && pvdData && pvdData.excluded.length > 0 && (
                      <>
                        <span
                          onClick={() => setShowExcluded((v) => !v)}
                          style={{ marginTop: 14, fontSize: 12.5, color: theme.accent, cursor: 'pointer', display: 'inline-block', userSelect: 'none' }}
                        >
                          {showExcluded ? 'Hide' : 'Show'} {pvdData.excluded.length} filtered out {showExcluded ? '▴' : '▾'}
                        </span>
                        {showExcluded && (
                          <div style={{
                            marginTop: 10, padding: '12px 14px', background: theme.bgCard, border: `1px solid ${theme.border}`,
                            borderRadius: 6, fontSize: 12.5, color: theme.textMuted, lineHeight: 1.7,
                          }}>
                            {pvdData.excluded.map((item, i) => (
                              <div key={i}>{formatExcluded(item, pvdPosition)}</div>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}

                {pvdPosition && nextGame && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '4px 0 10px' }}>
                    <div style={{ flex: 1, height: 1, background: theme.border }} />
                    <div style={{ fontSize: 11, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>Rest of schedule</div>
                    <div style={{ flex: 1, height: 1, background: theme.border }} />
                  </div>
                )}

                {isMobile ? (
                  <div>
                    {gameData.upcoming.map((g, i) => (
                      <StatCard
                        key={i}
                        title={
                          <span style={{ fontWeight: 700 }}>
                            Week {g.week} · vs {g.opponent}
                            {i === 0 && pvdPosition && (
                              <span style={{ fontWeight: 400, fontSize: 11, color: theme.textMuted }}> (detailed above)</span>
                            )}
                          </span>
                        }
                        value={g.def_ypg_rank_current != null ? ordinal(g.def_ypg_rank_current) : '—'}
                        valueColor={rankColor(g.def_ypg_rank_current)}
                        valueLabel="Opp D (Yds/G)"
                        meta={[
                          <>
                            Yds/Att{' '}
                            <span style={{ color: rankColor(g.def_ypa_rank_current), fontWeight: 600 }}>
                              {g.def_ypa_rank_current != null ? ordinal(g.def_ypa_rank_current) : '—'}
                            </span>
                          </>,
                          <span style={{ color: theme.textMuted }}>current-season ranks</span>,
                        ]}
                      />
                    ))}
                  </div>
                ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <thead>
                    <tr style={{ background: theme.bgCard }}>
                      <th style={{ padding: '10px 14px', textAlign: 'left', fontSize: 12, color: theme.textSecondary }}>Week</th>
                      <th style={{ padding: '10px 14px', textAlign: 'left', fontSize: 12, color: theme.textSecondary }}>Opponent</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right', fontSize: 12, color: theme.textSecondary }}>Opp D Rank (Yds/G)</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right', fontSize: 12, color: theme.textSecondary }}>Opp D Rank (Yds/Att)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gameData.upcoming.map((g, i) => (
                      <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgPage : theme.bgCard, color: theme.textPrimary }}>
                        <td style={{ padding: '8px 14px' }}>W{g.week}</td>
                        <td style={{ padding: '8px 14px' }}>
                          {g.opponent}
                          {i === 0 && pvdPosition && (
                            <span style={{ fontSize: 11, color: theme.textMuted }}> (detailed above)</span>
                          )}
                        </td>
                        <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: rankColor(g.def_ypg_rank_current) }}>
                          {g.def_ypg_rank_current != null ? ordinal(g.def_ypg_rank_current) : '—'}
                          <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 400 }}> (current)</span>
                        </td>
                        <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: rankColor(g.def_ypa_rank_current) }}>
                          {g.def_ypa_rank_current != null ? ordinal(g.def_ypa_rank_current) : '—'}
                          <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 400 }}> (current)</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                )}
              </>
            )}
          </>
        )}
        {!loading && !error && !gameData && (
          <div style={{ color: theme.textSecondary, marginTop: 60, textAlign: 'center', fontSize: 16, background: theme.bgPage, minHeight: '100%' }}>
            Select a player and stat, then click "Get Stats".
          </div>
        )}
      </div>
    </div>
  );
}
