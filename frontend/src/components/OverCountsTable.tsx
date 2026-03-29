interface OverCount { over: number; total: number; pct: number; }
interface OverCountsTableProps {
  over_counts: { last5: OverCount; last10: OverCount; season: OverCount };
  threshold: number;
  stat: string;
}

function formatPct(pct: number): string {
  // Backend returns 0-1 decimal. Guard against already-percentage values.
  const display = pct > 1 ? Math.round(pct) : Math.round(pct * 100);
  return `${display}%`;
}

function pctColor(pct: number): string {
  const val = pct > 1 ? pct / 100 : pct;
  return val >= 0.6 ? '#2ecc71' : val >= 0.4 ? '#f39c12' : '#e74c3c';
}

export default function OverCountsTable({ over_counts, threshold, stat }: OverCountsTableProps) {
  const periods = [
    { label: 'Last 5', data: over_counts.last5 },
    { label: 'Last 10', data: over_counts.last10 },
    { label: 'Season', data: over_counts.season },
  ];

  return (
    <div style={{ marginTop: 20 }}>
      <h4 style={{ marginBottom: 8, color: '#1a1a2e' }}>
        Over {threshold} {stat.toUpperCase()}
      </h4>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ background: '#1a1a2e', color: 'white' }}>
            <th style={{ padding: '8px 12px', textAlign: 'left' }}>Period</th>
            <th style={{ padding: '8px 12px', textAlign: 'center' }}>Over</th>
            <th style={{ padding: '8px 12px', textAlign: 'center' }}>Total</th>
            <th style={{ padding: '8px 12px', textAlign: 'center' }}>Hit %</th>
          </tr>
        </thead>
        <tbody>
          {periods.map(({ label, data }) => (
            <tr key={label} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ padding: '8px 12px', color: '#555' }}>{label}</td>
              <td style={{ padding: '8px 12px', textAlign: 'center' }}>{data.over}</td>
              <td style={{ padding: '8px 12px', textAlign: 'center' }}>{data.total}</td>
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
