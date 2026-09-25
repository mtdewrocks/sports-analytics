import { useState, useEffect, useMemo } from 'react';
import type { ReactNode } from 'react';
import LoadingSpinner from './LoadingSpinner';
import SegmentedToggle from './SegmentedToggle';
import ScrollTable from './ScrollTable';
import OddsDisclaimer from './OddsDisclaimer';
import useIsMobile from '../hooks/useIsMobile';
import { theme } from '../theme';

// Split out of the old combined PropMiddles.tsx (one page, an NFL/MLB toggle)
// into a shared component the same way PropsExplorer.tsx already split off
// from MLBProps.tsx -- so NFL and MLB each get their own page and their own
// spot in that sport's nav, instead of a standalone "Middles" link people
// weren't finding. `title` is required (not defaulted) for the same reason
// PropsExplorer's is: a copy-pasted wrapper missing its own title silently
// shows the OTHER sport's data under the wrong heading.

type Kind = 'all' | 'middle+arb' | 'arb' | 'middle' | 'anti_middle';

interface Row {
  Player: string; market: string; kind: string;
  over_book: string; over_line: number; over_price: number;
  under_book: string; under_line: number; under_price: number;
  gap: number; window: string; window_width: number;
  stake_over_pct: number; one_wins_pct: number; window_pct: number;
  breakeven_window_rate_pct: number;
  commence_time?: string; home_team?: string; away_team?: string;
  [k: string]: any;
}

interface MiddlesExplorerProps {
  fetcher: (params: Record<string, any>) => Promise<{ data: Row[] }>;
  title: string;
  /** Rendered under the heading -- the Betting pages' sport toggle. */
  toolbar?: ReactNode;
}

const KIND_LABEL: Record<string, string> = {
  'middle+arb': 'Middle + Arb',
  arb: 'Arb',
  middle: 'Middle',
  anti_middle: 'Anti-Middle',
};

// Green only where the pair wins no matter the result; blue where it needs the
// window to land; amber where the window is the one result you're betting
// AGAINST -- a real trade, but one that needs a judgment call the other three
// don't (is that result actually unlikely for this market?), so it gets its
// own colour rather than blending into "needs the window".
const KIND_COLOR: Record<string, string> = {
  'middle+arb': theme.accent,
  arb: theme.accent,
  middle: theme.dataBlue,
  anti_middle: theme.warningText,
};

function fmtOdds(n: number): string {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return n > 0 ? `+${n.toFixed(0)}` : n.toFixed(0);
}

