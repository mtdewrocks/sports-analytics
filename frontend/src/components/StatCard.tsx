import React from 'react';
import { theme } from '../theme';

export interface StatCardProps {
  /** Left side of the headline row -- the row's identity. */
  title: React.ReactNode;
  /** Small muted text beside the title (team, position, date). */
  titleAside?: React.ReactNode;
  /** The one number the row exists for, shown large on the right. */
  value?: React.ReactNode;
  valueColor?: string;
  /** Small label under the value (e.g. "ERA"), for when the number needs naming. */
  valueLabel?: React.ReactNode;
  /** 1-based position, rendered as a monospace marker before the title. Only
   *  pass this when the list is genuinely ranked -- it's information, not decoration. */
  rank?: number;
  /** Secondary stats. Rendered as one dot-separated line per array. */
  meta?: React.ReactNode[];
  metaSecondary?: React.ReactNode[];
  /** Small muted line at the bottom (the stat's own name, a caveat). */
  footer?: React.ReactNode;
  footerColor?: string;
  /** Anything extra below the meta lines -- a bar, a pill strip, a mini table. */
  children?: React.ReactNode;
  onClick?: () => void;
  style?: React.CSSProperties;
}

function joinDots(parts: React.ReactNode[]): React.ReactNode[] {
  return parts.filter((p) => p !== null && p !== undefined && p !== false).flatMap((p, i) => (
    i === 0 ? [<span key={i}>{p}</span>] : [<span key={`d${i}`}> · </span>, <span key={i}>{p}</span>]
  ));
}

/**
 * The generalised form of GameCard: the shape every table row on this site
 * collapses to on a phone. Identity on the left, the number you came for large
 * on the right, everything secondary as a dot-separated meta line underneath.
 *
 * Keeping one component for this matters more than it looks -- eleven pages
 * converted independently is eleven slightly different cards, and the
 * difference is visible the moment you navigate between two of them.
 */
export default function StatCard({
  title, titleAside, value, valueColor, valueLabel, rank, meta, metaSecondary,
  footer, footerColor, children, onClick, style,
}: StatCardProps) {
  const interactive = !!onClick;

  return (
    <div
      onClick={onClick}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={interactive ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick!(); } } : undefined}
      style={{
        background: theme.bgCard, borderRadius: 8, padding: '12px 14px', marginBottom: 8,
        cursor: interactive ? 'pointer' : undefined, ...style,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <div style={{ fontSize: 13, color: theme.textPrimary, minWidth: 0 }}>
          {rank != null && (
            <span style={{
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              fontSize: 11, color: theme.textMuted, marginRight: 6,
            }}>
              {String(rank).padStart(2, '0')}
            </span>
          )}
          {title}
          {titleAside && <span style={{ color: theme.textMuted, fontSize: 11, marginLeft: 6 }}>{titleAside}</span>}
        </div>
        {value != null && (
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div style={{
              fontSize: 20, fontWeight: 700, lineHeight: 1.1,
              fontVariantNumeric: 'tabular-nums',
              color: valueColor ?? theme.textPrimary,
            }}>
              {value}
            </div>
            {valueLabel && (
              <div style={{ fontSize: 10, color: theme.textMuted, marginTop: 1 }}>{valueLabel}</div>
            )}
          </div>
        )}
      </div>

      {meta && meta.length > 0 && (
        <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 5 }}>{joinDots(meta)}</div>
      )}
      {metaSecondary && metaSecondary.length > 0 && (
        <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 2 }}>{joinDots(metaSecondary)}</div>
      )}

      {children}

      {footer && (
        <div style={{ fontSize: 11, color: footerColor ?? theme.textMuted, marginTop: 4 }}>{footer}</div>
      )}
    </div>
  );
}
