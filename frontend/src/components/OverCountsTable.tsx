interface OverCount { over: number; total: number; pct: number; }
interface OverCountsTableProps {
  over_counts: { last5: OverCount; last10: OverCount; season: OverCount };
  threshold: number;
  stat: string;
}

export default function OverCountsTable({ over_counts, threshold, stat }: OverCountsTableProps) {
  const periods = [
    { label: 'Last 5', data: over_counts.last5 },
    { label: 'Last 10', data: over_counts.last10 },
    { label: 'Season', data: over_counts.season },
  ];
  return (
    <div style={{ marginTop: 20 }}>
      <h4 style={{ marginBottom: 8 }}>Over {threshold} {stat.toUpperCase()}</h4>
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
              <td style={{ padding: '8px 12px' }}>{label}</td>
              <td style={{ padding: '8px 12px', textAlign: 'center' }}>{data.over}</td>
              <td style={{ padding: '8px 12px', textAlign: 'center' }}>{data.total}</td>
              <td style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 'bold', color: data.pct >= 60 ? '#2ecc71' : data.pct >= 40 ? '#f39c12' : '#e74c3c' }}>
                {data.pct}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
