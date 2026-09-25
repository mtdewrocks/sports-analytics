import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import LoadingSpinner from './LoadingSpinner';
import SegmentedToggle from './SegmentedToggle';
import OddsDisclaimer, { latestFetchedAt } from './OddsDisclaimer';
import { formatOdds, prettyBook, prettyMarket } from './PropsExplorer';
import useIsMobile from '../hooks/useIsMobile';
import { theme } from '../theme';

/**
 * EV Finder -- shared by the MLB and NFL pages, same split as
 * MiddlesExplorer/PropsExplorer. `title` is required for the same reason it
 * is there: a copy-pasted wrapper can't silently show the other sport under
 * the wrong heading.
 *
 * Two modes, one endpoint (backend/app/data/ev.py):
 *   Sharp price   source=auto -- Pinnacle's de-vigged price where it hangs
 *                 the line, the other books' consensus where it doesn't.
 *   Outliers      source=consensus -- always the consensus of the OTHER
 *                 books, sorted by how far the price sits from the pack.
 * In both, a price is only listed if it's +EV once the vig is removed: a
 * number far from the pack that's merely fair doesn't show up.
 */

type Mode = 'auto' | 'consensus';

interface PriceRow { book: string; over: number | null; under: number | null }

export interface EVRow {
  event_id: string;
  player: string;
  market: string;
  line: number | null;
  side: 'over' | 'under';
  book: string;
  price: number;
  implied_pct: number;
  fair_pct: number;
  fair_price: number | null;
  ev_pct: number;
  source: 'sharp' | 'consensus';
  consensus_books: number;
  sharp_ref: string | null;
  median_price: number | null;
  gap_pp: number | null;
  suspicious: boolean;
  prices: PriceRow[];
  price_since: string | null;
  commence_time: string | null;
  home_team: string | null;
  away_team: string | null;
  fetched_at: string | null;
  /** Other books that also clear the bar on this same bet, best first. */
  other_books: { book: string; price: number; ev_pct: number }[];
}

interface EVExplorerProps {
  fetcher: (params: Record<string, unknown>) => Promise<{ data: EVRow[] }>;
  title: string;
  /** Rendered under the heading -- the Betting pages' sport toggle. */
  toolbar?: ReactNode;
}

function ago(iso: string | null): string | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (isNaN(t)) return null;
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 60) return `${mins} min`;
  const h = Math.round(mins / 60);
  return h < 48 ? `${h}h` : `${Math.round(h / 24)}d`;
}

function kickoff(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
}

function sideLabel(r: EVRow): string {
  const s = r.side === 'over' ? 'Over' : 'Under';
  return r.line === null ? (r.side === 'over' ? 'Yes' : 'No') : `${s} ${r.line}`;
}

const selectStyle = (isMobile: boolean) => ({
  minHeight: 40, padding: '9px 12px', fontSize: 14, borderRadius: 4,
  border: `1px solid ${theme.border}`, background: theme.bgCard, color: theme.textPrimary,
  boxSizing: 'border-box' as const, width: isMobile ? '100%' : undefined,
});

