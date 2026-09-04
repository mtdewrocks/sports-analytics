import React, { useState, useEffect } from 'react';
import { getNBAPlayers, getNBAProps } from '../../api/nba';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import { theme } from '../../theme';

const MARKETS = [
  { label: 'Points',          value: 'points' },
  { label: 'Rebounds',        value: 'rebounds' },
  { label: 'Assists',         value: 'assists' },
  { label: 'Steals',          value: 'steals' },
  { label: 'Blocks',          value: 'blocks' },
  { label: '3-Pointers',      value: '3-pointers' },
  { label: 'PTS+REB+AST',     value: 'pts+reb+ast' },
  { label: 'PTS+REB',         value: 'pts+reb' },
  { label: 'PTS+AST',         value: 'pts+ast' },
  { label: 'REB+AST',         value: 'reb+ast' },
  { label: 'BLK+STL',         value: 'blk+stl' },
];

const SPORTSBOOKS = [
  'betmgm', 'draftkings', 'espnbet', 'fanatics', 'fanduel',
  'fliff', 'hardrockbet', 'prizepicks', 'underdog', 'williamhill_us',
];

interface Prop {
  player: string;
  market: string;
  line: number;
  side: string;
  bookmaker: string;
  odds: number;
}

const selectStyle: React.CSSProperties = {
  padding: '8px 12px',
  border: `1px solid ${theme.border}`,
  borderRadius: 4,
  fontSize: 14,
  minWidth: 160,
  height: 38,
  background: theme.bgCard,
  color: theme.textPrimary,
};

export default function NBAProps() {
  const [players, setPlayers] = useState<string[]>([]);
  const [playerFilter, setPlayerFilter] = useState('');
  const [marketFilter, setMarketFilter] = useState('');
  const [sideFilter, setSideFilter] = useState('');
  const [bookmakerFilter, setBookmakerFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [props, setProps] = useState<Prop[]>([]);

  useEffect(() => {
    getNBAPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
  }, []);

  const search = async () => {
    setLoading(true);
    setError('');
    setProps([]);
    try {
      const params: Record<string, any> = {};
      if (playerFilter) params.player = playerFilter;
      if (marketFilter) params.market = marketFilter;
      if (sideFilter) params.side = sideFilter;
      if (bookmakerFilter) params.bookmaker = bookmakerFilter;
      const res = await getNBAProps(params);
      setProps(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch props.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 24, overflowY: 'auto', minHeight: 'calc(100vh - 60px)', background: theme.bgPage }}>
      <h2 style={{ marginTop: 0, marginBottom: 24, color: theme.textPrimary }}>NBA Props</h2>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 28 }}>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>Player</label>
          <SearchDropdown
            players={players}
            value={playerFilter}
            onSelect={setPlayerFilter}
            placeholder="Search player..."
            inputStyle={{ minWidth: 200, height: 38, padding: '8px 12px', fontSize: 14 }}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>Market</label>
          <select style={selectStyle} value={marketFilter} onChange={(e) => setMarketFilter(e.target.value)}>
            <option value="">-- All Markets --</option>
            {MARKETS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>Side</label>
          <select style={selectStyle} value={sideFilter} onChange={(e) => setSideFilter(e.target.value)}>
            <option value="">-- Both --</option>
            <option value="over">Over</option>
            <option value="under">Under</option>
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>Sportsbook</label>
          <select style={selectStyle} value={bookmakerFilter} onChange={(e) => setBookmakerFilter(e.target.value)}>
            <option value="">-- All Books --</option>
            {SPORTSBOOKS.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </div>
        <button
          onClick={search}
          disabled={loading}
          style={{
            padding: '9px 24px',
            background: theme.accent,
            color: 'white',
            border: 'none',
            borderRadius: 4,
            fontWeight: 700,
            fontSize: 14,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.6 : 1,
            height: 38,
          }}
        >
          Search
        </button>
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
          {error}
        </div>
      )}
      {!loading && props.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                <th style={{ padding: '10px 14px', textAlign: 'left' }}>Player</th>
                <th style={{ padding: '10px 14px', textAlign: 'left' }}>Market</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>Line</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>Side</th>
                <th style={{ padding: '10px 14px', textAlign: 'left' }}>Sportsbook</th>
                <th style={{ padding: '10px 14px', textAlign: 'center' }}>Odds</th>
              </tr>
            </thead>
            <tbody>
              {props.map((p, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                  <td style={{ padding: '8px 14px', fontWeight: 600, color: theme.textPrimary }}>{p.player}</td>
                  <td style={{ padding: '8px 14px', color: theme.textSecondary }}>{p.market}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{p.line}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'center' }}>
                    <span style={{
                      background: p.side === 'over' ? 'rgba(107,168,240,0.18)' : 'rgba(244,87,63,0.18)',
                      color: p.side === 'over' ? theme.dataBlue : theme.dataRed,
                      padding: '2px 10px',
                      borderRadius: 12,
                      fontWeight: 700,
                      fontSize: 12,
                      textTransform: 'uppercase',
                    }}>
                      {p.side}
                    </span>
                  </td>
                  <td style={{ padding: '8px 14px', color: theme.textPrimary }}>{p.bookmaker}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'center', fontWeight: 700, color: theme.textPrimary }}>
                    {p.odds > 0 ? `+${p.odds}` : p.odds}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 10, fontSize: 13, color: theme.textSecondary }}>{props.length} result{props.length !== 1 ? 's' : ''}</div>
        </div>
      )}
      {!loading && !error && props.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          Use the filters above and click "Search" to find props.
        </div>
      )}
    </div>
  );
}
