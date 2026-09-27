import { useState } from 'react';
import { formatOdds, prettyBook } from './PropsExplorer';
import { theme } from '../theme';

/**
 * Expandable "Props" section for a starter on the Pitcher Daily Report:
 * best over / best under per market plus how many of his last 10 starts
 * cleared the consensus line. Rows come from get_pitcher_daily_report()
 * (backend/app/data/mlb.py), graded the same way as the Pitcher Matchup
 * page's props card so the two pages agree.
 */

export interface PropSide { line: number | null; price: number; books: string[] }
export interface DailyPitcherProp {
  market: string;
  label: string;
  consensus_line: number | null;
  book_count: number;
  over: PropSide | null;
  under: PropSide | null;
  l10: { hits: number; games: number; values: number[] } | null;
}

const isWin = (m: DailyPitcherProp) => m.market === 'pitcher_record_a_win';

function Side({ m, side }: { m: DailyPitcherProp; side: 'over' | 'under' }) {
  const s = m[side];
  if (!s) return <div style={{ color: theme.textMuted, textAlign: 'right' }}>—</div>;
  const label = isWin(m) ? (side === 'over' ? 'Yes' : 'No') : `${side === 'over' ? 'o' : 'u'}${s.line}`;
  // A best line that's off the consensus is the reason to shop it -- flag it.
  const off = s.line != null && m.consensus_line != null && s.line !== m.consensus_line;
  const books = s.books.map(prettyBook);
  return (
    <div style={{ textAlign: 'right' }}>
      <div style={{ whiteSpace: 'nowrap' }}>
        <span style={{ color: off ? theme.textPrimary : theme.textSecondary, textDecoration: off ? 'underline' : 'none', fontWeight: off ? 700 : 400 }}>{label}</span>{' '}
        <span style={{ color: theme.textPrimary, fontWeight: 700 }}>{formatOdds(s.price)}</span>
      </div>
      <div style={{ fontSize: 10, color: theme.textMuted, whiteSpace: 'nowrap' }}>
        {books[0]}{books.length > 1 ? ` +${books.length - 1}` : ''}
      </div>
    </div>
  );
}

function HitRate({ m }: { m: DailyPitcherProp }) {
  if (!m.l10) return <div style={{ color: theme.textMuted, textAlign: 'right' }}>—</div>;
  const { hits, games } = m.l10;
  const rate = hits / games;
  // Colour only with a real sample; 2-for-3 says very little.
  const color = games < 5 ? theme.textPrimary
    : rate >= 0.7 ? theme.dataBlue : rate <= 0.3 ? theme.dataRed : theme.textPrimary;
  return (
    <div style={{ textAlign: 'right' }}>
      <div style={{ color, fontWeight: 700 }}>{hits}/{games}</div>
      <div style={{ fontSize: 10, color: theme.textMuted }}>{Math.round(rate * 100)}%</div>
    </div>
  );
}

const GRID = 'minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 1fr) 44px';

/** `bare` drops the toggle and always shows the table -- the desktop report
 *  expands a whole table row instead. */
export default function PitcherPropsPanel({ props, bare = false }: { props: DailyPitcherProp[]; bare?: boolean }) {
  const [toggled, setToggled] = useState(false);
  const open = bare || toggled;
  const setOpen = setToggled;
  if (props.length === 0) {
    return <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 10 }}>No props posted yet.</div>;
  }
  const n = Math.max(...props.map((m) => m.l10?.games ?? 0));
  return (
    <div style={{ marginTop: bare ? 0 : 10, maxWidth: bare ? 560 : undefined }}>
      {!bare && <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        style={{
          width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: theme.bgPage, border: `1px solid ${theme.border}`, borderRadius: 6,
          padding: '8px 10px', color: theme.textPrimary, fontSize: 12, fontWeight: 600, cursor: 'pointer',
        }}
      >
        <span>Props &amp; last {n || 10} hit rate <span style={{ color: theme.textMuted, fontWeight: 400 }}>· {props.length}</span></span>
        <span style={{ color: theme.textSecondary, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}>▾</span>
      </button>}

      {open && (
        <div style={{ marginTop: 6, fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
          <div style={{
            display: 'grid', gridTemplateColumns: GRID, gap: 8, padding: '0 2px 4px',
            fontSize: 9.5, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            <span>Prop</span>
            <span style={{ textAlign: 'right' }}>Best over</span>
            <span style={{ textAlign: 'right' }}>Best under</span>
            <span style={{ textAlign: 'right' }}>L{n || 10}</span>
          </div>
          {props.map((m, i) => (
            <div
              key={m.market}
              style={{
                display: 'grid', gridTemplateColumns: GRID, gap: 8, alignItems: 'center',
                padding: '6px 2px', borderTop: i === 0 ? 'none' : `1px solid ${theme.border}`,
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ color: theme.textPrimary, fontWeight: 600 }}>{m.label}</div>
                <div style={{ fontSize: 10, color: theme.textMuted }}>
                  {!isWin(m) && m.consensus_line != null ? `line ${m.consensus_line} · ` : ''}
                  {m.book_count} {m.book_count === 1 ? 'book' : 'books'}
                </div>
              </div>
              <Side m={m} side="over" />
              <Side m={m} side="under" />
              <HitRate m={m} />
            </div>
          ))}
          <div style={{ fontSize: 10, color: theme.textMuted, marginTop: 4, lineHeight: 1.4 }}>
            Hit rate = recent starts over the consensus line (wins for "To record a win").
          </div>
        </div>
      )}
    </div>
  );
}
