import { useCallback, useEffect, useState } from 'react';
import LoadingSpinner from '../../components/LoadingSpinner';
import { formatOdds, prettyBook, prettyMarket } from '../../components/PropsExplorer';
import { deleteBet, getMyBets, getReportCard, setBetResult } from '../../api/betting';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

/**
 * My Bets -- every bet logged from a "Bet this" sheet, with the closing line
 * value (CLV) of each and the summary that tells skill from luck. Also the
 * site-wide report card: how the EV Finder's own flagged plays have done
 * against the close. Grading happens on the server when this page loads.
 */

interface BetRow {
  id: string;
  sport: string;
  player: string;
  market: string;
  line: number | null;
  side: 'over' | 'under';
  book: string;
  price: number;
  stake: number | null;
  tool: string | null;
  verification: 'verified' | 'self_reported';
  commence_time: string | null;
  home_team: string | null;
  away_team: string | null;
  placed_at: string;
  close_price: number | null;
  close_fair_pct: number | null;
  clv_pct: number | null;
  result: 'pending' | 'win' | 'loss' | 'push' | 'void';
  result_source: string | null;
}

interface Summary {
  bets: number;
  settled: number;
  record: { win: number; loss: number; push: number };
  units: number;
  roi_pct: number | null;
  avg_clv_pct: number | null;
  beat_close_pct: number | null;
  clv_bets: number;
  verified_share_pct: number | null;
}

interface CardRow { label: string; graded: number; avg_clv_pct: number | null; beat_close_pct: number | null }
interface ReportCard { overall: CardRow; flagged: number; by: CardRow[] }

const RESULT_COLOR: Record<string, string> = {
  win: theme.accent, loss: theme.dataRed, push: theme.textSecondary, void: theme.textSecondary, pending: theme.textMuted,
};

