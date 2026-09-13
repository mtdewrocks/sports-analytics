import type { CSSProperties } from 'react';

/**
 * Style for the first cell of each row inside a ScrollTable, so the row's
 * identity stays on screen while the numbers scroll under it.
 *
 * `background` has to be opaque or the scrolling cells show through -- it takes
 * whichever surface the row is painted on, since the zebra striping alternates.
 *
 * Kept out of ScrollTable.tsx so that file exports only its component, which is
 * what lets fast refresh work on it.
 */
export function stickyColStyle(background: string, extra?: CSSProperties): CSSProperties {
  return {
    position: 'sticky',
    left: 0,
    zIndex: 1,
    background,
    ...extra,
  };
}
