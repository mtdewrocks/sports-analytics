import React, { useState, useEffect } from 'react';
import { getNBAPlayers, getNBATeammates, getNBAGameLog } from '../../api/nba';
import StatChart from '../../components/StatChart';
import OverCountsTable from '../../components/OverCountsTable';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import { theme } from '../../theme';

const STAT_OPTIONS = ['pts', 'reb', 'ast', 'stl', 'blk', 'tov', '3pm', 'pra', 'blk_stl', 'reb_ast', 'pts_ast', 'pts_reb'];

interface Game {
  game_date: string;
  opponent: string;
  stat_value: number;
  min?: number | string;
  fgm?: number | null;
  fga?: number | null;
}

interface OverCount {
  over: number;
  total: number;
  pct: number;
}

interface GameData {
  games: Game[];
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
  borderRadius: 4,
  boxSizing: 'border-box',
  background: theme.bgPage,
  color: theme.textPrimary,
};

export default function NBAGameLog() {
  const [players, setPlayers] = useState<string[]>([]);
  const [teammates, setTeammates] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState('');
  const [playerSearch, setPlayerSearch] = useState('');
  const [showPlayerDropdown, setShowPlayerDropdown] = useState(false);
  const [selectedStat, setSelectedStat] = useState('pts');
  const [thresholdStr, setThresholdStr] = useState('');
  const [minMinutesStr, setMinMinutesStr] = useState('');
  const [withPlayer, setWithPlayer] = useState('');
  const [withoutPlayer, setWithoutPlayer] = useState('');
  const [b2b, setB2b] = useState(false);
  const [threeInFour, setThreeInFour] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [gameData, setGameData] = useState<GameData | null>(null);

  useEffect(() => {
    getNBAPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
  }, []);

  useEffect(() => {
    if (!selectedPlayer) {
      setTeammates([]);
      return;
    }
    getNBATeammates(selectedPlayer)
      .then((res) => setTeammates(res.data))
      .catch(() => setTeammates([]));
  }, [selectedPlayer]);

  const fetchStats = async () => {
    if (!selectedPlayer) return;
    setLoading(true);
    setError('');
    setGameData(null);
    try {
      const threshold = parseFloat(thresholdStr) || 0;
      const minMinutes = parseInt(minMinutesStr) || 0;
      const params: Record<string, any> = {
        player: selectedPlayer,
        stat: selectedStat,
        threshold,
        b2b,
        three_in_four: threeInFour,
      };
      if (minMinutes > 0) params.min_minutes = minMinutes;
      if (withPlayer) params.with_player = withPlayer;
      if (withoutPlayer) params.without_player = withoutPlayer;
      const res = await getNBAGameLog(params);
      setGameData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch game log.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 60px)' }}>
      {/* Sidebar */}
      <div style={{ width: 240, background: theme.bgCard, padding: '16px 16px', height: 'calc(100vh - 60px)', overflowY: 'auto', flexShrink: 0 }}>
        <h3 style={{ marginTop: 0, marginBottom: 20, fontSize: 16, fontWeight: 700, color: theme.textPrimary }}>NBA Game Log</h3>

        <label style={labelStyle}>Player</label>
        <div style={{ position: 'relative', marginBottom: 16 }}>
          <input
            style={{ ...inputStyle, marginBottom: 0 }}
            placeholder="Search by first or last name..."
            value={playerSearch}
            onChange={(e) => {
              setPlayerSearch(e.target.value);
              setSelectedPlayer('');
              setShowPlayerDropdown(true);
            }}
            onFocus={() => setShowPlayerDropdown(true)}
            onBlur={() => setTimeout(() => setShowPlayerDropdown(false), 150)}
          />
          {showPlayerDropdown && playerSearch.length > 0 && (
            <div style={{
              position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
              background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 4,
              maxHeight: 200, overflowY: 'auto', boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
            }}>
              {players
                .filter((p) => p.toLowerCase().includes(playerSearch.toLowerCase()))
                .map((p) => (
                  <div
                    key={p}
                    onMouseDown={() => {
                      setSelectedPlayer(p);
                      setPlayerSearch(p);
                      setShowPlayerDropdown(false);
                    }}
                    style={{
                      padding: '8px 12px', cursor: 'pointer', fontSize: 13, color: theme.textPrimary,
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = theme.bgCardHover)}
                    onMouseLeave={(e) => (e.currentTarget.style.background = theme.bgCard)}
                  >
                    {p}
                  </div>
                ))}
              {players.filter((p) => p.toLowerCase().includes(playerSearch.toLowerCase())).length === 0 && (
                <div style={{ padding: '8px 12px', color: theme.textMuted, fontSize: 13 }}>No players found</div>
              )}
            </div>
          )}
        </div>

        <label style={labelStyle}>Stat</label>
        <select style={inputStyle} value={selectedStat} onChange={(e) => setSelectedStat(e.target.value)}>
          {STAT_OPTIONS.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
        </select>

        <label style={labelStyle}>Threshold</label>
        <input
          type="number"
          min={0}
          max={100}
          step={1}
          style={inputStyle}
          placeholder="e.g. 20"
          value={thresholdStr}
          onFocus={(e) => e.target.select()}
          onChange={(e) => setThresholdStr(e.target.value)}
        />

        <label style={labelStyle}>Minimum Minutes Played</label>
        <input
          type="number"
          min={0}
          max={48}
          step={1}
          style={inputStyle}
          placeholder="e.g. 20"
          value={minMinutesStr}
          onFocus={(e) => e.target.select()}
          onChange={(e) => setMinMinutesStr(e.target.value)}
        />

        <label style={labelStyle}>With Player</label>
        <div style={{ marginBottom: 16 }}>
          <SearchDropdown
            players={teammates}
            value={withPlayer}
            onSelect={setWithPlayer}
            placeholder={selectedPlayer ? 'Search teammate...' : 'Select player first'}
            disabled={!selectedPlayer || teammates.length === 0}
            inputStyle={{ padding: 8 }}
          />
        </div>

        <label style={labelStyle}>Without Player</label>
        <div style={{ marginBottom: 16 }}>
          <SearchDropdown
            players={teammates}
            value={withoutPlayer}
            onSelect={setWithoutPlayer}
            placeholder={selectedPlayer ? 'Search teammate...' : 'Select player first'}
            disabled={!selectedPlayer || teammates.length === 0}
            inputStyle={{ padding: 8 }}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={b2b} onChange={(e) => setB2b(e.target.checked)} />
            Back-to-Back Only
          </label>
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={threeInFour} onChange={(e) => setThreeInFour(e.target.checked)} />
            3-in-4 Only
          </label>
        </div>

        <button
          onClick={fetchStats}
          disabled={!selectedPlayer || loading}
          style={{
            width: '100%',
            padding: '10px 0',
            background: theme.accent,
            color: 'white',
            border: 'none',
            borderRadius: 4,
            fontWeight: 700,
            fontSize: 14,
            cursor: selectedPlayer && !loading ? 'pointer' : 'not-allowed',
            opacity: selectedPlayer && !loading ? 1 : 0.6,
          }}
        >
          Get Stats
        </button>
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, padding: '16px 20px', overflowY: 'auto', background: theme.bgPage }}>
        {loading && <LoadingSpinner />}
        {error && (
          <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
            {error}
          </div>
        )}
        {!loading && !error && gameData && (
          <>
            <h2 style={{ marginTop: 0, color: theme.textPrimary }}>
              {selectedPlayer} — {selectedStat.toUpperCase()} (Line: {parseFloat(thresholdStr) || 0})
            </h2>
            <StatChart games={gameData.games} threshold={parseFloat(thresholdStr) || 0} stat={selectedStat} />
            <OverCountsTable over_counts={gameData.over_counts} threshold={parseFloat(thresholdStr) || 0} stat={selectedStat} />
            <h3 style={{ marginTop: 28, marginBottom: 12, color: theme.textPrimary }}>Recent Games (Last 10)</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Date</th>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Opponent</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>MIN</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>FGA</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>FG</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>FG%</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>{selectedStat.toUpperCase()}</th>
                </tr>
              </thead>
              <tbody>
                {[...gameData.games].slice(-10).reverse().map((g, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgPage : theme.bgCard, color: theme.textPrimary }}>
                    <td style={{ padding: '8px 14px' }}>{g.game_date}</td>
                    <td style={{ padding: '8px 14px' }}>{g.opponent}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                      {g.min ?? '—'}
                    </td>
                    <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                      {g.fga != null ? g.fga : '—'}
                    </td>
                    <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                      {g.fgm != null && g.fga != null ? `${g.fgm}-${g.fga}` : '—'}
                    </td>
                    <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                      {g.fgm != null && g.fga != null && g.fga > 0
                        ? `${Math.round((g.fgm / g.fga) * 100)}%`
                        : '—'}
                    </td>
                    <td style={{
                      padding: '8px 14px',
                      textAlign: 'center',
                      fontWeight: 700,
                      color: g.stat_value > (parseFloat(thresholdStr) || 0) ? theme.dataBlue : theme.dataRed,
                    }}>
                      {g.stat_value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
