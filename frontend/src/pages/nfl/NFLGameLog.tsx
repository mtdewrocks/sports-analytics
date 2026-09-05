import React, { useState, useEffect } from 'react';
import { getNFLPlayers, getNFLStats, getNFLGameLog } from '../../api/nfl';
import StatChart from '../../components/StatChart';
import OverCountsTable from '../../components/OverCountsTable';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import { theme } from '../../theme';

interface Game {
  week?: number;
  opponent?: string;
  stat_value: number;
  game_date?: string;
  season?: number;
  def_ypg_season?: number | null;
  def_ypg_rank_season?: number | null;
  def_ypa_season?: number | null;
  def_ypa_rank_season?: number | null;
  def_ypg_last4?: number | null;
  def_ypg_rank_last4?: number | null;
  def_ypa_last4?: number | null;
  def_ypa_rank_last4?: number | null;
  def_is_fallback?: boolean;
  tooltip?: Record<string, number | null>;
}

interface UpcomingGame {
  week: number;
  opponent: string;
  def_ypg_current?: number | null;
  def_ypg_rank_current?: number | null;
  def_ypa_current?: number | null;
  def_ypa_rank_current?: number | null;
}

interface OverCount {
  over: number;
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
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  marginBottom: 4,
  fontWeight: 600,
  fontSize: 13,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: 8,
  marginBottom: 16,
  border: `1px solid ${theme.border}`,
  background: theme.bgPage,
  color: theme.textPrimary,
  borderRadius: 4,
  boxSizing: 'border-box',
};

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
};

function formatTooltip(tooltip?: Record<string, number | null>): string {
  if (!tooltip || Object.keys(tooltip).length === 0) return '';
  return Object.entries(tooltip)
    .map(([key, val]) => `${TOOLTIP_LABELS[key] ?? key}: ${val ?? '—'}`)
    .join(' \u00b7 ');
}

type RankMode = 'season' | 'last4';

export default function NFLGameLog() {
  const [players, setPlayers] = useState<string[]>([]);
  const [stats, setStats] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState('');
  const [selectedStat, setSelectedStat] = useState('');
  const [thresholdStr, setThresholdStr] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [gameData, setGameData] = useState<GameData | null>(null);
  const [rankMode, setRankMode] = useState<RankMode>('season');

  useEffect(() => {
    getNFLPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
    getNFLStats()
      .then((res) => {
        setStats(res.data);
        if (res.data.length > 0) setSelectedStat(res.data[0]);
      })
      .catch(() => setStats([]));
  }, []);

  const fetchStats = async () => {
    if (!selectedPlayer || !selectedStat) return;
    setLoading(true);
    setError('');
    setGameData(null);
    try {
      const threshold = parseFloat(thresholdStr) || 0;
      const res = await getNFLGameLog({ player: selectedPlayer, stat: selectedStat, threshold });
      setGameData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch game log.');
    } finally {
      setLoading(false);
    }
  };

  // Whether this stat has any defensive context at all -- a player's own
  // defensive stats (sacks, tackles) have no mapped opponent context, so
  // the extra columns and toggle simply don't render for those.
  const hasDefContext = !!gameData?.games.some((g) => g.def_ypg_rank_season != null)
    || !!gameData?.upcoming.some((g) => g.def_ypg_rank_current != null);

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 60px)' }}>
      {/* Sidebar */}
      <div style={{ width: 280, background: theme.bgCard, padding: 20, height: 'calc(100vh - 60px)', overflowY: 'auto', flexShrink: 0 }}>
        <h3 style={{ marginTop: 0, marginBottom: 20, fontSize: 16, fontWeight: 700, color: theme.textPrimary }}>NFL Game Log</h3>

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

        <button
          onClick={fetchStats}
          disabled={!selectedPlayer || !selectedStat || loading}
          style={{
            width: '100%',
            padding: '10px 0',
            background: theme.accent,
            color: 'white',
            border: 'none',
            borderRadius: 4,
            fontWeight: 700,
            fontSize: 14,
            cursor: selectedPlayer && selectedStat && !loading ? 'pointer' : 'not-allowed',
            opacity: selectedPlayer && selectedStat && !loading ? 1 : 0.6,
          }}
        >
          Get Stats
        </button>
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, padding: 24, overflowY: 'auto', background: theme.bgPage }}>
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
            </h2>
            <StatChart games={gameData.games} threshold={parseFloat(thresholdStr) || 0} stat={selectedStat} />
            <OverCountsTable over_counts={gameData.over_counts} threshold={parseFloat(thresholdStr) || 0} stat={selectedStat} />

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 28, marginBottom: 12 }}>
              <h3 style={{ margin: 0, color: theme.textPrimary }}>Recent Games</h3>
              {hasDefContext && (
                <div style={{ display: 'flex', gap: 4, background: theme.bgCard, borderRadius: 4, padding: 3 }}>
                  <button
                    onClick={() => setRankMode('season')}
                    style={{
                      border: 'none', padding: '5px 12px', fontSize: 13, borderRadius: 4, cursor: 'pointer',
                      background: rankMode === 'season' ? theme.bgCardHover : 'transparent',
                      fontWeight: rankMode === 'season' ? 700 : 400,
                      color: rankMode === 'season' ? theme.textPrimary : theme.textSecondary,
                    }}
                  >
                    Season
                  </button>
                  <button
                    onClick={() => setRankMode('last4')}
                    style={{
                      border: 'none', padding: '5px 12px', fontSize: 13, borderRadius: 4, cursor: 'pointer',
                      background: rankMode === 'last4' ? theme.bgCardHover : 'transparent',
                      fontWeight: rankMode === 'last4' ? 700 : 400,
                      color: rankMode === 'last4' ? theme.textPrimary : theme.textSecondary,
                    }}
                  >
                    Last 4 Games
                  </button>
                </div>
              )}
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Week</th>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Opponent</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>{formatStatLabel(selectedStat)}</th>
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

            {gameData.upcoming.length > 0 && (
              <>
                <h3 style={{ marginTop: 28, marginBottom: 12, color: theme.textPrimary }}>Upcoming</h3>
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
                        <td style={{ padding: '8px 14px' }}>{g.opponent}</td>
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
