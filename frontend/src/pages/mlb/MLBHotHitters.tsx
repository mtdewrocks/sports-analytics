import React, { useState, useEffect } from 'react';
import { getMLBHotHitters } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';

interface SortConfig {
  key: string;
  direction: 'asc' | 'desc';
}

export default function MLBHotHitters() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [hitters, setHitters] = useState<Record<string, any>[]>([]);
  const [sortConfig, setSortConfig] = useState<SortConfig | null>(null);

  useEffect(() => {
    getMLBHotHitters()
      .then((res) => setHitters(res.data))
      .catch(() => setError('Failed to load hot hitters.'))
      .finally(() => setLoading(false));
  }, []);

  const columns = hitters.length > 0 ? Object.keys(hitters[0]) : [];

  const handleSort = (key: string) => {
    setSortConfig((prev) => {
      if (prev?.key === key) {
        return { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
      }
      return { key, direction: 'asc' };
    });
  };

  const sortedHitters = React.useMemo(() => {
    if (!sortConfig) return hitters;
    return [...hitters].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;
      const aNum = parseFloat(aVal);
      const bNum = parseFloat(bVal);
      if (!isNaN(aNum) && !isNaN(bNum)) {
        return sortConfig.direction === 'asc' ? aNum - bNum : bNum - aNum;
      }
      const aStr = String(aVal).toLowerCase();
      const bStr = String(bVal).toLowerCase();
      if (aStr < bStr) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aStr > bStr) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [hitters, sortConfig]);

  return (
    <div style={{ padding: 24, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 24, color: '#1a1a2e' }}>Today's Hot Hitters</h2>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b' }}>
          {error}
        </div>
      )}
      {!loading && !error && sortedHitters.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#1a1a2e', color: 'white' }}>
                {columns.map((col) => (
                  <th
                    key={col}
                    onClick={() => handleSort(col)}
                    style={{
                      padding: '10px 14px',
                      textAlign: 'left',
                      whiteSpace: 'nowrap',
                      cursor: 'pointer',
                      userSelect: 'none',
                    }}
                  >
                    {col}
                    {sortConfig?.key === col && (
                      <span style={{ marginLeft: 6, fontSize: 10 }}>
                        {sortConfig.direction === 'asc' ? '▲' : '▼'}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedHitters.map((row, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #eee', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                  {columns.map((col) => (
                    <td key={col} style={{ padding: '8px 14px', whiteSpace: 'nowrap' }}>
                      {String(row[col] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 10, fontSize: 13, color: '#999' }}>{sortedHitters.length} player{sortedHitters.length !== 1 ? 's' : ''}</div>
        </div>
      )}
      {!loading && !error && sortedHitters.length === 0 && (
        <div style={{ color: '#999', textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          No hot hitters data available today.
        </div>
      )}
    </div>
  );
}
