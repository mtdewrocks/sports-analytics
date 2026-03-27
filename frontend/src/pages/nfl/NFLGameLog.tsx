import React, { useState, useEffect } from 'react';
import { getNFLPlayers, getNFLStats, getNFLGameLog } from '../../api/nfl';
import StatChart from '../../components/StatChart';
import OverCountsTable from '../../components/OverCountsTable';
import LoadingSpinner from '../../components/LoadingSpinner';

interface Game {
  week?: number;
  opponent?: string;
  stat_value: number;
  game_date?: string;
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

export default function NFLGameLog() {
  const [players, setPlayers] = useState<string[]>([]);
  const [stats, setStats] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState('');
  const [selectedStat, setSelectedStat] = useState('');
  const [threshold, setThreshold] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [gameData, setGameData] = useState<GameData | null>(null);

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
      const res = await getNFLGameLog({ player: selectedPlayer, stat: selectedStat, threshold });
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
        <h3 style={{ marginTop: 0, marginBottom: 20, fontSize: 16, fontWeight: 700, color: '#1a1a2e' }}>NFL Game Log</h3>

        <label style={labelStyle}>Player</label>
        <select style={inputStyle} value={selectedPlayer} onChange={(e) => setSelectedPlayer(e.target.value)}>
          <option value="">-- Select Player --</option>
          {players.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>

        <label style={labelStyle}>Stat</label>
        <select style={inputStyle} value={selectedStat} onChange={(e) => setSelectedStat(e.target.value)}>
          <option value="">-- Select Stat --</option>
          {stats.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
        </select>

        <label style={labelStyle}>Threshold</label>
        <input
          type="number"
          min={0}
          step={0.5}
          style={inputStyle}
          value={threshold}
          onChange={(e) => setThreshold(parseFloat(e.target.value) || 0)}
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
              {selectedPlayer} — {selectedStat.toUpperCase()} (Line: {threshold})
            </h2>
            <StatChart games={gameData.games} threshold={threshold} stat={selectedStat} />
            <OverCountsTable over_counts={gameData.over_counts} threshold={threshold} stat={selectedStat} />
            <h3 style={{ marginTop: 28, marginBottom: 12, color: '#1a1a2e' }}>Recent Games</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: '#1a1a2e', color: 'white' }}>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Week</th>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Opponent</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>{selectedStat.toUpperCase()}</th>
                </tr>
              </thead>
              <tbody>
                {gameData.games.map((g, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #eee', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                    <td style={{ padding: '8px 14px' }}>{g.week ?? g.game_date ?? '—'}</td>
                    <td style={{ padding: '8px 14px' }}>{g.opponent ?? '—'}</td>
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
            Select a player and stat, then click "Get Stats".
          </div>
        )}
      </div>
    </div>
  );
}
