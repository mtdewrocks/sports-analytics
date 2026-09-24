import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import useIsMobile from '../hooks/useIsMobile';
import BottomSheet from './BottomSheet';
import { theme } from '../theme';
import { flatPages, sportsBySeason } from '../siteMap';

/** Height of the fixed mobile tab bar. App.tsx pads the page by this much so
 *  the last card on a page isn't sitting underneath it. */
export const TABBAR_HEIGHT = 58;

/** Heights of the two sticky bars at the top of a league page, so a page can
 *  stick its own header directly beneath them. */
export const NAV_HEIGHT = 56;
export const CHIPBAR_HEIGHT = 54;

interface NavItem { label: string; to: string; }
interface NavSection { label: string; items: NavItem[]; }
interface NavGroup { key: string; label: string; icon: string; sections: NavSection[]; items: NavItem[]; }

// Built from siteMap.ts -- the one list the Dashboard and Landing page also
// read -- with in-season sports first. `items` is the sections flattened in
// order, for the mobile chip bar and the tab bar's landing page.
const GROUPS: NavGroup[] = sportsBySeason().map((s) => ({
  key: s.key,
  label: s.label,
  icon: s.icon,
  sections: s.sections.map((sec) => ({ label: sec.label, items: sec.pages })),
  items: flatPages(s),
}));

const styles: Record<string, React.CSSProperties> = {
  nav: {
    background: theme.bgPage,
    color: 'white',
    padding: '0 16px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 56,
    position: 'sticky',
    top: 0,
    zIndex: 1000,
    boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
  },
  brand: {
    fontSize: 18,
    fontWeight: 700,
    color: theme.accent,
    letterSpacing: 0.5,
    textDecoration: 'none',
  },
  navBtn: {
    background: 'none',
    border: 'none',
    color: theme.textSecondary,
    cursor: 'pointer',
    padding: '8px 14px',
    fontSize: 14,
    fontWeight: 500,
    borderRadius: 4,
  },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    background: theme.bgCard,
    borderRadius: 6,
    minWidth: 180,
    boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
    // NFL runs 11 pages plus section headers -- scroll rather than run off
    // the bottom of a short laptop screen.
    maxHeight: 'calc(100vh - 72px)',
    overflowY: 'auto',
    zIndex: 2000,
  },
  dropdownHeader: {
    padding: '8px 16px 2px',
    color: theme.textSecondary,
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  dropdownLink: {
    display: 'block',
    padding: '10px 16px',
    color: theme.textSecondary,
    fontSize: 14,
    textDecoration: 'none',
  },
  logoutBtn: {
    background: theme.accent,
    border: 'none',
    color: 'white',
    cursor: 'pointer',
    padding: '8px 16px',
    fontSize: 14,
    fontWeight: 600,
    borderRadius: 4,
    marginLeft: 8,
  },
};

/** Desktop dropdown. Opens on click rather than hover, and closes on an
 *  outside click -- the hover version left menus stuck open on any device
 *  without a real pointer. */
function NavDropdown({ label, sections }: { label: string; sections: NavSection[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLLIElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <li ref={ref} style={{ position: 'relative' }}>
      <button style={styles.navBtn} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {label} ▾
      </button>
      {open && (
        <div style={styles.dropdown}>
          {sections.map((section, i) => (
            <div key={section.label} style={i > 0 ? { borderTop: `1px solid ${theme.border}` } : undefined}>
              <div style={styles.dropdownHeader}>{section.label}</div>
              {section.items.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  style={styles.dropdownLink}
                  onClick={() => setOpen(false)}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.background = theme.bgCardHover;
                    (e.currentTarget as HTMLElement).style.color = theme.textPrimary;
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.background = '';
                    (e.currentTarget as HTMLElement).style.color = theme.textSecondary;
                  }}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          ))}
        </div>
      )}
    </li>
  );
}

