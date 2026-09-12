import { useState, useEffect } from 'react';

const MOBILE_BREAKPOINT = 768;

/**
 * True when the browser viewport is narrower than the mobile breakpoint.
 * Purely a live viewport-width check (via matchMedia), not device
 * detection -- a desktop browser window resized narrow gets the same
 * mobile layout as an actual phone, and updates live if the window is
 * resized while the page is open.
 */
export default function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`).matches
  );

  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  return isMobile;
}
