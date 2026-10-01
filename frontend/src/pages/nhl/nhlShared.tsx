/**
 * Pieces shared by the NHL pages: page chrome, the game picker every
 * game-level page uses, status pills and rank colouring.
 *
 * Colour rules match the rest of the site: blue = good / over, red = bad /
 * under, amber = caution. Never green and red together -- the brand accent
 * is for controls and links only.
 */
import type { CSSProperties, ReactNode } from 'react';
import { fmtDate, fmtTime } from './nhlUtils';
import type { Slate } from './nhlUtils';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

export function PageShell({ title, subtitle, children, maxWidth = 1300 }: {
  title: string; subtitle?: ReactNode; children: ReactNode; maxWidth?: number;
}) {
  const isMobile = useIsMobile();
  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth, margin: '0 auto', background: theme.bgPage,
      minHeight: 'calc(100vh - 60px)', boxSizing: 'border-box', color: theme.textPrimary,
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>{title}</h2>
      {subtitle && <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 16, lineHeight: 1.5 }}>{subtitle}</div>}
      {children}
    </div>
  );
}

export function Card({ children, style, title, aside }: {
  children: ReactNode; style?: CSSProperties; title?: ReactNode; aside?: ReactNode;
}) {
  return (
    <section style={{
      background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 10,
      padding: '14px 16px', boxSizing: 'border-box', minWidth: 0, ...style,
    }}>
      {(title || aside) && (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
          {title && <div style={{ fontSize: 15, fontWeight: 600, color: theme.textPrimary }}>{title}</div>}
          {aside && <div style={{ marginLeft: 'auto', fontSize: 12, color: theme.textSecondary }}>{aside}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Banner({ children }: { children: ReactNode }) {
  return (
    <div style={{
      padding: '10px 14px', borderRadius: 8, marginBottom: 16, fontSize: 13, lineHeight: 1.45,
      background: 'rgba(232,163,61,0.12)', border: '1px solid rgba(232,163,61,0.45)', color: theme.warningText,
    }}>{children}</div>
  );
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return (
    <div style={{
      background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4,
      padding: 16, color: theme.dataRed, marginBottom: 16,
    }}>{children}</div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40, fontSize: 15 }}>{children}</div>;
}

const PILL: Record<string, { bg: string; fg: string }> = {
  Confirmed: { bg: 'rgba(107,168,240,0.15)', fg: theme.dataBlue },
  Projected: { bg: theme.bgCardHover, fg: theme.textSecondary },
  Unknown: { bg: theme.bgCardHover, fg: theme.textMuted },
  tired: { bg: 'rgba(232,163,61,0.15)', fg: theme.warningText },
  rested: { bg: 'rgba(107,168,240,0.15)', fg: theme.dataBlue },
  neutral: { bg: theme.bgCardHover, fg: theme.textSecondary },
  warn: { bg: 'rgba(232,163,61,0.15)', fg: theme.warningText },
};

export function Pill({ kind, children }: { kind: string; children: ReactNode }) {
  const c = PILL[kind] ?? PILL.neutral;
  return (
    <span style={{
      display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
      background: c.bg, color: c.fg, whiteSpace: 'nowrap',
    }}>{children}</span>
  );
}

/** Rank out of 32: top 10 blue, bottom 10 red, the middle grey. */
export function GamePicker({ slate, gameId, onChange }: {
  slate: Slate | null; gameId: number | null; onChange: (id: number) => void;
}) {
  const isMobile = useIsMobile();
  if (!slate) return null;
  const inSlate = slate.games.some((g) => g.game_id === gameId);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
      <label htmlFor="nhl-game" style={{ fontSize: 13, color: theme.textSecondary }}>
        {slate.is_today ? 'Tonight' : fmtDate(slate.date)}
      </label>
      <select
        id="nhl-game"
        value={gameId ?? ''}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{
          minHeight: 40, minWidth: isMobile ? 0 : 260, flex: isMobile ? 1 : undefined,
          background: theme.bgCard, color: theme.textPrimary, border: `1px solid ${theme.borderStrong}`,
          borderRadius: 6, padding: '0 10px', fontSize: 14,
        }}
      >
        {!inSlate && gameId != null && <option value={gameId}>Selected game</option>}
        {slate.games.map((g) => (
          <option key={g.game_id} value={g.game_id}>{g.label} · {fmtTime(g.start_utc)}</option>
        ))}
      </select>
    </div>
  );
}

export function KV({ k, v, vStyle }: { k: ReactNode; v: ReactNode; vStyle?: CSSProperties }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13, padding: '3px 0' }}>
      <span style={{ color: theme.textSecondary }}>{k}</span>
      <span style={{ color: theme.textPrimary, textAlign: 'right', ...vStyle }}>{v}</span>
    </div>
  );
}

