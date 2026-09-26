import { theme } from '../theme';

/**
 * Today's lineup vs the team's usual lineup against the same pitcher hand
 * (backend/app/data/mlb_lineups.py). Shared by the Alt-Line pitcher cards and
 * the Pitcher Daily Report. Numbers are from the pitcher's point of view: a
 * lower wOBA, higher K% or lower BB% than usual helps him.
 */

export interface VsUsual {
  hand: 'L' | 'R' | null;
  basis: 'vs_hand' | 'overall' | null;
  games: number;
  today: { woba: number; k: number; bb: number };
  usual: { woba: number; k: number; bb: number };
  diff: { woba: number; k: number; bb: number };
  missing: { player: string; woba: number }[];
  replacements: string[];
  notable: boolean;
  big: boolean;
}

const w = (v: number) => v.toFixed(3).replace(/^0/, '').replace(/^-0/, '-');
const pts = (d: number) => `${d > 0 ? '+' : ''}${Math.round(d * 1000)}`;
const pp = (d: number) => `${d > 0 ? '+' : ''}${d.toFixed(1)}`;

/** Green when the change helps the pitcher, red when it hurts, grey when small. */
function tone(d: number, goodIfNegative: boolean, threshold: number): string {
  if (Math.abs(d) < threshold) return theme.textSecondary;
  return (d < 0) === goodIfNegative ? theme.accent : theme.dataRed;
}

export default function LineupVsUsual({ v, compact = false }: { v: VsUsual; compact?: boolean }) {
  const side = v.hand ? `vs ${v.hand}HP` : '';
  const label = v.diff.woba <= -0.015 ? 'Weaker than their usual lineup'
    : v.diff.woba >= 0.015 ? 'Stronger than their usual lineup' : 'Close to their usual lineup';
  const big = v.big || Math.abs(v.diff.k) >= 2 || Math.abs(v.diff.bb) >= 2;
  return (
    <div style={{
      marginTop: compact ? 4 : 6, fontSize: 12, lineHeight: 1.55, color: theme.textSecondary,
      fontVariantNumeric: 'tabular-nums',
    }}>
      <div>
        <strong style={{ color: big ? theme.textPrimary : theme.textSecondary }}>{label}</strong>
        {side && ` ${side}`}
        {v.basis === 'overall' && <span style={{ color: theme.textMuted }}> (overall regulars; few games vs this hand)</span>}
      </div>
      <div>
        wOBA {w(v.today.woba)} vs {w(v.usual.woba)}{' '}
        <strong style={{ color: tone(v.diff.woba, true, 0.015) }}>({pts(v.diff.woba)})</strong>
        {' · '}K {v.today.k.toFixed(1)}% vs {v.usual.k.toFixed(1)}%{' '}
        <strong style={{ color: tone(v.diff.k, false, 2) }}>({pp(v.diff.k)})</strong>
        {' · '}BB {v.today.bb.toFixed(1)}% vs {v.usual.bb.toFixed(1)}%{' '}
        <strong style={{ color: tone(v.diff.bb, true, 2) }}>({pp(v.diff.bb)})</strong>
      </div>
      {v.missing.length > 0 && (
        <div>
          Missing regulars:{' '}
          {v.missing.map((m, i) => (
            <span key={m.player}>{i > 0 && ', '}<span style={{ color: theme.textPrimary }}>{m.player}</span> ({w(m.woba)})</span>
          ))}
          {!compact && v.replacements.length > 0 && <> · In: {v.replacements.join(', ')}</>}
        </div>
      )}
    </div>
  );
}
