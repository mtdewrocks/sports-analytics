import React, { useEffect } from 'react';
import { theme } from '../theme';

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  /** Pinned to the bottom of the sheet, below the scrolling content. */
  footer?: React.ReactNode;
}

/**
 * Full-width sheet for the pickers that were previously scrolling boxes inside
 * a scrolling page -- the In/Out teammate list, the Props book filter, the
 * Screener's filter editor.
 *
 * A nested scroll region is the worst interaction on a touch device: a flick
 * either moves the wrong thing or nothing at all. Giving the picker the whole
 * screen removes the nesting entirely, and the wide controls that don't fit on
 * a narrow page fit fine in here.
 */
export default function BottomSheet({ open, onClose, title, children, footer }: BottomSheetProps) {
  // Lock the page behind the sheet, which is what actually prevents the
  // scroll-chaining that made the inline picker unusable.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 3000,
        background: 'rgba(0,0,0,0.55)',
        display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 640,
          background: theme.bgCard,
          borderRadius: '14px 14px 0 0',
          borderTop: `1px solid ${theme.borderStrong}`,
          maxHeight: '85vh',
          display: 'flex', flexDirection: 'column',
          boxShadow: '0 -8px 32px rgba(0,0,0,0.5)',
        }}
      >
        <div style={{ padding: '10px 16px 6px', flexShrink: 0 }}>
          <div aria-hidden style={{
            width: 34, height: 3, borderRadius: 2, background: theme.borderStrong, margin: '0 auto 10px',
          }} />
          {title && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: theme.textPrimary }}>{title}</div>
              <button
                onClick={onClose}
                aria-label="Close"
                style={{
                  background: 'none', border: 'none', color: theme.textSecondary,
                  fontSize: 18, cursor: 'pointer', padding: '4px 8px', minHeight: 34,
                }}
              >
                ✕
              </button>
            </div>
          )}
        </div>

        <div style={{ overflowY: 'auto', padding: '4px 16px 16px', flex: 1 }}>
          {children}
        </div>

        {footer && (
          <div style={{ padding: '12px 16px 18px', borderTop: `1px solid ${theme.border}`, flexShrink: 0 }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

/** A 44px tap row for use inside a sheet. */
export function SheetRow({
  checked, onToggle, children,
}: { checked?: boolean; onToggle?: () => void; children: React.ReactNode }) {
  return (
    <label
      onClick={onToggle}
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '11px 2px', minHeight: 44, cursor: 'pointer', fontSize: 14,
        borderBottom: `1px solid ${theme.border}`, color: theme.textPrimary,
      }}
    >
      {checked !== undefined && (
        <input
          type="checkbox"
          checked={checked}
          onChange={() => { /* handled by the row's onClick */ }}
          style={{ width: 18, height: 18, flexShrink: 0, cursor: 'pointer', accentColor: theme.accent }}
        />
      )}
      {children}
    </label>
  );
}
