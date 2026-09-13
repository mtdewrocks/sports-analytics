import React from 'react';
import { theme } from '../theme';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

interface SegmentedToggleProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Stretch each segment to fill the container. Used on mobile, where the
   *  toggle is a primary control rather than something tucked beside a heading. */
  fullWidth?: boolean;
  size?: 'sm' | 'md';
  style?: React.CSSProperties;
}

/**
 * The Season / Last 4 Games pill pair from the NFL Game Log, extracted so the
 * other pages that had hand-rolled their own copy (Fantasy Matchup's mode
 * switch, MLB Matchup, Props) all share one appearance and one tap target size.
 */
export default function SegmentedToggle<T extends string>({
  options, value, onChange, fullWidth = false, size = 'md', style,
}: SegmentedToggleProps<T>) {
  const pad = size === 'sm' ? '4px 10px' : '6px 14px';
  const font = size === 'sm' ? 12 : 13;

  return (
    <div
      role="tablist"
      style={{
        display: 'flex', gap: 4, background: theme.bgCard, borderRadius: 4, padding: 3,
        width: fullWidth ? '100%' : undefined, boxSizing: 'border-box', ...style,
      }}
    >
      {options.map((opt) => {
        const on = opt.value === value;
        return (
          <button
            key={opt.value}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(opt.value)}
            style={{
              border: 'none', padding: pad, fontSize: font, borderRadius: 4, cursor: 'pointer',
              flex: fullWidth ? 1 : undefined,
              minHeight: 36,
              background: on ? theme.bgCardHover : 'transparent',
              fontWeight: on ? 700 : 400,
              color: on ? theme.textPrimary : theme.textSecondary,
              whiteSpace: 'nowrap',
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
