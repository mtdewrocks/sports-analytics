import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const styles: Record<string, React.CSSProperties> = {
  nav: {
    background: '#1a1a2e',
    color: 'white',
    padding: '0 24px',
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
    color: '#e94560',
    letterSpacing: 0.5,
    textDecoration: 'none',
  },
  navLinks: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    listStyle: 'none',
  },
  navItem: {
    position: 'relative',
  },
  navBtn: {
    background: 'none',
    border: 'none',
    color: '#ccc',
    cursor: 'pointer',
    padding: '8px 14px',
    fontSize: 14,
    fontWeight: 500,
    borderRadius: 4,
    transition: 'color 0.2s, background 0.2s',
  },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    background: '#16213e',
    borderRadius: 6,
    minWidth: 160,
    boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
    overflow: 'hidden',
    zIndex: 2000,
  },
  dropdownLink: {
    display: 'block',
    padding: '10px 16px',
    color: '#ccc',
    fontSize: 14,
    transition: 'background 0.15s, color 0.15s',
    textDecoration: 'none',
  },
  logoutBtn: {
    background: '#e94560',
    border: 'none',
    color: 'white',
    cursor: 'pointer',
    padding: '7px 16px',
    fontSize: 14,
    fontWeight: 600,
    borderRadius: 4,
    marginLeft: 8,
  },
  hamburger: {
    background: 'none',
    border: 'none',
    color: 'white',
    fontSize: 22,
    cursor: 'pointer',
    display: 'none',
  },
  mobileMenu: {
    display: 'none',
    flexDirection: 'column' as const,
    background: '#16213e',
    position: 'absolute',
    top: 56,
    left: 0,
    right: 0,
    padding: '12px 0',
    zIndex: 999,
  },
};

interface DropdownItem { label: string; to: string; }

function NavDropdown({ label, items }: { label: string; items: DropdownItem[] }) {
  const [open, setOpen] = useState(false);

  return (
    <li
      style={styles.navItem}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        style={styles.navBtn}
        onClick={() => setOpen((o) => !o)}
      >
        {label} ▾
      </button>
      {open && (
        <div style={styles.dropdown}>
          {items.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              style={styles.dropdownLink}
              onClick={() => setOpen(false)}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.background = '#0f3460';
                (e.currentTarget as HTMLElement).style.color = 'white';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = '';
                (e.currentTarget as HTMLElement).style.color = '#ccc';
              }}
            >
              {item.label}
            </Link>
          ))}
        </div>
      )}
    </li>
  );
}

export default function Navbar() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const nbaItems: DropdownItem[] = [
    { label: 'Game Logs', to: '/nba/game-log' },
    { label: 'In/Out Analysis', to: '/nba/in-out' },
    { label: 'Props', to: '/nba/props' },
  ];
  const nflItems: DropdownItem[] = [
    { label: 'Game Log', to: '/nfl/game-log' },
    { label: 'Matchup', to: '/nfl/matchup' },
  ];
  const mlbItems: DropdownItem[] = [
    { label: 'Matchup', to: '/mlb/matchup' },
    { label: 'Hot Hitters', to: '/mlb/hot-hitters' },
    { label: 'Props', to: '/mlb/props' },
  ];

  return (
    <>
      <nav style={styles.nav}>
        <Link to="/nba/game-log" style={styles.brand}>Sports Analytics</Link>

        {/* Desktop menu */}
        <ul style={{ ...styles.navLinks, display: 'flex' } as React.CSSProperties}>
          <NavDropdown label="NBA" items={nbaItems} />
          <NavDropdown label="NFL" items={nflItems} />
          <NavDropdown label="MLB" items={mlbItems} />
        </ul>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button style={styles.logoutBtn} onClick={handleLogout}>Logout</button>
          <button
            style={{ ...styles.hamburger, display: 'block' }}
            onClick={() => setMobileOpen((o) => !o)}
            aria-label="Toggle menu"
          >
            {mobileOpen ? '✕' : '☰'}
          </button>
        </div>
      </nav>

      {/* Mobile menu */}
      {mobileOpen && (
        <div style={{ ...styles.mobileMenu, display: 'flex' }}>
          <div style={{ padding: '8px 16px', color: '#e94560', fontWeight: 700, fontSize: 13 }}>NBA</div>
          {nbaItems.map((i) => (
            <Link key={i.to} to={i.to} style={{ padding: '10px 24px', color: '#ccc', fontSize: 14 }} onClick={() => setMobileOpen(false)}>{i.label}</Link>
          ))}
          <div style={{ padding: '8px 16px', color: '#e94560', fontWeight: 700, fontSize: 13 }}>NFL</div>
          {nflItems.map((i) => (
            <Link key={i.to} to={i.to} style={{ padding: '10px 24px', color: '#ccc', fontSize: 14 }} onClick={() => setMobileOpen(false)}>{i.label}</Link>
          ))}
          <div style={{ padding: '8px 16px', color: '#e94560', fontWeight: 700, fontSize: 13 }}>MLB</div>
          {mlbItems.map((i) => (
            <Link key={i.to} to={i.to} style={{ padding: '10px 24px', color: '#ccc', fontSize: 14 }} onClick={() => setMobileOpen(false)}>{i.label}</Link>
          ))}
        </div>
      )}
    </>
  );
}
