import { useEffect, useMemo, useState } from 'react';
import { getNBAGapBets } from '../../api/nba';
import LoadingSpinner from '../../components/LoadingSpinner';
import SegmentedToggle from '../../components/SegmentedToggle';
import OddsDisclaimer, { clockLabel } from '../../components/OddsDisclaimer';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

/**
 * NBA Gap Bets -- anti-middles. An Under at one book and an Over one point
 * higher at another, both plus money: exactly one leg cashes on every result
 * except the gap, where both lose. Each pair is priced against that player's
 * own last 30 games (app/data/nba_gaps.py), because whether this is a good
 * bet comes down entirely to how often he lands on that number -- ~6% for
 * points, ~23% for threes.
 */

interface GapRow {
  player: string;
  team: string | null;
  market: string;
  market_label: string;
  game: string;
  commence_time: string | null;
  under_book: string; under_line: number; under_price: number;
  over_book: string; over_line: number; over_price: number;
  gap: string;
  gap_width: number;
  stake_over_pct: number;
  win_pct: number;
  breakeven_pct: number;
  games: number;
  avg: number | null;
  landing_pct: number | null;
  ev_pct: number | null;
  dfs_leg: string;
  fetched_at: string | null;
}

interface GapResponse {
  lines_as_of: string | null;
  oldest_line: string | null;
  lookback: number;
  rows: GapRow[];
}

function odds(n: number): string {
  return n > 0 ? `+${n.toFixed(0)}` : n.toFixed(0);
}

const BOOK_NAMES: Record<string, string> = {
  betmgm: 'BetMGM', draftkings: 'DraftKings', fanduel: 'FanDuel', fanatics: 'Fanatics',
  espnbet: 'ESPN BET', prizepicks: 'PrizePicks', underdog: 'Underdog', pick6: 'Pick6',
  dabble_us_dfs: 'Dabble',
};

function book(b: string): string {
  return BOOK_NAMES[b] || String(b || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function tipTime(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '' : d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function Leg({ side, line, price, bookName }: { side: string; line: number; price: number; bookName: string }) {
  return (
    <div style={{ flex: 1, minWidth: 0, background: theme.bgPage, border: `1px solid ${theme.border}`, borderRadius: 6, padding: '8px 10px' }}>
      <div style={{ fontSize: 11, color: theme.textMuted }}>{book(bookName)}</div>
      <div style={{ fontSize: 15, fontWeight: 700, color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>
        {side} {line} <span style={{ color: theme.accent }}>{odds(price)}</span>
      </div>
    </div>
  );
}

function GapCard({ r, lookback }: { r: GapRow; lookback: number }) {
  const underStake = 100 - r.stake_over_pct;
  const priced = r.landing_pct != null && r.ev_pct != null;
  // Blue when the history says the gap is rarer than the break-even needs,
  // amber when it's close or worse -- no green/red pairing, per the app's
  // colour rule.
  const evColor = !priced ? theme.textSecondary : (r.ev_pct as number) > 0 ? theme.dataBlue : theme.warningText;
  return (
    <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: theme.textPrimary }}>
            {r.player}{r.team ? <span style={{ color: theme.textMuted, fontWeight: 500 }}> · {r.team}</span> : null}
          </div>
          <div style={{ fontSize: 12, color: theme.textSecondary }}>
            {r.market_label}{r.game ? ` · ${r.game}` : ''}{r.commence_time ? ` · ${tipTime(r.commence_time)}` : ''}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 11, color: theme.textMuted }}>Est. return</div>
          <div style={{ fontSize: 18, fontWeight: 800, color: evColor, fontVariantNumeric: 'tabular-nums' }}>
            {priced ? `${(r.ev_pct as number) > 0 ? '+' : ''}${(r.ev_pct as number).toFixed(1)}%` : '—'}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <Leg side="Under" line={r.under_line} price={r.under_price} bookName={r.under_book} />
        <Leg side="Over" line={r.over_line} price={r.over_price} bookName={r.over_book} />
      </div>

      <div style={{ fontSize: 13, color: theme.textSecondary, lineHeight: 1.55 }}>
        Loses only if he finishes on <b style={{ color: theme.warningText }}>exactly {r.gap}</b>.
        {' '}Per $100: ${underStake.toFixed(0)} on the Under, ${r.stake_over_pct.toFixed(0)} on the Over
        → <b style={{ color: theme.textPrimary }}>+${r.win_pct.toFixed(2)}</b> on any other result,
        −$100 on {r.gap}.
      </div>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 10, fontSize: 12 }}>
        <span style={{ color: theme.textSecondary }}>
          Landed on {r.gap}:{' '}
          <b style={{ color: theme.textPrimary }}>{r.landing_pct != null ? `${r.landing_pct}%` : '—'}</b>
          {r.games > 0 && <span style={{ color: theme.textMuted }}> of last {Math.min(r.games, lookback)} games</span>}
          {r.landing_pct == null && <span style={{ color: theme.textMuted }}> (not enough games)</span>}
        </span>
        <span style={{ color: theme.textSecondary }}>
          Break-even: <b style={{ color: theme.textPrimary }}>under {r.breakeven_pct}%</b>
        </span>
        {r.avg != null && (
          <span style={{ color: theme.textSecondary }}>
            Average: <b style={{ color: theme.textPrimary }}>{r.avg}</b>
          </span>
        )}
      </div>

      <div style={{ marginTop: 8, fontSize: 11, color: theme.textMuted }}>
        Lines as of {clockLabel(r.fetched_at) || 'unknown'}
        {r.dfs_leg && <span style={{ color: theme.warningText }}> · includes a pick'em app leg ({r.dfs_leg}) — may not be placeable alone</span>}
      </div>
    </div>
  );
}

