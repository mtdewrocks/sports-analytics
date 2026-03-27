import React, { useState, useEffect } from 'react';
import { getNFLMatchups, getNFLMatchup } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';

interface MatchupData {
  away_team: string;
  home_team: string;
  away_stats: Record<string, any>;
  home_stats: Record<string, any>;
}

function TeamCard({ teamName, stats }: { teamName: string; stats: Record<string, any> }) {
  return (
    <div style={{
      flex: 1,
      background: 'white',
      borderRadius: 8,
      boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
      overflow: 'hidden',
    }}>
      <div style={{ background: '#1a1a2e', color: 'white', padding: '14px 20px', fontWeight: 700, fontSize: 18 }}>
        {teamName}
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <tbody>
          {Object.entries(stats).map(([key, value], i) => (
            <tr key={key} style={{ borderBottom: '1px solid #f0f0f0', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
              <td style={{ padding: '8px 16px', fontWeight: 600, color: '#555', textTransform: 'capitalize' }}>
                {key.replace(/_/g, ' ')}
              </td>
              <td style={{ padding: '8px 16px', textAlign: 'right', fontWeight: 700, color: '#1a1a2e' }}>
                {String(value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function NFLMatchup() {
  const [matchups, setMatchups] = useState<string[]>([]);
  const [selectedMatchup, setSelectedMatchup] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetchingMatchups, setFetchingMatchups] = useState(true);
  const [error, setError] = useState('');
  const [matchupData, setMatchupData] = useState<MatchupData | null>(null);

  useEffect(() => {
    getNFLMatchups()
      .then((res) => {
        setMatchups(res.data);
        if (res.data.length > 0) setSelectedMatchup(res.data[0]);
      })
      .catch(() => setMatchups([]))
      .finally(() => setFetchingMatchups(false));
  }, []);

  const analyze = async () => {
    if (!selectedMatchup) return;
    setLoading(true);
    setError('');
    setMatchupData(null);
    try {
      const res = await getNFLMatchup(selectedMatchup);
      setMatchupData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch matchup data.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 24, overflowY: 'auto', minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 24, color: '#1a1a2e' }}>NFL Matchup Analysis</h2>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 28 }}>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Select Matchup</label>
          {fetchingMatchups ? (
            <div style={{ fontSize: 13, color: '#999', padding: '8px 0' }}>Loading matchups...</div>
          ) : (
            <select
              style={{ padding: '8px 12px', border: '1px solid #ddd', borderRadius: 4, fontSize: 14, minWidth: 240 }}
              value={selectedMatchup}
              onChange={(e) => setSelectedMatchup(e.target.value)}
            >
              <option value="">-- Select Matchup --</option>
              {matchups.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          )}
        </div>
        <button
          onClick={analyze}
          disabled={!selectedMatchup || loading}
          style={{
            padding: '9px 24px',
            background: '#1a1a2e',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            fontWeight: 700,
            fontSize: 14,
            cursor: selectedMatchup && !loading ? 'pointer' : 'not-allowed',
            opacity: selectedMatchup && !loading ? 1 : 0.6,
          }}
        >
          Analyze
        </button>
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b', marginBottom: 16 }}>
          {error}
        </div>
      )}
      {!loading && matchupData && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <TeamCard teamName={matchupData.away_team} stats={matchupData.away_stats} />
          <TeamCard teamName={matchupData.home_team} stats={matchupData.home_stats} />
        </div>
      )}
      {!loading && !error && !matchupData && !fetchingMatchups && (
        <div style={{ color: '#999', textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          Select a matchup and click "Analyze" to view team stats.
        </div>
      )}
    </div>
  );
}
