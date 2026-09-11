import { theme } from '../theme';

interface WinLossSummary { games: number; avg: number | null; hit: number; total: number; pct: number; }
interface WinLossBreakdownTableProps {
  breakdown: { W: WinLossSummary; L: WinLossSummary };
  threshold: number;
  stat: string;
}

function formatPct(pct: number): string {
  const display = pct > 1 ? Math.round(pct) : Math.round(pct * 100);
  return `${display}%`;
}

function pctColor(pct: number): string {
  const val = pct > 1 ? pct / 100 : pct;
  return val >= 0.6 ? theme.dataBlue : val >= 0.4 ? '#9ca3af' : theme.dataRed;
}

export default function WinLossBreakdownTable({ breakdown, threshold, stat }: WinLossBreakdownTableProps) {
  const rows = [
    { label: 'Wins', data: breakdown.W },
    { label: 'Losses', data: breakdown.L },
  ];

  return (
    <div style={{ marginTop: 20 }}>
      <h4 style={{ marginBottom: 8, color: theme.textPrimary }}>
        Wins vs Losses — {stat.toUpperCase()} (Season)
      </h4>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
            <th style={{ padding: '8px 12px', textAlign: 'left' }}>Result</th>
            <th style={{ padding: '8px 12px', textAlign: 'center' }}>Games</th>
            <th style={{ padding: '8px 12px', textAlign: 'center' }}>Avg {stat.toUpperCase()}</th>
            <th style={{ padding: '8px 12px', textAlign: 'center' }}>Hit % (Over {threshold})</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, data }) => (
            <tr key={label} style={{ borderBottom: `1px solid ${theme.border}` }}>
              <td style={{ padding: '8px 12px', color: theme.textSecondary }}>{label}</td>
              <td style={{ padding: '8px 12px', textAlign: 'center', color: theme.textPrimary }}>{data.games}</td>
              <td style={{ padding: '8px 12px', textAlign: 'center', color: theme.textPrimary, fontWeight: 'bold' }}>
                {data.avg ?? '—'}
              </td>
              <td style={{
                padding: '8px 12px', textAlign: 'center',
                fontWeight: 'bold', color: data.games > 0 ? pctColor(data.pct) : theme.textMuted,
              }}>
                {data.games > 0 ? formatPct(data.pct) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