export default function NBAGapBets() {
  const [data, setData] = useState<GapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showAll, setShowAll] = useState<'positive' | 'all'>('positive');
  const [market, setMarket] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    setLoading(true);
    setError('');
    getNBAGapBets({ include_negative: showAll === 'all' })
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load gap bets.'))
      .finally(() => setLoading(false));
  }, [showAll]);

  const markets = useMemo(() => {
    const m = new Map<string, string>();
    (data?.rows || []).forEach((r) => m.set(r.market, r.market_label));
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [data]);

  const rows = useMemo(
    () => (data?.rows || []).filter((r) => !market || r.market === market),
    [data, market],
  );

  return (
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 900, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NBA Gap Bets</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 14, lineHeight: 1.55 }}>
        Two books disagree on a player's line by a point, and both sides are plus money: an
        Under at the lower number and an Over at the higher one. One of them wins on every result
        except the number in between, where both lose. That makes it a small, steady win — so
        it only pays if the player rarely lands on that exact number. Each pair is priced
        against the player's own last {data?.lookback ?? 30} games.
      </div>

      <OddsDisclaimer fetchedAt={data?.lines_as_of ?? null} compact={isMobile} />
      {data?.oldest_line && data.lines_as_of && data.oldest_line !== data.lines_as_of && (
        <div style={{ fontSize: 12, color: theme.warningText, marginTop: -6, marginBottom: 14 }}>
          Some pairs below are older — the oldest line shown is from {clockLabel(data.oldest_line)}. Each
          card shows its own time; the older a line, the more likely it has moved or been pulled.
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
        <SegmentedToggle
          value={showAll}
          onChange={setShowAll}
          options={[
            { value: 'positive', label: 'Positive return' },
            { value: 'all', label: 'All pairs' },
          ]}
        />
        {markets.length > 1 && (
          <select
            value={market}
            onChange={(e) => setMarket(e.target.value)}
            style={{ minHeight: 36, padding: '6px 10px', fontSize: 13, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgCard, color: theme.textPrimary }}
          >
            <option value="">All markets</option>
            {markets.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
        )}
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {!loading && !error && rows.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40, fontSize: 15, lineHeight: 1.6 }}>
          {showAll === 'positive'
            ? <>No gap bets with a positive estimated return right now. Switch to <b>All pairs</b> to see the rest, or check back as lines move.</>
            : <>No gap bets on the board right now. They show up when two books are a point apart on a player — usually when one hasn't updated yet.</>}
        </div>
      )}

      {!loading && !error && rows.length > 0 && (
        <div style={{ display: 'grid', gap: 12 }}>
          {rows.map((r, i) => <GapCard key={`${r.player}-${r.market}-${r.under_book}-${r.over_book}-${i}`} r={r} lookback={data?.lookback ?? 30} />)}
        </div>
      )}

      <div style={{ marginTop: 22, fontSize: 12, color: theme.textMuted, lineHeight: 1.6 }}>
        The landing rate is how often it happened, not a prediction — 30 games is a small sample,
        and a role or minutes change makes the past a worse guide. Estimated return assumes the
        stake split shown, so either winning leg pays the same. Games that have started are left out.
      </div>
    </div>
  );
}
