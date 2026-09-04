import { useState, useEffect, useMemo } from 'react';
import { getMLBPitcherDailyReport } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import { theme } from '../../theme';

interface PitcherRow {
  player: string;
  team: string;
  opposing_team: string;
  games: number;
  avg_outs: number | null;
  avg_hits: number | null;
  avg_er: number | null;
  avg_so: number | null;
  avg_bb: number | null;
  opp_avg: number | null;
  opp_k_pct: number | null;
  opp_bb_pct: number | null;
  high_k_hitter: number;
  high_bb_hitter: number;
  high_avg_hitter: number;
  low_avg_hitter: number;
  high_iso_hitter: number;
  high_woba_hitter: number;
}

type SortKey = keyof PitcherRow;

const columns: { key: SortKey; label: string; align?: 'left' | 'right' }[] = [
  { key: 'player', label: 'Pitcher', align: 'left' },
  { key: 'team', label: 'Team', align: 'left' },
  { key: 'opposing_team', label: 'Opponent', align: 'left' },
  { key: 'games', label: 'GP' },
  { key: 'avg_outs', label: 'Outs' },
  { key: 'avg_hits', label: 'H' },
  { key: 'avg_er', label: 'ER' },
  { key: 'avg_so', label: 'SO' },
  { key: 'avg_bb', label: 'BB' },
  { key: 'opp_avg', label: 'Opp AVG' },
  { key: 'opp_k_pct', label: 'Opp K%' },
  { key: 'opp_bb_pct', label: 'Opp BB%' },
  { key: 'high_k_hitter', label: 'Hi K' },
  { key: 'high_bb_hitter', label: 'Hi BB' },
  { key: 'high_avg_hitter', label: 'Hi Avg' },
  { key: 'low_avg_hitter', label: 'Lo Avg' },
  { key: 'high_iso_hitter', label: 'Hi ISO' },
  { key: 'high_woba_hitter', label: 'Hi wOBA' },
];

export default function MLBPitcherDailyReport() {
  const [rows, setRows] = useState<PitcherRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('player');
  const [sortDesc, setSortDesc] = useState(false);

  useEffect(() => {
    getMLBPitcherDailyReport()
      .then((res) => setRows(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to fetch pitcher report.'))
      .finally(() => setLoading(false));
  }, []);

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'string') return sortDesc ? String(bv).localeCompare(av) : av.localeCompare(String(bv));
      return sortDesc ? (bv as number) - (av as number) : (av as number) - (bv as number);
    });
    return copy;
  }, [rows, sortKey, sortDesc]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      setSortDesc(false);
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 1300, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>MLB Pitcher Daily Report</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 20 }}>
        Every starting pitcher on today's slate -- recent-form averages (last up to 10 starts) alongside
        today's opposing lineup's toughness. Click a column to sort.
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {!loading && !error && rows.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40 }}>
          No starting pitchers found for today's slate.
        </div>
      )}

      {!loading && !error && rows.length > 0 && (
        <div style={{ background: theme.bgCard, borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.4)', overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', fontSize: 13, minWidth: 1200 }}>
            <thead>
              <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                {columns.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    style={{
                      padding: '9px 10px', textAlign: col.align ?? 'right', cursor: 'pointer',
                      whiteSpace: 'nowrap', userSelect: 'none',
                    }}
                  >
                    {col.label}{sortKey === col.key ? (sortDesc ? ' ▼' : ' ▲') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr key={r.player} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage, color: theme.textPrimary }}>
                  <td style={{ padding: '7px 10px', fontWeight: 600 }}>{r.player}</td>
                  <td style={{ padding: '7px 10px', color: theme.textSecondary }}>{r.team}</td>
                  <td style={{ padding: '7px 10px', color: theme.textSecondary }}>{r.opposing_team}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.games}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.avg_outs ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.avg_hits ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.avg_er ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.avg_so ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.avg_bb ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.opp_avg ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.opp_k_pct ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.opp_bb_pct ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.high_k_hitter}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.high_bb_hitter}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.high_avg_hitter}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.low_avg_hitter}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.high_iso_hitter}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.high_woba_hitter}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 16, textAlign: 'center' }}>
        "Hi/Lo X" columns count how many opposing batters clear a fixed threshold (e.g. K% ≥ 20, AVG ≥ .270)
        against this pitcher's specific throwing hand -- not a ranking relative to today's other games.
      </div>
    </div>
  );
}
