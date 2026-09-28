import { useEffect, useState } from 'react';
import { getReportCard } from '../api/betting';
import { theme } from '../theme';

/**
 * The EV Finder's track record: every play it flags is logged at the price
 * it first showed and graded against the closing line, whether or not anyone
 * bet it (backend/app/data/report_card.py, from build_flagged_plays.py).
 * Shown at the bottom of the EV Finder page.
 */

interface CardRow { label: string; graded: number; avg_clv_pct: number | null; beat_close_pct: number | null }
interface Card { overall: CardRow; flagged: number; by: CardRow[] }

function pct(v: number | null, signed = false): string {
  if (v === null || v === undefined) return '—';
  return `${signed && v > 0 ? '+' : ''}${v.toFixed(1)}%`;
}

export default function ReportCard() {
  const [card, setCard] = useState<Card | null>(null);
  useEffect(() => {
    getReportCard().then((r) => setCard(r.data)).catch(() => setCard(null));
  }, []);
  if (!card) return null;
  return (
    <div style={{
      background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 10,
      padding: '14px 16px', marginTop: 24,
    }}>
      <h3 style={{ color: theme.textPrimary, fontSize: 16, margin: '0 0 4px' }}>Track record</h3>
      <div style={{ fontSize: 12.5, color: theme.textSecondary, marginBottom: 10, lineHeight: 1.5 }}>
        How this page's own picks have done: every play it flags is recorded at the price it first showed
        and graded against the closing line, whether or not anyone bet it. Beating the close is the
        earliest sign an edge is real. {card.flagged} plays logged so far.
      </div>
      {card.overall.graded === 0 ? (
        <div style={{ fontSize: 13, color: theme.textMuted }}>
          No plays graded yet; they're graded once their games start.
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ color: theme.textMuted, fontSize: 11, textTransform: 'uppercase' }}>
              <th style={{ textAlign: 'left', padding: 6 }}>Group</th>
              <th style={{ textAlign: 'right', padding: 6 }}>Graded</th>
              <th style={{ textAlign: 'right', padding: 6 }}>Avg CLV</th>
              <th style={{ textAlign: 'right', padding: 6 }}>Beat close</th>
            </tr>
          </thead>
          <tbody>
            {[{ ...card.overall, label: 'All plays' }, ...card.by].map((r) => (
              <tr key={r.label} style={{ borderTop: `1px solid ${theme.border}`, color: theme.textPrimary }}>
                <td style={{ padding: 6 }}>{r.label}</td>
                <td style={{ padding: 6, textAlign: 'right' }}>{r.graded}</td>
                <td style={{ padding: 6, textAlign: 'right', color: (r.avg_clv_pct ?? 0) >= 0 ? theme.dataBlue : theme.dataRed }}>
                  {pct(r.avg_clv_pct, true)}
                </td>
                <td style={{ padding: 6, textAlign: 'right' }}>{pct(r.beat_close_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
