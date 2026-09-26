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
  // fresh state -- no resetting inside an effect. `draft` is the bet as the
  // user has adjusted it (side can be flipped: the Props and Hit Rate pages
  // open on the Over, but either side can be logged).
  const [draft, setDraft] = useState<BetDraft | null>(bet);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [loading, setLoading] = useState(!!bet);
  const [price, setPrice] = useState(bet ? String(bet.price) : '');
  const [stake, setStake] = useState('');
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState<null | { verification: string }>(null);
  const [error, setError] = useState('');

  const loadQuote = (b: BetDraft) => {
    getQuote(b)
      .then((res) => {
        setQuote(res.data);
        const at = res.data.at_book;
        const best = res.data.best;
        // The chosen book isn't hanging this side/line: move to the best one
        // that is, so the bet is logged at a book that actually offers it.
        if (!at && best) setDraft((d) => (d ? { ...d, book: best.book } : d));
        const p = at?.price ?? best?.price;
        if (p !== undefined && p !== null) setPrice(String(p));
      })
      .catch(() => setQuote(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (bet) loadQuote(bet);
  }, [bet]);

  const switchSide = (side: 'over' | 'under') => {
    if (!draft || draft.side === side) return;
    const next = { ...draft, side };
    setDraft(next); setQuote(null); setLoading(true); setError(''); setPrice('');
    loadQuote(next);
  };

  if (!bet || !draft) return null;

  // The offer at the book currently chosen (it can change: see loadQuote and
  // the "Use" button), falling back to the quote's own at-book match.
  const atBook = (quote?.offers ?? []).find((o) => o.book === draft?.book) ?? quote?.at_book ?? null;
  const best = quote?.best;
  const started = quote?.reason === 'started';
  const moved = atBook && draft.side === bet.side && atBook.price !== bet.price;
  const betterElsewhere = best && atBook && best.book !== atBook.book && best.price > atBook.price;

  const submit = () => {
    const p = parseInt(price, 10);
    if (!(p >= 100 || p <= -100)) { setError('Enter American odds, like -110 or +150.'); return; }
    setSaving(true); setError('');
    logBet({ ...draft, price: p, stake: stake ? Number(stake) : null, event_id: quote?.event_id ?? draft.event_id })
      .then((res) => setDone({ verification: res.data.verification }))
      .catch((err) => setError(err?.response?.data?.detail || 'Could not log this bet.'))
      .finally(() => setSaving(false));
  };

  return (
    <BottomSheet open={!!bet} onClose={onClose} title="Bet this">
      <div style={{ padding: '4px 16px 18px', color: theme.textSecondary, fontSize: 13.5, lineHeight: 1.5 }}>
        <div style={{ color: theme.textPrimary, fontWeight: 700, fontSize: 15 }}>{bet.player}</div>
        <div>{marketText(bet.market)} · <strong style={{ color: theme.textPrimary }}>{sideText(draft)}</strong></div>
        {quote?.away_team && <div style={{ fontSize: 12, color: theme.textMuted }}>{quote.away_team} @ {quote.home_team}</div>}

        {!done && (
          <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
            {(['over', 'under'] as const).map((sd) => (
              <button
                key={sd}
                onClick={() => switchSide(sd)}
                style={{
                  flex: 1, padding: '7px 10px', borderRadius: 6, fontSize: 13, fontWeight: 700, cursor: 'pointer',
                  border: `1px solid ${draft.side === sd ? theme.accent : theme.border}`,
                  background: draft.side === sd ? theme.accent : theme.bgPage,
                  color: draft.side === sd ? 'white' : theme.textSecondary,
                }}
              >
                {sideText({ ...draft, side: sd })}
              </button>
            ))}
          </div>
        )}

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
                  {best
                    ? <>{prettyBook(draft.book)} isn't showing this side right now; best available below.</>
                    : <>No book is showing this line right now. It may have moved or been pulled.</>}
                </div>
              )}
              {betterElsewhere && best && (
                <div style={{ marginTop: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <span>Better price: <strong style={{ color: theme.accent }}>{prettyBook(best.book)} {formatOdds(best.price)}</strong></span>
                  <button
                    onClick={() => {
                      setDraft({ ...draft, book: best.book, price: best.price });
                      setQuote({ ...quote!, at_book: best });
                      setPrice(String(best.price));
                    }}
                    style={{
                      padding: '4px 10px', borderRadius: 6, border: `1px solid ${theme.accent}`,
                      background: 'transparent', color: theme.accent, fontSize: 12, fontWeight: 700, cursor: 'pointer',
                    }}
                  >
                    Use {prettyBook(best.book)}
                  </button>
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
