import { theme } from '../theme';

interface OverCount { over: number; total: number; pct: number; }
export interface OverCountsPeriod { key: string; label: string; }
interface OverCountsTableProps {
  over_counts: Record<string, OverCount>;
  threshold: number;
  stat: string;
  /** Which keys to show, in what order, and under what label. Defaults to
   *  the original NBA/NFL Last 5 / Last 10 / Season shape, so those pages
   *  need no changes -- MLB's Game Log passes Last 10 / Last 25 / Season
   *  instead, since a 150+ game season makes "Last 5" too small a window to
   *  be worth a row, and "Last 25" a more useful second lens than it would
   *  be for a 17-game NFL season or an 82-game NBA one. */
  periods?: OverCountsPeriod[];
  /** Period keys to draw with a highlighted background -- e.g. the MLB Game
   *  Log's "vs LHP" row that matches the next opposing starter. */
  highlightKeys?: string[];
}

const DEFAULT_PERIODS: OverCountsPeriod[] = [
  { key: 'last5', label: 'Last 5' },
  { key: 'last10', label: 'Last 10' },
  { key: 'season', label: 'Season' },
];

function formatPct(pct: number): string {
  // Backend returns 0-1 decimal. Guard against already-percentage values.
  const display = pct > 1 ? Math.round(pct) : Math.round(pct * 100);
  return `${display}%`;
}

function pctColor(pct: number): string {
  const val = pct > 1 ? pct / 100 : pct;
  return val >= 0.6 ? theme.dataBlue : val >= 0.4 ? '#9ca3af' : theme.dataRed;
}

const EMPTY_COUNT: OverCount = { over: 0, total: 0, pct: 0 };

export default function OverCountsTable({ over_counts, threshold, stat, periods: periodDefs, highlightKeys }: OverCountsTableProps) {
  const periods = (periodDefs ?? DEFAULT_PERIODS).map((p) => ({
    label: p.label,
    data: over_counts[p.key] ?? EMPTY_COUNT,
    highlight: highlightKeys?.includes(p.key) ?? false,
  }));

  return (
    <div style={{ marginTop: 20 }}>
      <h4 style={{ marginBottom: 8, color: theme.textPrimary }}>
        Over {threshold} {stat.toUpperCase()}
      </h4>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
            <th style={{ padding: '8px 12px', textAlign: 'left' }}>Period</th>
            <th style={{ padding: '8px 12px', textAlign: 'center' }}>Over</th>
            <th style={{ padding: '8px 12px', textAlign: 'center' }}>Total</th>
            <th style={{ padding: '8px 12px', textAlign: 'center' }}>Hit %</th>
          </tr>
        </thead>
        <tbody>
          {periods.map(({ label, data, highlight }) => (
            <tr key={label} style={{ borderBottom: `1px solid ${theme.border}`, background: highlight ? '#13201b' : undefined }}>
              <td style={{ padding: '8px 12px', color: highlight ? '#3fcf9a' : theme.textSecondary, fontWeight: highlight ? 600 : undefined }}>{label}</td>
              <td style={{ padding: '8px 12px', textAlign: 'center', color: theme.textPrimary }}>{data.over}</td>
              <td style={{ padding: '8px 12px', textAlign: 'center', color: theme.textPrimary }}>{data.total}</td>
              <td style={{
                padding: '8px 12px', textAlign: 'center',
                fontWeight: 'bold', color: pctColor(data.pct),
              }}>
                {formatPct(data.pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
