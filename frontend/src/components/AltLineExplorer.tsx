import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import LoadingSpinner from './LoadingSpinner';
import SegmentedToggle from './SegmentedToggle';
import ScrollTable from './ScrollTable';
import OddsDisclaimer, { latestFetchedAt } from './OddsDisclaimer';
import { formatOdds, prettyBook, prettyMarket } from './PropsExplorer';
import useIsMobile from '../hooks/useIsMobile';
import { theme } from '../theme';

/**
 * Alt-Line Value -- shared by the MLB and NFL pages. One card per player
 * ladder (every priced rung of one market), with the rung that offers the
 * most value highlighted. Scoring lives in backend/app/data/alt_value.py;
 * this component only displays it.
 */

interface Rung {
  line: number;
  best_price: number;
  best_book: string;
  book_count: number;
  implied_pct: number;
  season_pct: number;
  season_sample: string;
  recent_pct: number;
  recent_sample: string;
  model_pct: number;
  edge_pp: number;
  ev_pct: number;
  flagged: boolean;
  is_best: boolean;
}

interface Ladder {
  player: string;
  team: string | null;
  opponent: string | null;
  market: string;
  commence_time: string | null;
  fetched_at: string | null;
  games: number;
  enough_games: boolean;
  best_line: number | null;
  best_ev_pct: number | null;
  rungs: Rung[];
}

interface AltLineExplorerProps {
  fetcher: (params: Record<string, unknown>) => Promise<{ data: Ladder[] }>;
  title: string;
  /** Rendered under the heading -- the Betting pages' sport toggle. */
  toolbar?: ReactNode;
}

type Scope = 'flagged' | 'all';

/** Hit-rate-sheet market keys carry a batter_/player_ prefix the props
 *  labels don't -- strip it so "batter_hits" reads as "hits". */
function marketLabel(m: string): string {
  return prettyMarket(m.replace(/^(batter_|player_)/, ''));
}

const selectStyle = (isMobile: boolean) => ({
  minHeight: 40, padding: '9px 12px', fontSize: 14, borderRadius: 4,
  border: `1px solid ${theme.border}`, background: theme.bgCard, color: theme.textPrimary,
  boxSizing: 'border-box' as const, width: isMobile ? '100%' : undefined,
});

const th = (right: boolean) => ({
  padding: '6px 8px', textAlign: (right ? 'right' : 'left') as 'right' | 'left',
  fontSize: 10.5, fontWeight: 500, color: theme.textMuted, textTransform: 'uppercase' as const,
  letterSpacing: '0.03em', borderBottom: `1px solid ${theme.borderStrong}`, whiteSpace: 'nowrap' as const,
});

