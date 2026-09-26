import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import BottomSheet from './BottomSheet';
import LoadingSpinner from './LoadingSpinner';
import { formatOdds, prettyBook, prettyMarket } from './PropsExplorer';
import { getQuote, logBet } from '../api/betting';
import type { BetDraft, Quote } from '../api/betting';
import { theme } from '../theme';

/**
 * "Bet this" sheet, shared by the EV Finder, Alt-Line Value and Today.
 *
 * 1. Checks the price that's up right now (the backend refreshes that one
 *    market live, cached for a few minutes) -- so the user sees whether the
 *    edge is still there before going to the book.
 * 2. Offers the book's bet-slip link when the book provides one.
 * 3. Logs the bet at the price the user actually got. The server stamps the
 *    time and marks it "verified" when that price matches what we saw.
 */

function sideText(b: BetDraft): string {
  if (b.line === null || b.line === undefined) return b.side === 'over' ? 'Yes' : 'No';
  return `${b.side === 'over' ? 'Over' : 'Under'} ${b.line}`;
}

function marketText(m: string): string {
  return prettyMarket(m.replace(/^(batter_|player_)/, ''));
}

const input = {
  width: '100%', minHeight: 42, padding: '9px 12px', fontSize: 15, borderRadius: 6,
  border: `1px solid ${theme.border}`, background: theme.bgPage, color: theme.textPrimary,
  boxSizing: 'border-box' as const,
};

export default function BetSheet({ bet, onClose }: { bet: BetDraft | null; onClose: () => void }) {
  // Parents key this component by the bet, so every new bet starts from
  // fresh state -- no resetting inside an effect.
  const [quote, setQuote] = useState<Quote | null>(null);
  const [loading, setLoading] = useState(!!bet);
  const [price, setPrice] = useState(bet ? String(bet.price) : '');
  const [stake, setStake] = useState('');
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState<null | { verification: string }>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!bet) return;
    getQuote(bet)
      .then((res) => {
        setQuote(res.data);
        const p = res.data.at_book?.price;
        if (p !== undefined && p !== null) setPrice(String(p));
      })
      .catch(() => setQuote(null))
      .finally(() => setLoading(false));
  }, [bet]);

  if (!bet) return null;

  const atBook = quote?.at_book;
  const best = quote?.best;
  const started = quote?.reason === 'started';
  const moved = atBook && atBook.price !== bet.price;
  const betterElsewhere = best && atBook && best.book !== atBook.book && best.price > atBook.price;

  const submit = () => {
    const p = parseInt(price, 10);
    if (!(p >= 100 || p <= -100)) { setError('Enter American odds, like -110 or +150.'); return; }
    setSaving(true); setError('');
    logBet({ ...bet, price: p, stake: stake ? Number(stake) : null, event_id: quote?.event_id ?? bet.event_id })
      .then((res) => setDone({ verification: res.data.verification }))
      .catch((err) => setError(err?.response?.data?.detail || 'Could not log this bet.'))
      .finally(() => setSaving(false));
  };

  return (
    <BottomSheet open={!!bet} onClose={onClose} title="Bet this">
      <div style={{ padding: '4px 16px 18px', color: theme.textSecondary, fontSize: 13.5, lineHeight: 1.5 }}>
        <div style={{ color: theme.textPrimary, fontWeight: 700, fontSize: 15 }}>{bet.player}</div>
        <div>{marketText(bet.market)} · <strong style={{ color: theme.textPrimary }}>{sideText(bet)}</strong></div>
        {quote?.away_team && <div style={{ fontSize: 12, color: theme.textMuted }}>{quote.away_team} @ {quote.home_team}</div>}

        {loading && <LoadingSpinner />}

        {!loading && started && (
          <div style={{ marginTop: 12, color: theme.warningText }}>
            This game has started, so it can't be logged. Bets are only recorded before the game begins.
          </div>
        )}

        {!loading && !started && (
          <>
            <div style={{
              marginTop: 12, background: theme.bgPage, borderRadius: 8, padding: '10px 12px',
              border: `1px solid ${theme.border}`,
            }}>
              {atBook ? (
                <>
                  <div>
                    {prettyBook(atBook.book)} now:{' '}
                    <strong style={{ color: theme.textPrimary, fontSize: 16 }}>{formatOdds(atBook.price)}</strong>
                    {moved && (
                      <span style={{ color: atBook.price > bet.price ? theme.accent : theme.dataRed, marginLeft: 6 }}>
                        (was {formatOdds(bet.price)})
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 11.5, color: theme.textMuted }}>
                    {quote?.source === 'live' ? 'Checked just now.' : 'From the last scheduled odds pull; confirm at the book.'}
                  </div>
                </>
              ) : (
                <div>
                  {prettyBook(bet.book)} no longer shows this line in our data. It may have moved or been pulled.
                </div>
              )}
              {betterElsewhere && best && (
                <div style={{ marginTop: 6 }}>
                  Better price: <strong style={{ color: theme.accent }}>{prettyBook(best.book)} {formatOdds(best.price)}</strong>
                </div>
              )}
            </div>

            {atBook?.link && (
              <a
                href={atBook.link} target="_blank" rel="noopener noreferrer"
                style={{
                  display: 'block', textAlign: 'center', marginTop: 12, padding: '11px 12px',
                  borderRadius: 6, background: theme.bgCardHover, color: theme.textPrimary,
                  border: `1px solid ${theme.borderStrong}`, textDecoration: 'none', fontWeight: 600,
                }}
              >
                Open {prettyBook(atBook.book)} bet slip ↗
              </a>
            )}

            {done ? (
              <div style={{ marginTop: 14, color: theme.accent, fontWeight: 600 }}>
                Logged{done.verification === 'verified' ? ' and verified' : ''}.{' '}
                <Link to="/betting/my-bets" onClick={onClose} style={{ color: theme.accent }}>See My Bets →</Link>
                {done.verification !== 'verified' && (
                  <div style={{ fontWeight: 400, color: theme.textMuted, fontSize: 12, marginTop: 4 }}>
                    Marked self-reported because the price differs from what we saw at that book.
                  </div>
                )}
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
                  <label style={{ flex: 1 }}>
                    <div style={{ fontSize: 11.5, marginBottom: 4 }}>Price you got</div>
                    <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="numeric" style={input} />
                  </label>
                  <label style={{ flex: 1 }}>
                    <div style={{ fontSize: 11.5, marginBottom: 4 }}>Stake (optional)</div>
                    <input value={stake} onChange={(e) => setStake(e.target.value)} inputMode="decimal"
                      placeholder="$" style={input} />
                  </label>
                </div>
                {error && <div style={{ color: theme.dataRed, marginTop: 8 }}>{error}</div>}
                <button
                  onClick={submit} disabled={saving}
                  style={{
                    width: '100%', marginTop: 14, padding: '12px', borderRadius: 6, border: 'none',
                    background: theme.accent, color: 'white', fontWeight: 700, fontSize: 15,
                    cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.7 : 1,
                  }}
                >
                  {saving ? 'Logging…' : 'Log this bet'}
                </button>
                <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 8 }}>
                  Logging tracks your record and closing line value on My Bets. Place the bet at the book
                  yourself; nothing is placed from here.
                </div>
              </>
            )}
          </>
        )}
      </div>
    </BottomSheet>
  );
}
