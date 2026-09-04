import { useState, useEffect, useRef } from 'react';
import { theme } from '../theme';

interface SearchDropdownProps {
  players: string[];
  value: string;
  onSelect: (p: string) => void;
  placeholder: string;
  disabled?: boolean;
  inputStyle?: React.CSSProperties;
}

export default function SearchDropdown({
  players, value, onSelect, placeholder, disabled, inputStyle,
}: SearchDropdownProps) {
  const [search, setSearch] = useState(value);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => { setSearch(value); }, [value]);

  const filtered = search.length === 0
    ? players
    : players.filter((p) => p.toLowerCase().includes(search.toLowerCase()));

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'center' }}>
      <input
        disabled={disabled}
        style={{
          padding: '8px 12px',
          border: `1px solid ${theme.border}`,
          borderRadius: '4px 0 0 4px',
          fontSize: 14,
          width: '100%',
          boxSizing: 'border-box',
          background: disabled ? theme.bgCard : theme.bgPage,
          color: theme.textPrimary,
          cursor: disabled ? 'not-allowed' : 'text',
          ...inputStyle,
        }}
        placeholder={placeholder}
        value={search}
        onChange={(e) => { setSearch(e.target.value); setOpen(true); }}
        onFocus={() => { setSearch(''); }}
        onBlur={() => setTimeout(() => {
          setOpen(false);
          // If text doesn't match a valid selection, clear parent state
          if (!players.includes(search)) { onSelect(''); setSearch(''); }
        }, 150)}
      />
      <button
        disabled={disabled}
        onMouseDown={(e) => { e.preventDefault(); setOpen(prev => !prev); }}
        style={{
          padding: '8px 10px',
          border: `1px solid ${theme.border}`,
          borderLeft: 'none',
          borderRadius: '0 4px 4px 0',
          background: disabled ? theme.bgCard : theme.bgPage,
          cursor: disabled ? 'not-allowed' : 'pointer',
          fontSize: 12,
          color: theme.textSecondary,
          lineHeight: 1,
        }}
      >▾</button>
      </div>
      {open && !disabled && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
          background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 4,
          maxHeight: 200, overflowY: 'auto', boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
        }}>
          {filtered.length === 0 ? (
            <div style={{ padding: '8px 12px', color: theme.textMuted, fontSize: 13 }}>No players found</div>
          ) : (
            filtered.map((p) => (
              <div
                key={p}
                onMouseDown={() => { onSelect(p); setSearch(p); setOpen(false); }}
                style={{ padding: '8px 12px', cursor: 'pointer', fontSize: 13, color: theme.textPrimary }}
                onMouseEnter={(e) => (e.currentTarget.style.background = theme.bgCardHover)}
                onMouseLeave={(e) => (e.currentTarget.style.background = theme.bgCard)}
              >
                {p}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
