import React, { useState, useEffect } from 'react';
import { getMLBHotHitters } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import StatCard from '../../components/StatCard';
import ChipRow from '../../components/ChipRow';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';
import { prettyBook, formatOdds } from '../../components/PropsExplorer';

// ── Today's context (lineup, opposing starter, best 1+ hit price) ─────────────

interface HitPrice { line: number; price: number; books: string[]; is_live: boolean }
interface HitterToday {
  status: 'in_lineup' | 'pending' | 'out' | 'no_game';
  batting_order: number | null;
  pitcher: string | null;
  throws: 'L' | 'R' | null;
  vs_side: 'L' | 'R' | null;
  pitcher_stats: { avg?: number; woba?: number; k_pct?: number; bb_pct?: number; tbf?: number } | null;
  hit_price: HitPrice | null;
}

/** Below this many batters faced on that side, the pitcher's split is shown
 *  but flagged -- same floor Matchup Edge uses before trusting a split. */
const THIN_SAMPLE_TBF = 60;

const ordinal = (n: number) => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};
const fmt3 = (v?: number) => (v == null ? '—' : v.toFixed(3).replace(/^0/, ''));
const fmt1 = (v?: number) => (v == null ? '—' : `${v.toFixed(1)}%`);
/** American odds -> implied win probability, as a whole percent. */
const impliedPct = (o: number) => Math.round(100 * (o < 0 ? -o / (-o + 100) : 100 / (o + 100)));

const sideWord = (s: 'L' | 'R') => (s === 'L' ? 'left' : 'right');

function Pill({ children, tone }: { children: React.ReactNode; tone: 'red' | 'amber' | 'muted' }) {
  const c = tone === 'red' ? theme.dataRed : tone === 'amber' ? theme.warningText : theme.textSecondary;
  const bg = tone === 'red' ? 'rgba(244,87,63,0.15)' : tone === 'amber' ? 'rgba(232,163,61,0.15)' : theme.bgPage;
  return (
    <span style={{ fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 999, background: bg, color: c, whiteSpace: 'nowrap', textTransform: 'none', letterSpacing: 0 }}>
      {children}
    </span>
  );
}

function HitPriceBox({ price }: { price: HitPrice | null }) {
  if (!price) {
    return (
      <div style={{ textAlign: 'center', border: `1px dashed ${theme.border}`, borderRadius: 8, padding: '6px 10px', minWidth: 84 }}>
        <div style={{ fontSize: 9.5, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>1+ hit</div>
        <div style={{ fontSize: 12, color: theme.textMuted, fontWeight: 600 }}>No line</div>
      </div>
    );
  }
  return (
    <div style={{ textAlign: 'center', background: 'rgba(29,158,117,0.10)', border: '1px solid rgba(29,158,117,0.35)', borderRadius: 8, padding: '6px 10px', minWidth: 84 }}>
      <div style={{ fontSize: 9.5, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>1+ hit</div>
      <div style={{ fontSize: 17, fontWeight: 700, color: theme.accent, lineHeight: 1.15, fontVariantNumeric: 'tabular-nums' }}>
        {formatOdds(price.price)}
      </div>
      <div style={{ fontSize: 10.5, color: theme.textPrimary }}>{impliedPct(price.price)}% implied</div>
      <div style={{ fontSize: 10.5, color: theme.textMuted }}>
        {prettyBook(price.books[0])}{price.books.length > 1 ? ` +${price.books.length - 1}` : ''}
      </div>
    </div>
  );
}

/** The pitcher half of the strip: name, hand, and his numbers against the
 *  side this hitter bats from today. */
function PitcherLine({ t }: { t: HitterToday }) {
  if (!t.pitcher) {
    return <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 3 }}>Opposing starter not announced yet.</div>;
  }
  const ps = t.pitcher_stats;
  const thin = ps?.tbf != null && ps.tbf < THIN_SAMPLE_TBF;
  const num = (v: string) => <span style={{ color: theme.textPrimary, fontWeight: 600 }}>{v}</span>;
  return (
    <>
      <div style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary, marginTop: 3 }}>
        {t.pitcher}
        {t.throws && <span style={{ color: theme.textMuted, fontWeight: 400, fontSize: 11.5 }}> · throws {sideWord(t.throws)}</span>}
      </div>
      {ps && t.vs_side ? (
        <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 2, fontVariantNumeric: 'tabular-nums', lineHeight: 1.5 }}>
          vs {sideWord(t.vs_side)}-handed hitters: {num(fmt3(ps.avg))} avg allowed · {num(fmt3(ps.woba))} wOBA
          {' · '}{num(fmt1(ps.k_pct))} strikeout rate · {num(fmt1(ps.bb_pct))} walk rate
          <div style={{ fontSize: 10.5, color: thin ? theme.warningText : theme.textMuted }}>
            2025–26 combined{ps.tbf != null ? ` · ${ps.tbf} batters faced` : ''}{thin ? ' · small sample' : ''}
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 2 }}>
          {t.status === 'pending' ? 'Split shows once his side for this game is known.' : 'No split on file for this pitcher.'}
        </div>
      )}
    </>
  );
}