function pct(v: number | null, signed = false): string {
  if (v === null || v === undefined) return '—';
  return `${signed && v > 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function started(b: BetRow): boolean {
  return !!b.commence_time && new Date(b.commence_time).getTime() <= Date.now();
}

function Tile({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: 12 }}>
      <div style={{ fontSize: 11, color: theme.textMuted }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: theme.textMuted }}>{sub}</div>}
    </div>
  );
}

export default function MyBets() {
  const isMobile = useIsMobile();
  const [bets, setBets] = useState<BetRow[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [card, setCard] = useState<ReportCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    return getMyBets()
      .then((res) => { setBets(res.data.bets); setSummary(res.data.summary); })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load.'));
  }, []);

  useEffect(() => {
    Promise.all([load(), getReportCard().then((r) => setCard(r.data)).catch(() => setCard(null))])
      .finally(() => setLoading(false));
  }, [load]);

  const settle = (id: string, result: 'win' | 'loss' | 'push' | 'void') =>
    setBetResult(id, result).then(load).catch((err) => setError(err?.response?.data?.detail || 'Update failed.'));
  const remove = (id: string) =>
    deleteBet(id).then(load).catch((err) => setError(err?.response?.data?.detail || 'Delete failed.'));

  const s = summary;
  const verdict = s && s.avg_clv_pct !== null && s.roi_pct !== null
    ? (s.avg_clv_pct > 0 && s.roi_pct < 0
      ? "You're beating the close but down on results: most likely short-term variance, not a bad process."
      : s.avg_clv_pct > 0 ? "You're beating the close. That's the sign of a winning process."
        : "You're not beating the close yet. Results alone won't tell you much until the sample is large.")
    : null;

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 1000, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>My Bets</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 14, lineHeight: 1.55 }}>
        Every bet you log is checked against the closing line: the last price before the game
        started, with the vig removed. Beating it consistently (positive CLV) is the fastest sign
        your process works, win or lose. Log bets with the "Bet this" button on the EV Finder,
        Alt-Line Value and Today pages.
      </div>

      {loading && <LoadingSpinner />}
      {error && <div style={{ color: theme.dataRed, marginBottom: 12 }}>{error}</div>}

      {!loading && s && (
        <>
          <div style={{
            display: 'grid', gap: 10, marginBottom: 12,
            gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
          }}>
            <Tile label="Average CLV" value={pct(s.avg_clv_pct, true)} sub={`${s.clv_bets} bets graded`}
              color={s.avg_clv_pct === null ? undefined : s.avg_clv_pct >= 0 ? theme.accent : theme.dataRed} />
            <Tile label="Beat the close" value={pct(s.beat_close_pct)} />
            <Tile label="ROI" value={pct(s.roi_pct, true)} sub={`${s.units >= 0 ? '+' : ''}${s.units} units`}
              color={s.roi_pct === null ? undefined : s.roi_pct >= 0 ? theme.accent : theme.dataRed} />
            <Tile label="Record" value={`${s.record.win}-${s.record.loss}${s.record.push ? `-${s.record.push}` : ''}`}
              sub={`${s.bets} logged · ${s.verified_share_pct ?? 0}% verified`} />
          </div>
          {verdict && (
            <div style={{
              borderLeft: `3px solid ${theme.accent}`, background: theme.bgCard, padding: '8px 12px',
              fontSize: 13, color: theme.textSecondary, borderRadius: '0 8px 8px 0', marginBottom: 14,
            }}>{verdict}</div>
          )}
        </>
      )}

      {!loading && bets.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', margin: '30px 0' }}>
          No bets logged yet.
        </div>
      )}

      {bets.map((b) => {
        const side = b.line === null ? (b.side === 'over' ? 'Yes' : 'No') : `${b.side === 'over' ? 'Over' : 'Under'} ${b.line}`;
        const isStarted = started(b);
        return (
          <div key={b.id} style={{
            background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8,
            padding: 12, marginBottom: 8,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <div>
                <div style={{ fontWeight: 700, color: theme.textPrimary, fontSize: 14 }}>
                  {b.player} <span style={{ fontWeight: 400, color: theme.textSecondary }}>
                    {side} {prettyMarket(b.market)}</span>
                </div>
                <div style={{ fontSize: 12, color: theme.textSecondary }}>
                  {prettyBook(b.book)} {formatOdds(b.price)}
                  {b.stake ? ` · $${b.stake}` : ''}
                  {b.away_team ? ` · ${b.away_team} @ ${b.home_team}` : ''}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 700, color: RESULT_COLOR[b.result], textTransform: 'uppercase', fontSize: 12 }}>
                  {b.result}
                </div>
                <div style={{
                  fontSize: 10.5, marginTop: 2,
                  color: b.verification === 'verified' ? theme.accent : theme.textMuted,
                }}>
                  {b.verification === 'verified' ? 'Verified' : 'Self-reported'}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12, marginTop: 7, color: theme.textSecondary }}>
              <span>Close: {b.close_price !== null ? formatOdds(b.close_price) : '—'}
                {b.close_fair_pct !== null ? ` (fair ${b.close_fair_pct.toFixed(1)}%)` : ''}</span>
              <span>CLV: <strong style={{
                color: b.clv_pct === null ? theme.textMuted : b.clv_pct >= 0 ? theme.accent : theme.dataRed,
              }}>{pct(b.clv_pct, true)}</strong></span>
              {!isStarted && <span style={{ color: theme.textMuted }}>CLV appears after the game starts</span>}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              {!isStarted && (
                <button onClick={() => remove(b.id)} style={smallBtn}>Delete</button>
              )}
              {isStarted && b.result === 'pending' && (['win', 'loss', 'push', 'void'] as const).map((r) => (
                <button key={r} onClick={() => settle(b.id, r)} style={smallBtn}>Mark {r}</button>
              ))}
            </div>
          </div>
        );
      })}

      {!loading && card && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ color: theme.textPrimary, fontSize: 16, marginBottom: 4 }}>EV Finder report card</h3>
          <div style={{ fontSize: 12.5, color: theme.textSecondary, marginBottom: 10 }}>
            Every play the EV Finder flags is recorded at the price it first showed and graded against
            the close, whether or not anyone bet it. {card.flagged} plays logged so far.
          </div>
          {card.overall.graded === 0 ? (
            <div style={{ fontSize: 13, color: theme.textMuted }}>
              No plays graded yet; they're graded once their games start.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: theme.textMuted, fontSize: 11, textTransform: 'uppercase' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>Group</th>
                  <th style={{ textAlign: 'right', padding: 6 }}>Plays</th>
                  <th style={{ textAlign: 'right', padding: 6 }}>Avg CLV</th>
                  <th style={{ textAlign: 'right', padding: 6 }}>Beat close</th>
                </tr>
              </thead>
              <tbody>
                {[{ ...card.overall, label: 'All plays' }, ...card.by].map((r) => (
                  <tr key={r.label} style={{ borderTop: `1px solid ${theme.border}`, color: theme.textPrimary }}>
                    <td style={{ padding: 6 }}>{r.label}</td>
                    <td style={{ padding: 6, textAlign: 'right' }}>{r.graded}</td>
                    <td style={{ padding: 6, textAlign: 'right', color: (r.avg_clv_pct ?? 0) >= 0 ? theme.accent : theme.dataRed }}>
                      {pct(r.avg_clv_pct, true)}
                    </td>
                    <td style={{ padding: 6, textAlign: 'right' }}>{pct(r.beat_close_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

const smallBtn = {
  padding: '5px 10px', borderRadius: 6, border: `1px solid ${theme.border}`,
  background: theme.bgPage, color: theme.textSecondary, fontSize: 12, cursor: 'pointer',
};