export default function EVExplorer({ fetcher, title, toolbar }: EVExplorerProps) {
  const isMobile = useIsMobile();
  const [mode, setMode] = useState<Mode>('auto');
  const [minEdge, setMinEdge] = useState(2);
  const [minBooks, setMinBooks] = useState(2);
  const [market, setMarket] = useState('');
  const [rows, setRows] = useState<EVRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError('');
    fetcher({ source: mode, min_edge: minEdge, min_books: minBooks })
      .then((res) => setRows(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load.'))
      .finally(() => setLoading(false));
    // fetcher is a stable module-level export -- see MiddlesExplorer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, minEdge, minBooks]);

  const markets = useMemo(() => [...new Set(rows.map((r) => r.market))].sort(), [rows]);

  const shown = useMemo(() => {
    const r = rows.filter((x) => !market || x.market === market);
    if (mode === 'consensus') {
      return [...r].sort((a, b) => (b.gap_pp ?? -99) - (a.gap_pp ?? -99));
    }
    return r;
  }, [rows, market, mode]);

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 1200, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>{title}</h2>
      {toolbar}
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 14, lineHeight: 1.55 }}>
        Props where one sportsbook is paying more than the bet is worth. The fair price comes
        from the market itself with the vig removed — Pinnacle's line where it has one, otherwise
        the other books' consensus (the book being judged never counts toward its own fair
        price). A price is only listed if it's still <strong style={{ color: theme.accent }}>+EV</strong>{' '}
        after the vig comes out, so a number that just <em>looks</em> cheap doesn't make it.
      </div>

      <OddsDisclaimer fetchedAt={latestFetchedAt(shown)} compact={isMobile} />

      <SegmentedToggle
        value={mode}
        onChange={(m) => { setMode(m); setOpen(null); }}
        fullWidth={isMobile}
        options={[
          { value: 'auto', label: 'Sharp price' },
          { value: 'consensus', label: 'Outliers vs. consensus' },
        ]}
        style={{ marginBottom: 10 }}
      />

      <div style={{
        display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: 8, marginBottom: 16,
      }}>
        <select value={minEdge} onChange={(e) => setMinEdge(Number(e.target.value))} style={selectStyle(isMobile)}>
          {[1, 2, 3, 5].map((v) => <option key={v} value={v}>Min edge {v}%</option>)}
        </select>
        <select value={minBooks} onChange={(e) => setMinBooks(Number(e.target.value))} style={selectStyle(isMobile)}>
          <option value={2}>Consensus of 2+ books</option>
          <option value={3}>Consensus of 3+ books (sturdier)</option>
        </select>
        {markets.length > 0 && (
          <select value={market} onChange={(e) => setMarket(e.target.value)} style={selectStyle(isMobile)}>
            <option value="">All markets</option>
            {markets.map((m) => <option key={m} value={m}>{prettyMarket(m)}</option>)}
          </select>
        )}
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{
          background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`,
          borderRadius: 4, padding: 16, color: theme.dataRed,
        }}>{error}</div>
      )}

      {!loading && !error && shown.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 44, fontSize: 15 }}>
          Nothing clears the bar right now. Books mostly agree with each other, so an empty
          list is normal — try a lower minimum edge, or check back after lines move.
        </div>
      )}

      {!loading && !error && shown.length > 0 && (
        <div style={{
          display: 'grid', gap: 10,
          gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(340px, 1fr))',
        }}>
          {shown.map((r) => {
            const id = `${r.event_id}|${r.player}|${r.market}|${r.line}|${r.side}|${r.book}`;
            const expanded = open === id;
            const since = ago(r.price_since);
            return (
              <div
                key={id}
                onClick={() => setOpen(expanded ? null : id)}
                style={{
                  background: theme.bgCard, borderRadius: 8, padding: 13, cursor: 'pointer',
                  border: `1px solid ${r.suspicious ? theme.warningText : theme.border}`,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: theme.textPrimary }}>{r.player}</div>
                    <div style={{ fontSize: 12, color: theme.textSecondary }}>
                      {prettyMarket(r.market)} · <strong style={{ color: theme.textPrimary }}>{sideLabel(r)}</strong>
                    </div>
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: theme.accent, fontVariantNumeric: 'tabular-nums' }}>
                    +{r.ev_pct.toFixed(1)}%
                  </div>
                </div>

                <div style={{
                  display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginTop: 8,
                  color: theme.textSecondary, fontVariantNumeric: 'tabular-nums', gap: 8, flexWrap: 'wrap',
                }}>
                  <span>
                    {prettyBook(r.book)} pays{' '}
                    <strong style={{ color: theme.textPrimary }}>{formatOdds(r.price)}</strong>
                  </span>
                  <span>
                    Fair {r.fair_price !== null ? formatOdds(r.fair_price) : '—'} ({r.fair_pct.toFixed(1)}%)
                  </span>
                </div>

                {/* Green = what the book's price implies; white tick = the fair
                    chance. The gap between them is the edge. */}
                <div style={{ height: 6, background: theme.border, borderRadius: 3, position: 'relative', marginTop: 7 }}>
                  <div style={{
                    position: 'absolute', left: 0, top: 0, bottom: 0, borderRadius: 3,
                    width: `${Math.min(100, r.implied_pct)}%`, background: theme.accent,
                  }} />
                  <div style={{
                    position: 'absolute', top: -3, bottom: -3, width: 2, background: theme.textPrimary,
                    left: `${Math.min(99.5, r.fair_pct)}%`,
                  }} />
                </div>

                <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 7, lineHeight: 1.5 }}>
                  {r.source === 'sharp'
                    ? <>Fair from {r.sharp_ref ? r.sharp_ref.replace(/^pinnacle/, 'Pinnacle') : 'Pinnacle'}</>
                    : <>Fair from consensus of {r.consensus_books} other books</>}
                  {r.median_price !== null && <> · median {formatOdds(r.median_price)}</>}
                  {r.gap_pp !== null && r.gap_pp > 0 && <> · {r.gap_pp.toFixed(1)} pts off the pack</>}
                  {since && <> · price up {since}</>}
                  {r.away_team && <><br />{r.away_team} @ {r.home_team} · {kickoff(r.commence_time)}</>}
                </div>

                {r.other_books.length > 0 && (
                  <div style={{ fontSize: 11.5, color: theme.textSecondary, marginTop: 6 }}>
                    Also +EV at{' '}
                    {r.other_books.map((o, i) => (
                      <span key={o.book}>
                        {i > 0 && ', '}
                        {prettyBook(o.book)} {formatOdds(o.price)} (+{o.ev_pct.toFixed(1)}%)
                      </span>
                    ))}
                  </div>
                )}

                {r.suspicious && (
                  <div style={{ fontSize: 11.5, color: theme.warningText, marginTop: 6 }}>
                    An edge this big is usually a stale or mis-posted price, or news the other books
                    reacted to first. Check the book and the injury report before betting.
                  </div>
                )}

                {expanded && (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, marginTop: 10 }}>
                    <thead>
                      <tr style={{ color: theme.textMuted }}>
                        {['Book', 'Over', 'Under'].map((h, i) => (
                          <th key={h} style={{
                            textAlign: i ? 'right' : 'left', fontWeight: 500, fontSize: 10.5,
                            textTransform: 'uppercase', padding: '4px 4px',
                            borderBottom: `1px solid ${theme.borderStrong}`,
                          }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {r.prices.map((p) => {
                        const isThis = p.book === r.book;
                        return (
                          <tr key={p.book} style={{ background: isThis ? 'rgba(29,158,117,0.12)' : undefined }}>
                            <td style={{ padding: '5px 4px', color: theme.textPrimary }}>
                              {p.book === 'pinnacle' ? 'Pinnacle (reference)' : prettyBook(p.book)}
                            </td>
                            {(['over', 'under'] as const).map((s) => (
                              <td key={s} style={{
                                padding: '5px 4px', textAlign: 'right', fontVariantNumeric: 'tabular-nums',
                                color: isThis && s === r.side ? theme.accent : theme.textSecondary,
                                fontWeight: isThis && s === r.side ? 700 : 400,
                              }}>
                                {p[s] !== null ? formatOdds(p[s] as number) : '—'}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
                <div style={{ fontSize: 10.5, color: theme.textMuted, marginTop: 6 }}>
                  {expanded ? 'Tap to hide prices' : 'Tap for every book\'s price'}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!loading && shown.length > 0 && (
        <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 14, lineHeight: 1.6 }}>
          <strong>EV</strong> is the average profit per $100 if the fair chance is right — a +5% bet
          still loses often, and only pays off across many bets. Most edges here close fast: the
          soft book usually moves toward the pack. Pick'em apps aren't included, since their prices
          aren't single bets you can place.
        </div>
      )}
    </div>
  );
}
