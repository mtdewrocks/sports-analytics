import { useState, useEffect, useRef } from 'react';
import { getMLBGameLogPlayers, getMLBGameLog } from '../../api/mlb';
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
// NBA and NFL Game Log pages are built on, with the two splits that are
// specifically an MLB thing: Home/Away and vs LHP/vs RHP (the opposing
// starter's throwing hand, matched game-by-game -- see
// _mlb_starting_pitcher_hand() in backend/app/data/mlb.py, the same read
// the Pitcher Matchup page's own vs L / vs R splits come from). A 150+ game
// MLB season also makes "Last 5" too small a window to bother with and
// "Last 25" a genuinely useful one, so the hit-rate table shows Last 10 /
// Last 25 / Season instead of NBA/NFL's Last 5 / Last 10 / Season -- and the
// bar chart, which every game log page renders unscaled, is capped server
// -side to the last 60 games so a full season doesn't turn it into an
// unreadable smear.

const STAT_OPTIONS: { value: string; label: string }[] = [
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

type HomeAway = 'all' | 'home' | 'away';
type PitcherHand = 'all' | 'L' | 'R';

interface Game {
  game_date: string;
  opponent: string;
  is_home: boolean;
  at_bats?: number | null;
  hits?: number | null;
  opp_pitcher?: string | null;
  opp_pitcher_hand?: 'L' | 'R' | null;
  stat_value: number;
}

interface OverCount { over: number; total: number; pct: number; }

interface GameData {
  games: Game[];
  over_counts: { last10: OverCount; last25: OverCount; season: OverCount };
}

const labelStyle = fieldLabelStyle;
const inputStyle = fieldStyle;

const OVER_COUNTS_PERIODS = [
  { key: 'last10', label: 'Last 10' },
  { key: 'last25', label: 'Last 25' },
  { key: 'season', label: 'Season' },
];

function formatStatLabel(stat: string): string {
  return STAT_OPTIONS.find((s) => s.value === stat)?.label ?? stat;
}

function opponentLabel(g: Game): string {
  return (g.is_home ? 'vs ' : '@ ') + g.opponent;
}

function pitcherLabel(g: Game): string {
  if (!g.opp_pitcher) return '—';
  return g.opp_pitcher_hand ? `${g.opp_pitcher} (${g.opp_pitcher_hand})` : g.opp_pitcher;
}

export default function MLBGameLog() {
  const [players, setPlayers] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState('');
  const [selectedStat, setSelectedStat] = useState('batter_hits');
  const [thresholdStr, setThresholdStr] = useState('');
  const [homeAway, setHomeAway] = useState<HomeAway>('all');
  const [pitcherHand, setPitcherHand] = useState<PitcherHand>('all');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [gameData, setGameData] = useState<GameData | null>(null);
  const isMobile = useIsMobile();
  const panelLayout = usePanelLayout();

  useEffect(() => {
    getMLBGameLogPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
  }, []);

  // Guards an older request's response landing after a newer one's -- matters
  // now that a fetch can fire on its own (the toggle effect below) rather
  // than only from a single button click at a time.
  const requestIdRef = useRef(0);

  const fetchStats = async () => {
    if (!selectedPlayer) return;
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError('');
    setGameData(null);
    try {
      const threshold = parseFloat(thresholdStr) || 0;
      const params: Record<string, any> = { player: selectedPlayer, stat: selectedStat, threshold };
      if (homeAway !== 'all') params.home_away = homeAway;
      if (pitcherHand !== 'all') params.pitcher_hand = pitcherHand;
      const res = await getMLBGameLog(params);
      if (requestId === requestIdRef.current) setGameData(res.data);
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
    if (gameData) fetchStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [homeAway, pitcherHand]);

  const recentGames = gameData ? gameData.games.slice(-25).reverse() : [];
  const threshold = parseFloat(thresholdStr) || 0;

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
            players={players}
            value={selectedPlayer}
            onSelect={setSelectedPlayer}
            placeholder="Search by first or last name..."
            inputStyle={{ padding: 8 }}
          />
        </div>

        <label style={labelStyle}>Stat</label>
        <select style={inputStyle} value={selectedStat} onChange={(e) => setSelectedStat(e.target.value)}>
          {STAT_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
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
        <div style={{ marginBottom: 16 }}>
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
              {selectedPlayer} — {formatStatLabel(selectedStat)} (Line: {threshold})
              {homeAway !== 'all' && (
                <span style={{ color: theme.textSecondary, fontWeight: 400, fontSize: 16 }}>
                  {' '}· {homeAway === 'home' ? 'Home Only' : 'Away Only'}
                </span>
              )}
              {pitcherHand !== 'all' && (
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
                <StatChart games={gameData.games} threshold={threshold} stat={formatStatLabel(selectedStat)} />
                <OverCountsTable
                  over_counts={gameData.over_counts}
                  threshold={threshold}
                  stat={formatStatLabel(selectedStat)}
                  periods={OVER_COUNTS_PERIODS}
                />

                <h3 style={{ marginTop: 28, marginBottom: 12, color: theme.textPrimary }}>Recent Games (Last 25)</h3>

                {isMobile ? (
                  <div>
                    {recentGames.map((g, i) => (
                      <StatCard
                        key={i}
                        title={g.game_date}
                        titleAside={opponentLabel(g)}
                        value={g.stat_value}
                        valueColor={g.stat_value >= threshold ? theme.dataBlue : theme.dataRed}
                        footer={formatStatLabel(selectedStat)}
                        meta={[
                          g.at_bats != null && g.hits != null ? `${g.hits}-${g.at_bats}` : null,
                          pitcherLabel(g) !== '—' ? pitcherLabel(g) : null,
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
                        <th style={{ padding: '10px 14px', textAlign: 'center' }}>H</th>
                        <th style={{ padding: '10px 14px', textAlign: 'center' }}>{formatStatLabel(selectedStat)}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recentGames.map((g, i) => (
                        <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgPage : theme.bgCard, color: theme.textPrimary }}>
                          <td style={{ padding: '8px 14px' }}>{g.game_date}</td>
                          <td style={{ padding: '8px 14px' }}>{opponentLabel(g)}</td>
                          <td style={{ padding: '8px 14px', color: theme.textSecondary }}>{pitcherLabel(g)}</td>
                          <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                            {g.at_bats ?? '—'}
                          </td>
                          <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                            {g.hits ?? '—'}
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
                )}
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
