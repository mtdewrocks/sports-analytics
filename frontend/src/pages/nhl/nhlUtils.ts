/** Non-component helpers for the NHL pages (kept apart from nhlShared.tsx so
 *  React fast refresh keeps working -- a file that mixes the two can't be
 *  hot-reloaded). */
import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getNHLSlate } from '../../api/nhl';
import { theme } from '../../theme';

export const STEEL = '#9db4cc';           // NHL's sport colour (siteMap.ts), used for neutral edge bars

export interface SlateGame {
  game_id: number;
  label: string;
  away: string;
  home: string;
  start_utc: string | null;
  state: string | null;
}
export interface Slate { date: string; is_today: boolean; games: SlateGame[] }

export function rankColor(rank: number | null | undefined, graded = true): string {
  if (!graded || rank == null) return theme.textSecondary;
  if (rank <= 10) return theme.dataBlue;
  if (rank >= 23) return theme.dataRed;
  return theme.textSecondary;
}

export function pctColor(pct: number | null | undefined): string {
  if (pct == null) return theme.textSecondary;
  const v = pct > 1 ? pct / 100 : pct;
  return v >= 0.6 ? theme.dataBlue : v >= 0.4 ? '#9ca3af' : theme.dataRed;
}

export function ordinal(n: number | null | undefined): string {
  if (n == null) return '—';
  const s = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${s}`;
}

/** 1 -> 'fewest', 3 -> '3rd fewest'. */
export function rankWords(rank: number | null | undefined, words: string): string {
  if (rank == null) return '';
  return rank === 1 ? words : `${ordinal(rank)} ${words}`;
}

/** 'L1' -> 'Line 1', 'D2' -> 'Pair 2', 'PP1' -> 'PP1'. */
export function roleLabel(unit: string | null | undefined): string | null {
  if (!unit) return null;
  if (unit.startsWith('L')) return `Line ${unit.slice(1)}`;
  if (unit.startsWith('D')) return `Pair ${unit.slice(1)}`;
  return unit;
}

export function fmtTime(utc: string | null | undefined): string {
  if (!utc) return '';
  const d = new Date(utc);
  return isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export function fmtDate(iso: string | null | undefined, withWeekday = true): string {
  if (!iso) return '';
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return d.toLocaleDateString('en-US', withWeekday
    ? { weekday: 'short', month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric' });
}

export function fmtSv(v: number | null | undefined): string {
  return v == null ? '—' : v.toFixed(3).replace(/^0/, '');
}

export function signed(v: number | null | undefined, digits = 1): string {
  if (v == null) return '—';
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}`;
}

/** The slate (today, or the next day with games) plus the selected game,
 *  kept in the URL (?game=) so pages can link to each other. */
export function useGamePicker() {
  const [params, setParams] = useSearchParams();
  const [slate, setSlate] = useState<Slate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const fromUrl = Number(params.get('game')) || null;

  useEffect(() => {
    getNHLSlate()
      .then((res) => {
        if (res.data.error) setError(res.data.error);
        else setSlate(res.data);
      })
      .catch((e) => setError(e?.response?.data?.detail || 'Could not load the NHL schedule.'))
      .finally(() => setLoading(false));
  }, []);

  const gameId = fromUrl ?? slate?.games[0]?.game_id ?? null;
  const setGameId = (id: number) => {
    const next = new URLSearchParams(params);
    next.set('game', String(id));
    setParams(next, { replace: true });
  };
  return { slate, gameId, setGameId, loading, error };
}

export const th: CSSProperties = {
  fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, color: theme.textSecondary, fontWeight: 600,
  textAlign: 'left', padding: '9px 12px', borderBottom: `1px solid ${theme.borderStrong}`, whiteSpace: 'nowrap',
};
export const td: CSSProperties = {
  fontSize: 13, color: theme.textPrimary, padding: '9px 12px', borderBottom: `1px solid ${theme.border}`,
  whiteSpace: 'nowrap',
};
export const label: CSSProperties = { fontSize: 12, color: theme.textSecondary };
export const groupTitle: CSSProperties = {
  fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.6, color: theme.textSecondary, fontWeight: 700,
  margin: '10px 0 4px',
};

