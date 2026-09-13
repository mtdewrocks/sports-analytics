import type { CSSProperties } from 'react';
import useIsMobile from '../hooks/useIsMobile';
import { theme } from '../theme';

/** Shared field styles, so the pages with a filter sidebar stop each keeping
 *  their own near-identical copy of these two objects. */
export const fieldLabelStyle: CSSProperties = {
  display: 'block',
  marginBottom: 4,
  fontWeight: 600,
  fontSize: 13,
  color: theme.textPrimary,
};

export const fieldStyle: CSSProperties = {
  width: '100%',
  padding: 8,
  marginBottom: 16,
  minHeight: 38,
  border: `1px solid ${theme.border}`,
  background: theme.bgPage,
  color: theme.textPrimary,
  borderRadius: 4,
  boxSizing: 'border-box',
};

/**
 * The container style a FilterPanel expects to sit in: a row on desktop, a
 * column on mobile, with the page's own height rules flipped to match.
 */
export function usePanelLayout(): CSSProperties {
  const isMobile = useIsMobile();
  return {
    display: 'flex',
    flexDirection: isMobile ? 'column' : 'row',
    height: isMobile ? 'auto' : 'calc(100vh - 60px)',
    minHeight: isMobile ? 'calc(100vh - 60px)' : undefined,
  };
}
