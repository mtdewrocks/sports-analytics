import React from 'react';
import { theme } from '../theme';

export interface Chip {
  key: string;
  label: string;
  /** Appended to the label when this chip is active -- used for sort direction. */
  activeSuffix?: string;
}

interface ChipRowProps {
  chips: Chip[];
  value: string;
  onChange: (key: string) => void;
  /** Scroll sideways in one row instead of wrapping to three. */
  scroll?: boolean;
  /** Negative margin to let the row bleed to the screen edges, so the last
   *  chip visibly runs off rather than ending flush and looking complete. */
  bleed?: number;
  style?: React.CSSProperties;
}

/**
 * Category / sort chips. On a phone a wrapping row of eight buttons becomes
 * three rows and eats half the screen before any data; scrolling sideways keeps
 * it one row high no matter how many categories get added later.
 */
export default function ChipRow({ chips, value, onChange, scroll = true, bleed = 0, style }: ChipRowProps) {
  return (
    <div
      style={{
        display: 'flex', gap: 8,
        flexWrap: scroll ? 'nowrap' : 'wrap',
        overflowX: scroll ? 'auto' : undefined,
        scrollbarWidth: 'none',
        marginLeft: -bleed, marginRight: -bleed,
        paddingLeft: bleed, paddingRight: bleed,
        paddingBottom: 2,
        ...style,
      }}
    >
      {chips.map((c) => {
        const on = c.key === value;
        return (
          <button
            key={c.key}
            onClick={() => onChange(c.key)}
            aria-pressed={on}
            style={{
              flex: '0 0 auto',
              padding: '8px 14px', borderRadius: 6, fontSize: 13, fontWeight: 600,
              cursor: 'pointer', whiteSpace: 'nowrap', minHeight: 38,
              border: on ? `1px solid ${theme.accent}` : `1px solid ${theme.border}`,
              background: on ? theme.accent : theme.bgCard,
              color: on ? 'white' : theme.textSecondary,
            }}
          >
            {c.label}{on && c.activeSuffix ? ` ${c.activeSuffix}` : ''}
          </button>
        );
      })}
    </div>
  );
}

/** Removable chip, for built-up filters that read as a sentence. */
export function RemovableChip({
  children, onRemove, onClick, accent,
}: { children: React.ReactNode; onRemove?: () => void; onClick?: () => void; accent?: boolean }) {
  return (
    <span
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        background: theme.bgCard,
        border: `1px solid ${accent ? theme.accent : theme.border}`,
        color: accent ? theme.accent : theme.textPrimary,
        borderRadius: 999, padding: '7px 13px', fontSize: 13, minHeight: 36,
        margin: '0 7px 8px 0', cursor: onClick ? 'pointer' : undefined,
      }}
    >
      {children}
      {onRemove && (
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          aria-label="Remove filter"
          style={{
            background: 'none', border: 'none', color: theme.textMuted,
            cursor: 'pointer', padding: '0 0 0 2px', fontSize: 14, lineHeight: 1,
          }}
        >
          ✕
        </button>
      )}
    </span>
  );
}
