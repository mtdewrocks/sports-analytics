import { useState } from 'react';
import { getNFLSeasonScreener } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import StatCard from '../../components/StatCard';
import BottomSheet from '../../components/BottomSheet';
import SegmentedToggle from '../../components/SegmentedToggle';
import { RemovableChip } from '../../components/ChipRow';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

const SEASONS = [2026, 2025];
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

const selectStyle: React.CSSProperties = {
  padding: '9px 12px', fontSize: 14, borderRadius: 4, minHeight: 40,
  border: `1px solid ${theme.border}`, background: theme.bgCard, color: theme.textPrimary,
};

export default function NFLSeasonScreener() {
  const [season, setSeason] = useState(SEASONS[0]);
  // Starts empty rather than prefilled -- a default threshold reads as a real
  // filter you have to notice and clear. Search stays disabled until a number
  // is entered.
  const [filters, setFilters] = useState<FilterRow[]>([
    { id: 1, stat: 'rushing_yards', operator: '>=', value: '' },
  ]);
  const [nextId, setNextId] = useState(2);
  const [results, setResults] = useState<ResultRow[] | null>(null);
  const [activeStats, setActiveStats] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const isMobile = useIsMobile();
  // On mobile a filter is built in a sheet rather than on the page -- the wide
  // controls that don't fit a 390px row fit fine in there, which is what stops
  // "Interceptions (Thrown)" from being truncated to three words of nothing.
  const [draft, setDraft] = useState<FilterRow | null>(null);
  const [draftIsNew, setDraftIsNew] = useState(false);

  const addFilter = () => {
    setFilters([...filters, { id: nextId, stat: 'carries', operator: '>=', value: '' }]);
    setNextId(nextId + 1);
  };
  const removeFilter = (id: number) => setFilters(filters.filter((f) => f.id !== id));
  const updateFilter = (id: number, patch: Partial<FilterRow>) =>
    setFilters(filters.map((f) => (f.id === id ? { ...f, ...patch } : f)));

  const openNewDraft = () => {
    setDraft({ id: nextId, stat: 'rushing_yards', operator: '>=', value: '' });
    setDraftIsNew(true);
  };
  const openEditDraft = (f: FilterRow) => {
    setDraft({ ...f });
    setDraftIsNew(false);
  };
  const commitDraft = () => {
    if (!draft) return;
    if (draftIsNew) {
      setFilters([...filters, draft]);
      setNextId(nextId + 1);
    } else {
      setFilters(filters.map((f) => (f.id === draft.id ? draft : f)));
    }
    setDraft(null);
  };

  const search = async () => {
    const validFilters = filters.filter((f) => f.value.trim() !== '' && !isNaN(parseFloat(f.value)));
    if (validFilters.length === 0) return;
    setLoading(true);
    setError('');
    setResults(null);
    try {
      const filterStrings = validFilters.map((f) => `${f.stat}${f.operator}${f.value}`);
      const res = await getNFLSeasonScreener(season, filterStrings);
      setResults(res.data);
      setActiveStats(validFilters.map((f) => f.stat));
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to run screener.');
    } finally {
      setLoading(false);
    }
  };

  const canSearch = filters.some((f) => f.value.trim() !== '' && !isNaN(parseFloat(f.value)));

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 1000, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NFL Season Stat Screener</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 20 }}>
        Find every player who meets a set of season-long stat thresholds -- e.g. 1000+ rushing yards, or 250+ carries AND 100+ targets.
      </div>

      <div style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', fontSize: 12, color: theme.textSecondary, marginBottom: 4 }}>Season</label>
        <select
          value={season}
          onChange={(e) => setSeason(Number(e.target.value))}
          style={{ ...selectStyle, width: isMobile ? '100%' : undefined, boxSizing: 'border-box' }}
        >
          {SEASONS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {isMobile ? (
        <>
          <div style={{ fontSize: 11, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
            Filters (all must be true)
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', marginBottom: 10 }}>
            {filters.map((f) => (
              <RemovableChip
                key={f.id}
                onClick={() => openEditDraft(f)}
                onRemove={filters.length === 1 ? undefined : () => removeFilter(f.id)}
              >
                {statLabel(f.stat)} {f.operator === '>=' ? '≥' : '≤'} {f.value || '…'}
              </RemovableChip>
            ))}
            <RemovableChip accent onClick={openNewDraft}>+ Filter</RemovableChip>
          </div>
        </>
      ) : (
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
      )}

      <button
        onClick={search}
        disabled={loading || !canSearch}
        style={{
          padding: isMobile ? '12px 0' : '10px 28px',
          width: isMobile ? '100%' : undefined,
          minHeight: 44,
          background: theme.accent, color: 'white', border: 'none', borderRadius: 4,
          fontWeight: 700, fontSize: 14,
          cursor: loading || !canSearch ? 'not-allowed' : 'pointer',
          opacity: loading || !canSearch ? 0.6 : 1,
          marginBottom: 24,
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
            {isMobile ? (
              /* The first filter's stat is the hero, the rest join the meta
                 line -- which is how a variable number of result columns fits
                 on a phone without a sideways scroll. */
              <div>
                {results.map((r, i) => (
                  <StatCard
                    key={i}
                    title={<span style={{ fontWeight: 700 }}>{r.player}</span>}
                    titleAside={r.team as string}
                    value={activeStats[0] ? (r[activeStats[0]] ?? '—') : undefined}
                    valueLabel={activeStats[0] ? statLabel(activeStats[0]) : undefined}
                    meta={[
                      <>{r.games_played} GP</>,
                      ...activeStats.slice(1).map((s) => <>{r[s] ?? '—'} {statLabel(s)}</>),
                    ]}
                  />
                ))}
              </div>
            ) : (
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
            )}
          </>
        )
      )}

      {!loading && !error && !results && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 40 }}>
          Set your filters above, then tap Search.
        </div>
      )}

      <BottomSheet
        open={draft !== null}
        onClose={() => setDraft(null)}
        title={draftIsNew ? 'Add filter' : 'Edit filter'}
        footer={
          <button
            onClick={commitDraft}
            disabled={!draft || draft.value.trim() === '' || isNaN(parseFloat(draft.value))}
            style={{
              width: '100%', padding: '12px 0', minHeight: 44, borderRadius: 4, border: 'none',
              background: theme.accent, color: 'white', fontSize: 14, fontWeight: 700,
              cursor: !draft || draft.value.trim() === '' ? 'not-allowed' : 'pointer',
              opacity: !draft || draft.value.trim() === '' || isNaN(parseFloat(draft.value)) ? 0.6 : 1,
            }}
          >
            {draftIsNew ? 'Add filter' : 'Save filter'}
          </button>
        }
      >
        {draft && (
          <>
            <label style={{ display: 'block', fontSize: 12, color: theme.textSecondary, marginBottom: 5 }}>Stat</label>
            <select
              value={draft.stat}
              onChange={(e) => setDraft({ ...draft, stat: e.target.value })}
              style={{ ...selectStyle, width: '100%', boxSizing: 'border-box', marginBottom: 16, background: theme.bgPage }}
            >
              {STAT_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>

            <label style={{ display: 'block', fontSize: 12, color: theme.textSecondary, marginBottom: 5 }}>Condition</label>
            <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
              <SegmentedToggle
                value={draft.operator}
                onChange={(op) => setDraft({ ...draft, operator: op })}
                options={[
                  { value: '>=', label: 'At least ≥' },
                  { value: '<=', label: 'At most ≤' },
                ]}
                style={{ flex: 1 }}
                fullWidth
              />
            </div>

            <label style={{ display: 'block', fontSize: 12, color: theme.textSecondary, marginBottom: 5 }}>Value</label>
            <input
              type="number"
              inputMode="numeric"
              autoFocus
              value={draft.value}
              onFocus={(e) => e.target.select()}
              onChange={(e) => setDraft({ ...draft, value: e.target.value })}
              placeholder="e.g. 1000"
              style={{
                width: '100%', boxSizing: 'border-box', padding: '11px 12px', fontSize: 16, minHeight: 44,
                borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgPage, color: theme.textPrimary,
              }}
            />
          </>
        )}
      </BottomSheet>
    </div>
  );
}
