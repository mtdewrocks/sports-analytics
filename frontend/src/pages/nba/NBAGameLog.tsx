import React, { useState, useEffect } from 'react';
import { getNBAPlayers, getNBATeammates, getNBAGameLog } from '../../api/nba';
import StatChart from '../../components/StatChart';
import OverCountsTable from '../../components/OverCountsTable';
import LoadingSpinner from '../../components/LoadingSpinner';

const STAT_OPTIONS = ['pts', 'reb', 'ast', 'stl', 'blk', 'tov', '3pm', 'pra', 'blk_stl', 'reb_ast', 'pts_ast', 'pts_reb'];

interface Game {
  game_date: string;
  opponent: string;
  stat_value: number;
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
  border: '1px solid #ddd',
  borderRadius: 4,
  boxSizing: 'border-box',
};

export default function NBAGameLog() {
  const [players, setPlayers] = useState<string[]>([]);
  const [teammates, setTeammates] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState('');
  const [selectedStat, setSelectedStat] = useState('pts');
  const [threshold, setThreshold] = useState(0);
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
      const params: Record<string, any> = {
        player: selectedPlayer,
        stat: selectedStat,
        threshold,
        b2b,
        three_in_four: threeInFour,
      };
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
      <div style={{ width: 280, background: '#f8f9fa', padding: 20, height: 'calc(100vh - 60px)', overflowY: 'auto', flexShrink: 0 }}>
        <h3 style={{ marginTop: 0, marginBottom: 20, fontSize: 16, fontWeight: 700, color: '#1a1a2e' }}>NBA Game Log</h3>

        <label style={labelStyle}>Player</label>
        <select style={inputStyle} value={selectedPlayer} onChange={(e) => setSelectedPlayer(e.target.value)}>
          <option value="">-- Select Player --</option>
          {players.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>

        <label style={labelStyle}>Stat</label>
        <select style={inputStyle} value={selectedStat} onChange={(e) => setSelectedStat(e.target.value)}>
          {STAT_OPTIONS.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
        </select>

        <label style={labelStyle}>Threshold</label>
        <input
          type="number"
          min={0}
          max={60}
          step={0.5}
          style={inputStyle}
          value={threshold}
          onChange={(e) => setThreshold(parseFloat(e.target.value) || 0)}
        />

        <label style={labelStyle}>With Player</label>
        <select style={inputStyle} value={withPlayer} onChange={(e) => setWithPlayer(e.target.value)}>
          <option value="">-- None --</option>
          {teammates.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>

        <label style={labelStyle}>Without Player</label>
        <select style={inputStyle} value={withoutPlayer} onChange={(e) => setWithoutPlayer(e.target.value)}>
          <option value="">-- None --</option>
          {teammates.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>

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
            background: '#1a1a2e',
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
              {selectedPlayer} — {selectedStat.toUpperCase()} (Line: {threshold})
            </h2>
            <StatChart games={gameData.games} threshold={threshold} stat={selectedStat} />
            <OverCountsTable over_counts={gameData.over_counts} threshold={threshold} stat={selectedStat} />
            <h3 style={{ marginTop: 28, marginBottom: 12, color: '#1a1a2e' }}>Recent Games</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: '#1a1a2e', color: 'white' }}>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Date</th>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Opponent</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>{selectedStat.toUpperCase()}</th>
                </tr>
              </thead>
              <tbody>
                {gameData.games.map((g, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #eee', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                    <td style={{ padding: '8px 14px' }}>{g.game_date}</td>
                    <td style={{ padding: '8px 14px' }}>{g.opponent}</td>
                    <td style={{
                      padding: '8px 14px',
                      textAlign: 'center',
                      fontWeight: 700,
                      color: g.stat_value > threshold ? '#2ecc71' : '#e74c3c',
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
          <div style={{ color: '#999', marginTop: 60, textAlign: 'center', fontSize: 16 }}>
            Select a player and click "Get Stats" to view game log.
          </div>
        )}
      </div>
    </div>
  );
}