/** Same content as the mobile strip, laid out for a table cell. */
function DesktopToday({ t }: { t: HitterToday | null | undefined }) {
  if (!t) return <span style={{ color: theme.textMuted }}>—</span>;
  if (t.status === 'out') return <Pill tone="red">Out of lineup</Pill>;
  if (t.status === 'no_game') return <Pill tone="muted">No game today</Pill>;
  return (
    <div>
      {t.status === 'pending'
        ? <Pill tone="amber">Lineup pending</Pill>
        : t.batting_order != null && <span style={{ fontSize: 11, color: theme.accent, fontWeight: 600 }}>Batting {ordinal(t.batting_order)}</span>}
      <PitcherLine t={t} />
    </div>
  );
}

function TodayStrip({ t }: { t: HitterToday | null | undefined }) {
  if (!t) return null;
  const label = (
    <div style={{ fontSize: 9.5, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      Today
      {t.status === 'in_lineup' && t.batting_order != null && (
        <span style={{ textTransform: 'none', letterSpacing: 0, fontSize: 10.5, fontWeight: 600, color: theme.accent, background: 'rgba(29,158,117,0.12)', borderRadius: 4, padding: '1px 6px' }}>
          Batting {ordinal(t.batting_order)}
        </span>
      )}
      {t.status === 'pending' && <Pill tone="amber">Lineup pending</Pill>}
    </div>
  );
  const wrap: React.CSSProperties = { marginTop: 10, paddingTop: 10, borderTop: `1px solid ${theme.border}` };

  if (t.status === 'out' || t.status === 'no_game') {
    return (
      <div style={wrap}>
        {label}
        <div style={{ marginTop: 5 }}>
          <Pill tone={t.status === 'out' ? 'red' : 'muted'}>{t.status === 'out' ? 'Out of lineup' : 'No game today'}</Pill>
        </div>
      </div>
    );
  }
  return (
    <div style={{ ...wrap, display: 'grid', gridTemplateColumns: '1fr auto', gap: 12, alignItems: 'center' }}>
      <div style={{ minWidth: 0 }}>
        {label}
        <PitcherLine t={t} />
      </div>
      <HitPriceBox price={t.hit_price} />
    </div>
  );
}

/** True when every non-null value in this column parses as a number. Used to
 *  tell the identity columns (Player, Team) from the sortable stat columns,
 *  since the API decides the column set and there's no fixed list to check
 *  against -- that's also why the card layout below is generated rather than
 *  hardcoded, so a new stat column keeps working with no change here. */
function isNumericColumn(rows: Record<string, any>[], col: string): boolean {
  const vals = rows.map((r) => r[col]).filter((v) => v !== null && v !== undefined && v !== '');
  return vals.length > 0 && vals.every((v) => !isNaN(parseFloat(String(v))));
}

interface SortConfig {
  key: string;
  direction: 'asc' | 'desc';
}

export default function MLBHotHitters() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [hitters, setHitters] = useState<Record<string, any>[]>([]);
  const [sortConfig, setSortConfig] = useState<SortConfig | null>({ key: 'AVG', direction: 'desc' });

  useEffect(() => {
    getMLBHotHitters()
      .then((res) => setHitters(res.data))
      .catch(() => setError('Failed to load hot hitters.'))
      .finally(() => setLoading(false));
  }, []);

  const isMobile = useIsMobile();

  // `today` is a nested object for the strip below, not a column.
  const columns = hitters.length > 0 ? Object.keys(hitters[0]).filter((c) => c !== 'today') : [];
  const statColumns = columns.filter((c) => isNumericColumn(hitters, c));
  const identityColumns = columns.filter((c) => !statColumns.includes(c));

  const handleSort = (key: string) => {
    setSortConfig((prev) => {
      if (prev?.key === key) {
        return { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
      }
      return { key, direction: 'asc' };
    });
  };

  const sortedHitters = React.useMemo(() => {
    if (!sortConfig) return hitters;
    return [...hitters].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;
      const aNum = parseFloat(aVal);
      const bNum = parseFloat(bVal);
      if (!isNaN(aNum) && !isNaN(bNum)) {
        return sortConfig.direction === 'asc' ? aNum - bNum : bNum - aNum;
      }
      const aStr = String(aVal).toLowerCase();
      const bStr = String(bVal).toLowerCase();
      if (aStr < bStr) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aStr > bStr) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [hitters, sortConfig]);

  return (
    <div style={{ padding: isMobile ? 16 : 24, minHeight: 'calc(100vh - 60px)', background: theme.bgPage }}>
      <h2 style={{ marginTop: 0, marginBottom: isMobile ? 14 : 24, color: theme.textPrimary }}>Hot Hitters — Last 7 Days</h2>

      {/* On a phone the sort moves out of the table headers and becomes the
          primary control -- it's the only way to ask this page a question once
          the columns won't fit. */}
      {isMobile && statColumns.length > 0 && (
        <ChipRow
          chips={statColumns.map((c) => ({
            key: c,
            label: c,
            activeSuffix: sortConfig?.direction === 'asc' ? '▲' : '▼',
          }))}
          value={sortConfig?.key ?? ''}
          onChange={handleSort}
          bleed={16}
          style={{ marginBottom: 14 }}
        />
      )}

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}
      {!loading && !error && sortedHitters.length > 0 && isMobile && (
        <div>
          {sortedHitters.map((row, i) => {
            const sortKey = sortConfig?.key ?? statColumns[0];
            const today = row.today as HitterToday | null | undefined;
            // Out-of-lineup / off-day hitters keep their rank (the list is
            // about the last 7 days, which doesn't change), just dimmed.
            const inactive = today?.status === 'out' || today?.status === 'no_game';
            return (
              <StatCard
                key={i}
                rank={i + 1}
                title={<span style={{ fontWeight: 700 }}>{String(row[identityColumns[0]] ?? '—')}</span>}
                titleAside={identityColumns[1] ? String(row[identityColumns[1]] ?? '') : undefined}
                value={String(row[sortKey] ?? '—')}
                valueColor={i < 3 ? theme.dataBlue : theme.textPrimary}
                valueLabel={sortKey}
                meta={statColumns
                  .filter((c) => c !== sortKey)
                  .map((c) => <>{String(row[c] ?? '—')} {c}</>)}
                style={inactive ? { opacity: 0.6 } : undefined}
              >
                <TodayStrip t={today} />
              </StatCard>
            );
          })}
          <div style={{ marginTop: 10, fontSize: 13, color: theme.textSecondary }}>
            {sortedHitters.length} player{sortedHitters.length !== 1 ? 's' : ''}
          </div>
        </div>
      )}

      {!loading && !error && sortedHitters.length > 0 && !isMobile && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                {columns.map((col) => (
                  <th
                    key={col}
                    onClick={() => handleSort(col)}
                    style={{
                      padding: '10px 14px',
                      textAlign: 'left',
                      whiteSpace: 'nowrap',
                      cursor: 'pointer',
                      userSelect: 'none',
                    }}
                  >
                    {col}
                    {sortConfig?.key === col && (
                      <span style={{ marginLeft: 6, fontSize: 10 }}>
                        {sortConfig.direction === 'asc' ? '▲' : '▼'}
                      </span>
                    )}
                  </th>
                ))}
                <th style={{ padding: '10px 14px', textAlign: 'left', whiteSpace: 'nowrap' }}>Today</th>
                <th style={{ padding: '10px 14px', textAlign: 'center', whiteSpace: 'nowrap' }}>1+ hit</th>
              </tr>
            </thead>
            <tbody>
              {sortedHitters.map((row, i) => (
                <tr key={i} style={{
                  borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage, color: theme.textPrimary,
                  opacity: row.today?.status === 'out' || row.today?.status === 'no_game' ? 0.6 : 1,
                }}>
                  {columns.map((col) => (
                    <td key={col} style={{ padding: '8px 14px', whiteSpace: 'nowrap' }}>
                      {String(row[col] ?? '—')}
                    </td>
                  ))}
                  <td style={{ padding: '8px 14px', minWidth: 300 }}>
                    <DesktopToday t={row.today as HitterToday | null | undefined} />
                  </td>
                  <td style={{ padding: '6px 14px' }}>
                    {row.today && (row.today.status === 'in_lineup' || row.today.status === 'pending')
                      ? <HitPriceBox price={row.today.hit_price} />
                      : <span style={{ color: theme.textMuted }}>—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 10, fontSize: 13, color: theme.textSecondary }}>{sortedHitters.length} player{sortedHitters.length !== 1 ? 's' : ''}</div>
        </div>
      )}
      {!loading && !error && sortedHitters.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          No hot hitters data available today.
        </div>
      )}
    </div>
  );
}