export default function Navbar() {
  const { logout, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const isMobile = useIsMobile();
  const [moreOpen, setMoreOpen] = useState(false);

  const handleLogout = () => {
    setMoreOpen(false);
    logout();
    navigate('/login');
  };

  const activeGroup = GROUPS.find((g) => location.pathname.startsWith(`/${g.key}/`)) ?? null;

  // Bring the current page's chip into view. Without this the row always
  // starts at the far left, so on any page past the second one you can't see
  // which one you're on -- and the longer the labels, the sooner that bites.
  // scrollLeft rather than scrollIntoView, which would also move the page
  // vertically.
  const chipRowRef = useRef<HTMLDivElement>(null);
  const activeChipRef = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    const row = chipRowRef.current;
    const chip = activeChipRef.current;
    if (!row || !chip) return;
    row.scrollLeft = Math.max(0, chip.offsetLeft - (row.clientWidth - chip.clientWidth) / 2);
  }, [location.pathname]);

  // -------------------------------------------------------------- mobile
  if (isMobile) {
    // Logged-out marketing pages get the bar only, no app navigation.
    const showTabs = isAuthenticated;

    return (
      <>
        <nav style={styles.nav}>
          <Link to={isAuthenticated ? '/dashboard' : '/'} style={styles.brand}>Sports Analytics</Link>
        </nav>

        {showTabs && activeGroup && (
          <div ref={chipRowRef} style={{
            position: 'sticky', top: NAV_HEIGHT, zIndex: 999,
            background: theme.bgPage, borderBottom: `1px solid ${theme.border}`,
            display: 'flex', gap: 8, overflowX: 'auto', scrollbarWidth: 'none',
            alignItems: 'center',
            // Fixed height so pages can stack their own sticky header under it.
            height: CHIPBAR_HEIGHT, boxSizing: 'border-box', padding: '0 16px',
          }}>
            {activeGroup.items.map((item) => {
              const on = location.pathname === item.to;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  ref={on ? activeChipRef : undefined}
                  style={{
                    flex: '0 0 auto', textDecoration: 'none', whiteSpace: 'nowrap',
                    fontSize: 13, fontWeight: 600, borderRadius: 6, padding: '7px 13px', minHeight: 36,
                    border: on ? `1px solid ${theme.accent}` : `1px solid ${theme.border}`,
                    background: on ? theme.accent : theme.bgCard,
                    color: on ? 'white' : theme.textSecondary,
                  }}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        )}

        {showTabs && (
          <>
            <div style={{
              position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 1000,
              height: TABBAR_HEIGHT,
              display: 'flex',
              background: theme.bgCard,
              borderTop: `1px solid ${theme.border}`,
              paddingBottom: 'env(safe-area-inset-bottom)',
            }}>
              {GROUPS.map((g) => {
                const on = activeGroup?.key === g.key;
                return (
                  <button
                    key={g.key}
                    onClick={() => navigate(g.items[0].to)}
                    aria-current={on ? 'page' : undefined}
                    style={{
                      flex: 1, background: 'none', border: 'none', cursor: 'pointer',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                      gap: 2, padding: 0,
                      color: on ? theme.accent : theme.textMuted,
                      fontSize: 11, fontWeight: on ? 700 : 500,
                    }}
                  >
                    <span aria-hidden style={{ fontSize: 16, lineHeight: 1 }}>{g.icon}</span>
                    {g.label}
                  </button>
                );
              })}
              <button
                onClick={() => setMoreOpen(true)}
                style={{
                  flex: 1, background: 'none', border: 'none', cursor: 'pointer',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  gap: 2, padding: 0, color: theme.textMuted, fontSize: 11, fontWeight: 500,
                }}
              >
                <span aria-hidden style={{ fontSize: 16, lineHeight: 1 }}>☰</span>
                More
              </button>
            </div>

            <BottomSheet open={moreOpen} onClose={() => setMoreOpen(false)} title="More">
              <Link
                to="/dashboard"
                onClick={() => setMoreOpen(false)}
                style={{
                  display: 'block', padding: '13px 2px', minHeight: 44, fontSize: 15,
                  color: theme.textPrimary, textDecoration: 'none',
                  borderBottom: `1px solid ${theme.border}`,
                }}
              >
                Dashboard
              </Link>
              <Link
                to="/billing"
                onClick={() => setMoreOpen(false)}
                style={{
                  display: 'block', padding: '13px 2px', minHeight: 44, fontSize: 15,
                  color: theme.textPrimary, textDecoration: 'none',
                  borderBottom: `1px solid ${theme.border}`,
                }}
              >
                Billing
              </Link>
              <Link
                to="/hit-rate-sheet"
                onClick={() => setMoreOpen(false)}
                style={{
                  display: 'block', padding: '13px 2px', minHeight: 44, fontSize: 15,
                  color: theme.textPrimary, textDecoration: 'none',
                  borderBottom: `1px solid ${theme.border}`,
                }}
              >
                Hit Rate Sheet
              </Link>
              <button
                onClick={handleLogout}
                style={{
                  display: 'block', width: '100%', textAlign: 'left', padding: '13px 2px', minHeight: 44,
                  fontSize: 15, color: theme.dataRed, background: 'none', border: 'none', cursor: 'pointer',
                }}
              >
                Log out
              </button>
            </BottomSheet>
          </>
        )}
      </>
    );
  }

  // ------------------------------------------------------------- desktop
  return (
    <nav style={{ ...styles.nav, padding: '0 24px' }}>
      <Link to={isAuthenticated ? '/dashboard' : '/'} style={styles.brand}>Sports Analytics</Link>

      <ul style={{ display: 'flex', alignItems: 'center', gap: 4, listStyle: 'none', margin: 0, padding: 0 }}>
        {/* Cross-sport, so it sits alongside the per-sport dropdowns rather
            than being duplicated into one of the GROUPS below -- same
            top-level placement Dashboard/Billing get in the mobile "More"
            sheet, just also visible here since desktop has room for it. */}
        <li>
          <Link
            to="/hit-rate-sheet"
            style={{
              ...styles.navBtn, textDecoration: 'none', display: 'inline-block',
              color: location.pathname === '/hit-rate-sheet' ? theme.accent : theme.textSecondary,
            }}
          >
            Hit Rate Sheet
          </Link>
        </li>
        {GROUPS.map((g) => <NavDropdown key={g.key} label={g.label} sections={g.sections} />)}
      </ul>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button style={styles.logoutBtn} onClick={handleLogout}>Logout</button>
      </div>
    </nav>
  );
}
