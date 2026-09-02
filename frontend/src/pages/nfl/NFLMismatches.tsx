import { useState, useEffect } from 'react';
import { getNFLMismatchCategories, getNFLMismatches } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';

interface Category {
  key: string;
  label: string;
}

interface MismatchGame {
  matchup: string;
  offense_team: string;
  defense_team: string;
  offense_rank: number;
  defense_rank: number;
  offense_value: number | null;
  defense_value: number | null;
  score: number;
}

interface MismatchData {
  category: string;
  label: string;
  offense_label: string;
  defense_label: string;
  week: number;
  games: MismatchGame[];
  error?: string;
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

// Same absolute-tier convention used on the Matchup and Game Log pages:
// top 10 of 32 teams, bottom 10, middle 12.
function rankColor(rank: number): string {
  if (rank <= 10) return '#1565c0';
  if (rank >= 23) return '#c62828';
  return '#1a1a2e';
}

export default function NFLMismatches() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<MismatchData | null>(null);

  useEffect(() => {
    getNFLMismatchCategories()
      .then((res) => {
        setCategories(res.data);
        if (res.data.length > 0) setSelectedCategory(res.data[0].key);
      })
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (!selectedCategory) return;
    setLoading(true);
    setError('');
    getNFLMismatches(selectedCategory)
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to fetch mismatches.'))
      .finally(() => setLoading(false));
  }, [selectedCategory]);

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: '#1a1a2e' }}>NFL Weekly Mismatches</h2>
      <div style={{ fontSize: 13, color: '#888', marginBottom: 20 }}>
        Every game on this week's slate, ranked by how lopsided the matchup is for the stat you pick.
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 24 }}>
        {categories.map((c) => (
          <button
            key={c.key}
            onClick={() => setSelectedCategory(c.key)}
            style={{
              padding: '8px 16px', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer',
              border: c.key === selectedCategory ? '1px solid #1a1a2e' : '1px solid #ddd',
              background: c.key === selectedCategory ? '#1a1a2e' : 'white',
              color: c.key === selectedCategory ? 'white' : '#444',
            }}
          >
            {c.label}
          </button>
        ))}
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b' }}>
          {error}
        </div>
      )}

      {!loading && !error && data && data.error && (
        <div style={{ color: '#999', textAlign: 'center', marginTop: 40 }}>{data.error}</div>
      )}

      {!loading && !error && data && !data.error && (
        <>
          <div style={{ fontSize: 13, color: '#888', marginBottom: 12 }}>Week {data.week}</div>

          {data.games.length === 0 ? (
            <div style={{ color: '#999', textAlign: 'center', marginTop: 40 }}>
              No games with enough data for this category yet -- check back once more of the season has been played.
            </div>
          ) : (
            <div style={{ background: 'white', borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.08)', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: '#1a1a2e', color: 'white' }}>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Matchup</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>{data.offense_label}</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>{data.defense_label}</th>
                    <th style={{ padding: '10px 14px', textAlign: 'right' }}>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {data.games.map((g, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f0f0f0', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                      <td style={{ padding: '9px 14px', color: '#888', fontSize: 12 }}>{g.matchup}</td>
                      <td style={{ padding: '9px 14px' }}>
                        <span style={{ fontWeight: 700 }}>{g.offense_team}</span>{' '}
                        <span style={{ color: rankColor(g.offense_rank), fontWeight: 600 }}>
                          {ordinal(g.offense_rank)}
                        </span>
                        {g.offense_value != null && <span style={{ color: '#999' }}> ({g.offense_value})</span>}
                      </td>
                      <td style={{ padding: '9px 14px' }}>
                        <span style={{ fontWeight: 700 }}>{g.defense_team}</span>{' '}
                        <span style={{ color: rankColor(g.defense_rank), fontWeight: 600 }}>
                          {ordinal(g.defense_rank)}
                        </span>
                        {g.defense_value != null && <span style={{ color: '#999' }}> ({g.defense_value})</span>}
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', fontWeight: 700 }}>{g.score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ fontSize: 11, color: '#aaa', marginTop: 16, textAlign: 'center' }}>
            Ranks are out of 32 teams (1 = best). Early in the season these are based on a small number of
            games and can move quickly -- treat them as more reliable once a few weeks have been played.
          </div>
        </>
      )}
    </div>
  );
}
