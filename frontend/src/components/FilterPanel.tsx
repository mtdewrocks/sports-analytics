import React, { useState } from 'react';
import useIsMobile from '../hooks/useIsMobile';
import { theme } from '../theme';

interface FilterPanelProps {
  title?: string;
  /** Fields that stay visible at every width. Keep this to two or three. */
  children: React.ReactNode;
  /** Fields hidden behind the disclosure on mobile. Always visible on desktop. */
  more?: React.ReactNode;
  /** Names what's behind the disclosure, so nobody has to tap to find out. */
  moreLabel?: string;
  action?: { label: string; onClick: () => void; disabled?: boolean };
  /** Desktop sidebar width. */
  width?: number;
}

/**
 * The Game Log sidebar behaviour, extracted: a fixed-width scrolling column on
 * desktop, a full-width block on top on mobile, with the secondary fields
 * behind a named disclosure so the primary controls and the action button stay
 * on one screen.
 *
 * Render as the first child of a flex container; use `usePanelLayout` for the
 * matching container style.
 */
export default function FilterPanel({
  title, children, more, moreLabel, action, width = 280,
}: FilterPanelProps) {
  const isMobile = useIsMobile();
  const [showMore, setShowMore] = useState(false);

  return (
    <div style={{
      width: isMobile ? '100%' : width,
      background: theme.bgCard,
      padding: isMobile ? 16 : 20,
      height: isMobile ? 'auto' : 'calc(100vh - 60px)',
      overflowY: isMobile ? 'visible' : 'auto',
      flexShrink: 0,
      boxSizing: 'border-box',
    }}>
      {title && (
        <h3 style={{ marginTop: 0, marginBottom: 20, fontSize: 16, fontWeight: 700, color: theme.textPrimary }}>
          {title}
        </h3>
      )}

      {children}

      {more && (!isMobile || showMore) && <>{more}</>}

      {more && isMobile && (
        <button
          onClick={() => setShowMore((v) => !v)}
          aria-expanded={showMore}
          style={{
            width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '10px 0', marginBottom: 16, background: 'none', border: 'none',
            borderTop: `1px solid ${theme.border}`, borderBottom: `1px solid ${theme.border}`,
            color: theme.dataBlue, fontSize: 13, cursor: 'pointer',
          }}
        >
          <span>{showMore ? '− Fewer filters' : `+ More filters${moreLabel ? ` (${moreLabel})` : ''}`}</span>
          <span aria-hidden>{showMore ? '↑' : '↓'}</span>
        </button>
      )}

      {action && (
        <button
          onClick={action.onClick}
          disabled={action.disabled}
          style={{
            width: '100%', padding: '11px 0', background: theme.accent, color: 'white',
            border: 'none', borderRadius: 4, fontWeight: 700, fontSize: 14, minHeight: 42,
            cursor: action.disabled ? 'not-allowed' : 'pointer',
            opacity: action.disabled ? 0.6 : 1,
          }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