function book(b: string): string {
  return String(b || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function MiddlesExplorer({ fetcher, title, toolbar }: MiddlesExplorerProps) {
  const [kind, setKind] = useState<Kind>('all');
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [marketFilter, setMarketFilter] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    setLoading(true);
    setError('');
    fetcher({})
      .then((res) => setRows(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load.'))
      .finally(() => setLoading(false));
    // fetcher is a stable module-level export (getNFLMiddles / getMLBMiddles),
    // not state -- re-running this on every render would refetch in a loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const markets = useMemo(
    () => [...new Set(rows.map((r) => r.market).filter(Boolean))].sort(),
    [rows],
  );

  const shown = useMemo(
    () => rows.filter((r) => (kind === 'all' || r.kind === kind)
      && (!marketFilter || r.market === marketFilter)),
    [rows, kind, marketFilter],
  );

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    rows.forEach((r) => { c[r.kind] = (c[r.kind] || 0) + 1; });
    return c;
  }, [rows]);

  const fetchedAt = useMemo(() => {
    let best: string | null = null;
    for (const r of shown) {
      const v = r.fetched_at || r.commence_time_fetched;
      if (v && (best === null || String(v) > best)) best = String(v);
    }
    return best;
  }, [shown]);

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 1200, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>{title}</h2>
      {toolbar}
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 14, lineHeight: 1.55 }}>
        Pairs where one book's Over and another book's Under are both plus money.
        An <strong style={{ color: theme.accent }}>arb</strong> pays whichever side wins.
        A <strong style={{ color: theme.dataBlue }}>middle</strong> has a gap between
        the two lines where <em>both</em> bets cash — the window column is the
        result that does it. An <strong style={{ color: theme.warningText }}>anti-middle</strong> is
        the same gap with the lines swapped: it cashes on <em>anything except</em> the
        window, so it's a bet against that one result — worth it only if the window
        is actually unlikely for that market. "Needs" is the number to weigh that against.
        Games already in progress aren't listed here — their lines are frozen from before
        kickoff, so a pair on one isn't a bet you can still place (it still shows on the
        Props page, marked <span style={{ color: theme.warningText, fontWeight: 700 }}>LIVE</span>).
      </div>

      <OddsDisclaimer fetchedAt={fetchedAt} compact={isMobile} />

      <SegmentedToggle
        value={kind}
        onChange={setKind}
        fullWidth
        options={([
          ['all', `All (${rows.length})`],
          ['middle+arb', `Middle+Arb (${counts['middle+arb'] || 0})`],
          ['arb', `Arb (${counts.arb || 0})`],
          ['middle', `Middle (${counts.middle || 0})`],
          ['anti_middle', `Anti-Middle (${counts.anti_middle || 0})`],
        ] as [Kind, string][]).map(([value, label]) => ({ value, label }))}
        style={{ marginBottom: 10 }}
      />

      {markets.length > 0 && (
        <select
          value={marketFilter}
          onChange={(e) => setMarketFilter(e.target.value)}
          style={{
            width: isMobile ? '100%' : 260, minHeight: 40, padding: '9px 12px',
            fontSize: 14, borderRadius: 4, border: `1px solid ${theme.border}`,
            background: theme.bgCard, color: theme.textPrimary,
            boxSizing: 'border-box', marginBottom: 16,
          }}
        >
          <option value="">All markets</option>
          {markets.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      )}

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{
          background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`,
          borderRadius: 4, padding: 16, color: theme.dataRed,
        }}>{error}</div>
      )}

      {!loading && !error && shown.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 44, fontSize: 15 }}>
          Nothing qualifying right now. Books agreeing with each other is the
          normal state — this page is empty far more often than not.
        </div>
      )}

      {!loading && !error && shown.length > 0 && (isMobile ? (
        <div>
          {shown.map((r, i) => (
            <div key={i} style={{
              background: theme.bgCard, borderRadius: 8, padding: 13, marginBottom: 10,
              borderLeft: `3px solid ${KIND_COLOR[r.kind] || theme.border}`,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontWeight: 700, fontSize: 14, color: theme.textPrimary }}>{r.Player}</span>
                <span style={{
                  fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase',
                  color: KIND_COLOR[r.kind] || theme.textMuted, letterSpacing: '0.04em',
                }}>{KIND_LABEL[r.kind] || r.kind}</span>
              </div>
              <div style={{ fontSize: 11.5, color: theme.textMuted, marginBottom: 8 }}>
                {r.market}{r.away_team ? ` · ${r.away_team} @ ${r.home_team}` : ''}
              </div>

              <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                {[
                  ['OVER', r.over_line, r.over_price, r.over_book],
                  ['UNDER', r.under_line, r.under_price, r.under_book],
                ].map(([label, line, price, bk]) => (
                  <div key={String(label)} style={{
                    flex: 1, background: theme.bgPage, borderRadius: 6, padding: '8px 10px',
                  }}>
                    <div style={{ fontSize: 9.5, color: theme.textMuted, letterSpacing: '0.05em' }}>{label}</div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>
                      {Number(line).toFixed(1)} <span style={{ color: theme.accent }}>{fmtOdds(Number(price))}</span>
                    </div>
                    <div style={{ fontSize: 10.5, color: theme.textSecondary }}>{book(String(bk))}</div>
                  </div>
                ))}
              </div>

              <div style={{ fontSize: 11.5, color: theme.textSecondary, fontVariantNumeric: 'tabular-nums' }}>
                {r.kind === 'anti_middle' ? (
                  <>Wins on any result except{' '}
                    <strong style={{ color: theme.warningText }}>{r.window}</strong>, paying{' '}
                    <strong style={{ color: r.one_wins_pct >= 0 ? theme.accent : theme.dataRed }}>
                      {r.one_wins_pct >= 0 ? '+' : ''}{r.one_wins_pct.toFixed(1)}%
                    </strong>. Both legs lose if {r.window} does land — only take this if you think
                    that happens under <strong style={{ color: theme.warningText }}>
                      {r.breakeven_window_rate_pct.toFixed(0)}%
                    </strong> of the time. Stake {r.stake_over_pct.toFixed(0)}% on the Over.</>
                ) : r.window ? (
                  <>Both win on <strong style={{ color: theme.dataBlue }}>{r.window}</strong> → {r.window_pct.toFixed(1)}%.
                    Otherwise <strong style={{ color: r.one_wins_pct >= 0 ? theme.accent : theme.dataRed }}>
                      {r.one_wins_pct >= 0 ? '+' : ''}{r.one_wins_pct.toFixed(1)}%
                    </strong>. Stake {r.stake_over_pct.toFixed(0)}% on the Over.</>
                ) : (
                  <>No window — one side always wins. Otherwise{' '}
                    <strong style={{ color: r.one_wins_pct >= 0 ? theme.accent : theme.dataRed }}>
                      {r.one_wins_pct >= 0 ? '+' : ''}{r.one_wins_pct.toFixed(1)}%
                    </strong>. Stake {r.stake_over_pct.toFixed(0)}% on the Over.</>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <ScrollTable>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: theme.bgCard, color: theme.textSecondary }}>
                {['Player', 'Market', 'Type', 'Over', 'Under', 'Window',
                  'If window', 'Otherwise', 'Stake Over', 'Needs'].map((h, i) => (
                  <th key={h} style={{
                    padding: '9px 10px', textAlign: i < 3 ? 'left' : 'right',
                    fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em',
                    borderBottom: `1px solid ${theme.border}`, whiteSpace: 'nowrap',
                    ...(i === 0 ? stickyFirst : {}),
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${theme.border}` }}>
                  <td style={{ padding: '9px 10px', color: theme.textPrimary, fontWeight: 600, ...stickyFirst }}>
                    {r.Player}
                  </td>
                  <td style={{ padding: '9px 10px', color: theme.textSecondary }}>{r.market}</td>
                  <td style={{
                    padding: '9px 10px', fontWeight: 700, fontSize: 11,
                    color: KIND_COLOR[r.kind] || theme.textMuted, whiteSpace: 'nowrap',
                  }}>{KIND_LABEL[r.kind] || r.kind}</td>
                  <td style={{ padding: '9px 10px', textAlign: 'right', color: theme.textPrimary, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
                    {r.over_line?.toFixed(1)} {fmtOdds(r.over_price)}
                    <div style={{ fontSize: 10.5, color: theme.textMuted }}>{book(r.over_book)}</div>
                  </td>
                  <td style={{ padding: '9px 10px', textAlign: 'right', color: theme.textPrimary, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
                    {r.under_line?.toFixed(1)} {fmtOdds(r.under_price)}
                    <div style={{ fontSize: 10.5, color: theme.textMuted }}>{book(r.under_book)}</div>
                  </td>
                  <td style={{
                    padding: '9px 10px', textAlign: 'right', fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                    color: r.kind === 'anti_middle' ? theme.warningText : theme.dataBlue,
                  }}>
                    {r.window || '—'}
                  </td>
                  <td style={{ padding: '9px 10px', textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: theme.textPrimary }}>
                    {r.window_pct > 0 ? `+${r.window_pct.toFixed(1)}%` : `${r.window_pct.toFixed(1)}%`}
                  </td>
                  <td style={{
                    padding: '9px 10px', textAlign: 'right', fontVariantNumeric: 'tabular-nums',
                    fontWeight: 700, color: r.one_wins_pct >= 0 ? theme.accent : theme.dataRed,
                  }}>
                    {r.one_wins_pct >= 0 ? '+' : ''}{r.one_wins_pct.toFixed(2)}%
                  </td>
                  <td style={{ padding: '9px 10px', textAlign: 'right', color: theme.textSecondary, fontVariantNumeric: 'tabular-nums' }}>
                    {r.stake_over_pct?.toFixed(0)}%
                  </td>
                  <td style={{ padding: '9px 10px', textAlign: 'right', color: theme.textSecondary, fontVariantNumeric: 'tabular-nums' }}>
                    {r.breakeven_window_rate_pct > 0 ? `${r.breakeven_window_rate_pct.toFixed(0)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollTable>
      ))}

      {!loading && shown.length > 0 && (
        <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 14, lineHeight: 1.6 }}>
          <strong>Needs</strong> reads in opposite directions depending on the row. For a{' '}
          <strong style={{ color: theme.dataBlue }}>middle</strong> that loses money outside
          its window, it's how often the window has to land <em>at least</em> to break even.
          For an <strong style={{ color: theme.warningText }}>anti-middle</strong>, it's the
          opposite — the highest chance that window can have before betting against it stops
          being worth it. A pair showing a positive &ldquo;Otherwise&rdquo; figure doesn't
          depend on the window at all.
          <br />
          An anti-middle is only as good as your read on how likely its window actually is —
          this page prices the trade but has no view on that itself. A one-number gap is a
          common result in a low-scoring counting stat (MLB hits, total bases) and a rare one
          in a wide-range stat (NFL yardage, NBA points); the same &ldquo;Needs&rdquo; number
          means a very different thing in each.
          <br />
          Most of what appears here is a <strong>stale price</strong> rather than free
          money — the far side of a gap is usually a book that has not updated yet, and
          the larger the edge, the likelier the price moves or the bet is voided before
          it fills.
        </div>
      )}
    </div>
  );
}

const stickyFirst = {
  position: 'sticky' as const,
  left: 0,
  background: theme.bgPage,
  zIndex: 1,
};
