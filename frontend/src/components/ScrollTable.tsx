import React, { useEffect, useRef, useState } from 'react';
import { theme } from '../theme';

interface ScrollTableProps {
  children: React.ReactNode;
  /** Text for the one-time swipe affordance. Set to null to suppress it. */
  hint?: string | null;
  style?: React.CSSProperties;
}

/**
 * Horizontal-scroll container for the three genuinely matrix-shaped tables in
 * the app -- the Props book grid, MLB Matchup's opposing-hitter grid, and the
 * bullpen day calendar. Those lose their meaning as stacked cards, because the
 * point of them is scanning DOWN a column, so instead of converting them we
 * make the sideways scroll discoverable: a fade at the right edge and a hint
 * line that disappears once the user has actually scrolled.
 *
 * Pair with `stickyColStyle` below on the first cell of every row so the row's
 * identity stays on screen while the numbers scroll under it.
 */
export default function ScrollTable({ children, hint = 'swipe for more →', style }: ScrollTableProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [overflowing, setOverflowing] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const measure = () => setOverflowing(el.scrollWidth > el.clientWidth + 4);
    measure();

    const ro = new ResizeObserver(measure);
    ro.observe(el);
    // Content can arrive after the first measure (async fetch), so watch the
    // row count too rather than only the container box.
    const mo = new MutationObserver(measure);
    mo.observe(el, { childList: true, subtree: true });

    return () => { ro.disconnect(); mo.disconnect(); };
  }, [children]);

  const showAffordance = overflowing && !scrolled;

  return (
    <div style={style}>
      <div style={{ position: 'relative' }}>
        <div
          ref={ref}
          onScroll={(e) => { if (e.currentTarget.scrollLeft > 8) setScrolled(true); }}
          style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}
        >
          {children}
        </div>
        {showAffordance && (
          <div
            aria-hidden
            style={{
              position: 'absolute', top: 0, bottom: 0, right: 0, width: 36, pointerEvents: 'none',
              background: `linear-gradient(90deg, rgba(13,17,23,0), ${theme.bgPage})`,
            }}
          />
        )}
      </div>
      {hint && showAffordance && (
        <div style={{ fontSize: 11, color: theme.textMuted, textAlign: 'right', marginTop: 5 }}>
          {hint}
        </div>
      )}
    </div>
  );
}
