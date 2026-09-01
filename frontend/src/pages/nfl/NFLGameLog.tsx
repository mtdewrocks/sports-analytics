import React, { useState, useEffect } from 'react';
import { getNFLPlayers, getNFLStats, getNFLGameLog } from '../../api/nfl';
import StatChart from '../../components/StatChart';
import OverCountsTable from '../../components/OverCountsTable';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';

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
  border: '1px solid #ddd',
  borderRadius: 4,
  boxSizing: 'border-box',
};

// Same absolute-tier convention as the Matchup page: top 10 of 32 teams,
// bottom 10, middle 12 -- rather than comparing anything to an opponent.
function rankColor(rank: number | null | undefined): string {
  if (rank == null) return '#1a1a2e';
  if (rank <= 10) return '#1565c0';
  if (rank >= 23) return '#c62828';
  return '#1a1a2e';
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
      <div style={{ width: 280, background: '#f8f9fa', padding: 20, height: 'calc(100vh - 60px)', overflowY: 'auto', flexShrink: 0 }}>
        <h3 style={{ marginTop: 0, marginBottom: 20, fontSize: 16, fontWeight: 700, color: '#1a1a2e' }}>NFL Game Log</h3>

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
          {stats.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
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
            background: '#1a1a2e',
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
      <div style={{ flex: 1, padding: 24, overflowY: 'auto' }}>
        {loading && <LoadingSpinner />}
        {error && (
          <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b' }}>
            {error}
          </div>
        )}
        {!loading && !error && gameData && (
          <>
            <h2 style={{ marginTop: 0, color: '#1a1a2e' }}>
              {selectedPlayer} — {selectedStat.toUpperCase()} (Line: {parseFloat(thresholdStr) || 0})
            </h2>
            <StatChart games={gameData.games} threshold={parseFloat(thresholdStr) || 0} stat={selectedStat} />
            <OverCountsTable over_counts={gameData.over_counts} threshold={parseFloat(thresholdStr) || 0} stat={selectedStat} />

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 28, marginBottom: 12 }}>
              <h3 style={{ margin: 0, color: '#1a1a2e' }}>Recent Games</h3>
              {hasDefContext && (
                <div style={{ display: 'flex', gap: 4, background: '#f0f0f0', borderRadius: 4, padding: 3 }}>
                  <button
                    onClick={() => setRankMode('season')}
                    style={{
                      border: 'none', padding: '5px 12px', fontSize: 13, borderRadius: 4, cursor: 'pointer',
                      background: rankMode === 'season' ? 'white' : 'transparent',
                      fontWeight: rankMode === 'season' ? 700 : 400,
                      color: rankMode === 'season' ? '#1a1a2e' : '#666',
                    }}
                  >
                    Season
                  </button>
                  <button
                    onClick={() => setRankMode('last4')}
                    style={{
                      border: 'none', padding: '5px 12px', fontSize: 13, borderRadius: 4, cursor: 'pointer',
                      background: rankMode === 'last4' ? 'white' : 'transparent',
                      fontWeight: rankMode === 'last4' ? 700 : 400,
                      color: rankMode === 'last4' ? '#1a1a2e' : '#666',
                    }}
                  >
                    Last 4 Games
                  </button>
                </div>
              )}
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: '#1a1a2e', color: 'white' }}>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Week</th>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Opponent</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>{selectedStat.toUpperCase()}</th>
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
                    <tr key={i} style={{ borderBottom: '1px solid #eee', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                      <td style={{ padding: '8px 14px' }}>{g.week ?? g.game_date ?? '—'}</td>
                      <td style={{ padding: '8px 14px' }}>{g.opponent ?? '—'}</td>
                      <td style={{
                        padding: '8px 14px',
                        textAlign: 'center',
                        fontWeight: 700,
                        color: g.stat_value > (parseFloat(thresholdStr) || 0) ? '#2ecc71' : '#e74c3c',
                      }}>
                        {g.stat_value}
                      </td>
                      {hasDefContext && (
                        <>
                          <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: rankColor(ypgRank) }}>
                            {ypgRank != null ? ordinal(ypgRank) : '—'}
                            {g.def_is_fallback && <span style={{ fontSize: 11, color: '#999', fontWeight: 400 }}> (prior yr)</span>}
                          </td>
                          <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: rankColor(ypaRank) }}>
                            {ypaRank != null ? ordinal(ypaRank) : '—'}
                            {g.def_is_fallback && <span style={{ fontSize: 11, color: '#999', fontWeight: 400 }}> (prior yr)</span>}
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
                <h3 style={{ marginTop: 28, marginBottom: 12, color: '#1a1a2e' }}>Upcoming</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <thead>
                    <tr style={{ background: '#f0f0f0' }}>
                      <th style={{ padding: '10px 14px', textAlign: 'left', fontSize: 12, color: '#666' }}>Week</th>
                      <th style={{ padding: '10px 14px', textAlign: 'left', fontSize: 12, color: '#666' }}>Opponent</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right', fontSize: 12, color: '#666' }}>Opp D Rank (Yds/G)</th>
                      <th style={{ padding: '10px 14px', textAlign: 'right', fontSize: 12, color: '#666' }}>Opp D Rank (Yds/Att)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gameData.upcoming.map((g, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #eee', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                        <td style={{ padding: '8px 14px' }}>W{g.week}</td>
                        <td style={{ padding: '8px 14px' }}>{g.opponent}</td>
                        <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: rankColor(g.def_ypg_rank_current) }}>
                          {g.def_ypg_rank_current != null ? ordinal(g.def_ypg_rank_current) : '—'}
                          <span style={{ fontSize: 11, color: '#999', fontWeight: 400 }}> (current)</span>
                        </td>
                        <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: rankColor(g.def_ypa_rank_current) }}>
                          {g.def_ypa_rank_current != null ? ordinal(g.def_ypa_rank_current) : '—'}
                          <span style={{ fontSize: 11, color: '#999', fontWeight: 400 }}> (current)</span>
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
          <div style={{ color: '#999', marginTop: 60, textAlign: 'center', fontSize: 16 }}>
            Select a player and stat, then click "Get Stats".
          </div>
        )}
      </div>
    </div>
  );
}