export default function AltLineExplorer({ fetcher, title, toolbar }: AltLineExplorerProps) {
  const isMobile = useIsMobile();
  const [scope, setScope] = useState<Scope>('flagged');
  const [minEv, setMinEv] = useState(3);
  const [market, setMarket] = useState('');
  const [rows, setRows] = useState<Ladder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    fetcher({ min_ev: minEv, flagged_only: scope === 'flagged' })
      .then((res) => setRows(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load.'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minEv, scope]);

  const markets = useMemo(() => [...new Set(rows.map((r) => r.market))].sort(), [rows]);
  const shown = useMemo(() => rows.filter((r) => !market || r.market === market), [rows, market]);

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 1200, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>{title}</h2>
      {toolbar}
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 14, lineHeight: 1.55 }}>
        Every rung of a player's alt ladder, with how often he's cleared it compared to what the
        best available price implies. The highlighted rung is the best value. Hit rates are
        blended with the market's own price so a short hot streak can't make a long shot look
        like a lock, and very long odds are never flagged.
      </div>

      <OddsDisclaimer fetchedAt={latestFetchedAt(shown)} compact={isMobile} />

      <SegmentedToggle
        value={scope}
        onChange={setScope}
        fullWidth={isMobile}
        options={[
          { value: 'flagged', label: 'Value found' },
          { value: 'all', label: 'All ladders' },
        ]}
        style={{ marginBottom: 10 }}
      />

      <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: 8, marginBottom: 16 }}>
        <select value={minEv} onChange={(e) => setMinEv(Number(e.target.value))} style={selectStyle(isMobile)}>
          {[3, 5, 10].map((v) => <option key={v} value={v}>Min EV {v}%</option>)}
        </select>
        {markets.length > 0 && (
          <select value={market} onChange={(e) => setMarket(e.target.value)} style={selectStyle(isMobile)}>
            <option value="">All markets</option>
            {markets.map((m) => <option key={m} value={m}>{marketLabel(m)}</option>)}
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
          No ladder clears the bar right now. Early in a season there isn't enough game history
          to flag anything yet — switch to "All ladders" to browse them.
        </div>
      )}

      {!loading && !error && shown.map((lad) => (
        <div key={`${lad.player}|${lad.market}`} style={{
          background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8,
          padding: 13, marginBottom: 12,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: theme.textPrimary }}>
                {lad.player}{' '}
                <span style={{ fontWeight: 400, color: theme.textSecondary, fontSize: 12.5 }}>
                  {[lad.team, lad.opponent].filter(Boolean).join(' ')}
                </span>
              </div>
              <div style={{ fontSize: 12, color: theme.textSecondary }}>
                {marketLabel(lad.market)} · {lad.games} games this season
                {!lad.enough_games && <span style={{ color: theme.warningText }}> · too few to flag</span>}
              </div>
            </div>
            {lad.best_line !== null && (
              <span style={{
                fontSize: 11, fontWeight: 700, color: theme.accent, border: `1px solid ${theme.accent}`,
                borderRadius: 999, padding: '2px 8px', whiteSpace: 'nowrap',
              }}>
                Best: Over {lad.best_line}
              </span>
            )}
          </div>

          <ScrollTable hint={isMobile ? 'swipe for more →' : null} style={{ marginTop: 10 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={th(false)}>Rung</th>
                  <th style={th(true)}>Best price</th>
                  <th style={th(true)}>Implied</th>
                  <th style={th(true)}>Our chance</th>
                  <th style={th(true)}>EV</th>
                  <th style={th(true)}>Season</th>
                  <th style={th(true)}>Last 10</th>
                </tr>
              </thead>
              <tbody>
                {lad.rungs.map((r) => {
                  const muted = !r.flagged && !r.is_best;
                  const cell = {
                    padding: '8px 8px', textAlign: 'right' as const, fontVariantNumeric: 'tabular-nums' as const,
                    borderBottom: `1px solid ${theme.border}`, whiteSpace: 'nowrap' as const,
                    color: muted ? theme.textSecondary : theme.textPrimary,
                  };
                  return (
                    <tr key={r.line} style={{ background: r.is_best ? 'rgba(29,158,117,0.12)' : undefined }}>
                      <td style={{ ...cell, textAlign: 'left', fontWeight: r.is_best ? 700 : 400 }}>O {r.line}</td>
                      <td style={cell}>
                        {formatOdds(r.best_price)}
                        <div style={{ fontSize: 10.5, color: theme.textMuted }}>{prettyBook(r.best_book)}</div>
                      </td>
                      <td style={cell}>{r.implied_pct.toFixed(1)}%</td>
                      <td style={cell}>{r.model_pct.toFixed(1)}%</td>
                      <td style={{
                        ...cell, fontWeight: 700,
                        color: r.ev_pct >= 0 ? (muted ? theme.textSecondary : theme.accent) : theme.dataRed,
                      }}>
                        {r.ev_pct >= 0 ? '+' : ''}{r.ev_pct.toFixed(1)}%
                      </td>
                      <td style={cell}>
                        {r.season_pct.toFixed(0)}%
                        <div style={{ fontSize: 10.5, color: theme.textMuted }}>{r.season_sample}</div>
                      </td>
                      <td style={cell}>
                        {r.recent_pct.toFixed(0)}%
                        <div style={{ fontSize: 10.5, color: theme.textMuted }}>{r.recent_sample}</div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </ScrollTable>
        </div>
      ))}

      {!loading && shown.length > 0 && (
        <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 6, lineHeight: 1.6 }}>
          <strong>Our chance</strong> blends the season and last-10 hit rates, then pulls that toward
          the market's own price — harder for rare outcomes — so small samples can't carry a long shot.
          Hit rates don't know about today's matchup (the opposing pitcher, a defense, a role change);
          the price does. Use this to find the rung worth a closer look, then check the matchup.
          Rungs above +600 are shown but never flagged. Pick'em apps aren't counted as a best price.
        </div>
      )}
    </div>
  );
}
