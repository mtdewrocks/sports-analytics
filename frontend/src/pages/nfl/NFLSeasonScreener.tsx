import { useState } from 'react';
import { getNFLSeasonScreener } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import { theme } from '../../theme';

const SEASONS = [2026, 2025];
const POSITIONS = ['', 'QB', 'RB', 'WR', 'TE', 'DL', 'LB', 'DB'];
const STAT_OPTIONS = [
  { value: 'carries', label: 'Carries' },
  { value: 'rushing_yards', label: 'Rushing Yards' },
  { value: 'rushing_tds', label: 'Rushing TDs' },
  { value: 'targets', label: 'Targets' },
  { value: 'receptions', label: 'Receptions' },
  { value: 'receiving_yards', label: 'Receiving Yards' },
  { value: 'receiving_tds', label: 'Receiving TDs' },
  { value: 'attempts', label: 'Pass Attempts' },
  { value: 'completions', label: 'Completions' },
  { value: 'passing_yards', label: 'Passing Yards' },
  { value: 'passing_tds', label: 'Passing TDs' },
  { value: 'passing_interceptions', label: 'Interceptions (Thrown)' },
  { value: 'def_sacks', label: 'Sacks' },
  { value: 'def_interceptions', label: 'Interceptions (Defense)' },
];

function statLabel(value: string): string {
  return STAT_OPTIONS.find((s) => s.value === value)?.label ?? value;
}

interface FilterRow {
  id: number;
  stat: string;
  operator: '>=' | '<=';
  value: string;
}

type ResultRow = Record<string, string | number | null>;

export default function NFLSeasonScreener() {
  const [season, setSeason] = useState(SEASONS[0]);
  const [position, setPosition] = useState('RB');
  const [filters, setFilters] = useState<FilterRow[]>([
    { id: 1, stat: 'rushing_yards', operator: '>=', value: '1000' },
  ]);
  const [nextId, setNextId] = useState(2);
  const [results, setResults] = useState<ResultRow[] | null>(null);
  const [activeStats, setActiveStats] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const addFilter = () => {
    setFilters([...filters, { id: nextId, stat: 'carries', operator: '>=', value: '' }]);
    setNextId(nextId + 1);
  };
  const removeFilter = (id: number) => setFilters(filters.filter((f) => f.id !== id));
  const updateFilter = (id: number, patch: Partial<FilterRow>) =>
    setFilters(filters.map((f) => (f.id === id ? { ...f, ...patch } : f)));

  const search = async () => {
    const validFilters = filters.filter((f) => f.value.trim() !== '' && !isNaN(parseFloat(f.value)));
    if (validFilters.length === 0) return;
    setLoading(true);
    setError('');
    setResults(null);
    try {
      const filterStrings = validFilters.map((f) => `${f.stat}${f.operator}${f.value}`);
      const res = await getNFLSeasonScreener(season, position, filterStrings);
      setResults(res.data);
      setActiveStats(validFilters.map((f) => f.stat));
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to run screener.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 1000, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NFL Season Stat Screener</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 20 }}>
        Find every player who meets a set of season-long stat thresholds -- e.g. 1000+ rushing yards, or 250+ carries AND 100+ targets.
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <div>
          <label style={{ display: 'block', fontSize: 12, color: theme.textSecondary, marginBottom: 4 }}>Season</label>
          <select
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
            style={{ padding: '8px 12px', fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgCard, color: theme.textPrimary }}
          >
            {SEASONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, color: theme.textSecondary, marginBottom: 4 }}>Position</label>
          <select
            value={position}
            onChange={(e) => setPosition(e.target.value)}
            style={{ padding: '8px 12px', fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgCard, color: theme.textPrimary }}
          >
            <option value="">All Positions</option>
            {POSITIONS.filter((p) => p).map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>

      <div style={{ background: theme.bgCard, borderRadius: 8, padding: 16, marginBottom: 20 }}>
        <div style={{ color: theme.textSecondary, fontSize: 11, textTransform: 'uppercase', marginBottom: 10 }}>Filters (all must be true)</div>
        {filters.map((f) => (
          <div key={f.id} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <select
              value={f.stat}
              onChange={(e) => updateFilter(f.id, { stat: e.target.value })}
              style={{ flex: 2, padding: '7px 10px', fontSize: 13, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgPage, color: theme.textPrimary }}
            >
              {STAT_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
            <select
              value={f.operator}
              onChange={(e) => updateFilter(f.id, { operator: e.target.value as '>=' | '<=' })}
              style={{ width: 70, padding: '7px 10px', fontSize: 13, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgPage, color: theme.textPrimary }}
            >
              <option value=">=">&ge;</option>
              <option value="<=">&le;</option>
            </select>
            <input
              type="number"
              value={f.value}
              onChange={(e) => updateFilter(f.id, { value: e.target.value })}
              placeholder="value"
              style={{ flex: 1, padding: '7px 10px', fontSize: 13, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgPage, color: theme.textPrimary }}
            />
            <button
              onClick={() => removeFilter(f.id)}
              disabled={filters.length === 1}
              style={{
                padding: '7px 10px', fontSize: 13, borderRadius: 4, border: `1px solid ${theme.border}`,
                background: theme.bgPage, color: theme.textSecondary, cursor: filters.length === 1 ? 'not-allowed' : 'pointer',
                opacity: filters.length === 1 ? 0.4 : 1,
              }}
            >
              &times;
            </button>
          </div>
        ))}
        <button
          onClick={addFilter}
          style={{
            marginTop: 4, padding: '6px 14px', fontSize: 12, fontWeight: 700, borderRadius: 4,
            border: `1px solid ${theme.border}`, background: 'transparent', color: theme.textSecondary, cursor: 'pointer',
          }}
        >
          + Add Filter
        </button>
      </div>

      <button
        onClick={search}
        disabled={loading}
        style={{
          padding: '10px 28px', background: theme.accent, color: 'white', border: 'none', borderRadius: 4,
          fontWeight: 700, fontSize: 14, cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.6 : 1, marginBottom: 24,
        }}
      >
        Search
      </button>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!loading && !error && results && (
        results.length === 0 ? (
          <div style={{ color: theme.textSecondary, fontSize: 14 }}>No players matched every filter for {season}.</div>
        ) : (
          <>
            <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 10 }}>{results.length} player{results.length === 1 ? '' : 's'} matched</div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Player</th>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Team</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>Games</th>
                  {activeStats.map((s) => (
                    <th key={s} style={{ padding: '10px 14px', textAlign: 'center' }}>{statLabel(s)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                    <td style={{ padding: '8px 14px', color: theme.textPrimary, fontWeight: 600 }}>{r.player}</td>
                    <td style={{ padding: '8px 14px', color: theme.textPrimary }}>{r.team}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.games_played}</td>
                    {activeStats.map((s) => (
                      <td key={s} style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary, fontWeight: 600 }}>{r[s] ?? '—'}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )
      )}

      {!loading && !error && !results && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 40 }}>
          Set your filters above, then click Search.
        </div>
      )}
    </div>
  );
}
