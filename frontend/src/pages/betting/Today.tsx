import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import LoadingSpinner from '../../components/LoadingSpinner';
import ChipRow from '../../components/ChipRow';
import BetSheet from '../../components/BetSheet';
import { getToday } from '../../api/betting';
import type { BetDraft } from '../../api/betting';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

/**
 * Today -- the strongest signals from every page in one ranked feed
 * (backend/app/data/today.py). Injury changes lead, since they're the most
 * time-sensitive; then +EV prices, Alt-Line value, weather, middles and hot
 * hitters. Each card links to the page it came from, and bettable ones
 * open the "Bet this" sheet.
 */

interface Item {
  id: string;
  type: 'injury' | 'ev' | 'alt' | 'weather' | 'middle' | 'hot';
  sport: 'nfl' | 'mlb' | 'nba';
  title: string;
  subtitle: string;
  notes: string[];
  badge: string;
  time: string | null;
  link: string | null;
  bet: BetDraft | null;
  /** Bettable items only: price tier and a suggested stake (quarter-Kelly, capped). */
  risk?: { tier: 'standard' | 'longshot'; stake_pct: number };
}

const TYPE_STYLE: Record<Item['type'], { color: string; label: string }> = {
  injury: { color: theme.dataRed, label: 'Injury' },
  ev: { color: theme.accent, label: '+EV' },
  alt: { color: theme.accent, label: 'Alt value' },
  weather: { color: theme.warningText, label: 'Weather' },
  middle: { color: theme.dataBlue, label: 'Middle' },
  hot: { color: theme.dataBlue, label: 'Hot' },
};

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'nfl', label: 'NFL' },
  { key: 'mlb', label: 'MLB' },
  { key: 'nba', label: 'NBA' },
  { key: 'injury', label: 'Injuries' },
  { key: 'edges', label: 'Edges' },
  { key: 'longshot', label: 'Long shots' },
];

function ago(iso: string | null): string | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (isNaN(t)) return null;
  const mins = Math.round((Date.now() - t) / 60000);
  if (mins < 0) return null;
  if (mins < 60) return `${mins}m ago`;
  const h = Math.round(mins / 60);
  return h < 48 ? `${h}h ago` : null;
}

export default function Today() {
  const isMobile = useIsMobile();
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [betting, setBetting] = useState<BetDraft | null>(null);

  useEffect(() => {
    getToday()
      .then((res) => setItems(res.data.items))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load.'))
      .finally(() => setLoading(false));
  }, []);

  const shown = useMemo(() => items.filter((i) => {
    if (filter === 'all') return true;
    if (filter === 'injury') return i.type === 'injury';
    if (filter === 'edges') return i.type === 'ev' || i.type === 'alt' || i.type === 'middle';
    if (filter === 'longshot') return i.risk?.tier === 'longshot';
    return i.sport === filter;
  }), [items, filter]);

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 900, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>Edge Board</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 14, lineHeight: 1.55 }}>
        Every edge on today's board in one ranked list: mispriced odds, alt-line value, middles, and
        the injury news behind them. Bets priced from -250 to +250 follow the normal rules. Long shots (+251 to +600)
        have to pass extra checks, are limited to two per sport, and are labeled. Each bet shows a
        suggested stake as a share of your bankroll: long shots lose often even when they're good
        bets, so they're sized smaller.
      </div>

      <ChipRow chips={FILTERS} value={filter} onChange={setFilter} style={{ marginBottom: 14 }} />

      {loading && <LoadingSpinner />}
      {error && <div style={{ color: theme.dataRed }}>{error}</div>}
      {!loading && !error && shown.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40 }}>
          Nothing here right now. Check back closer to game time.
        </div>
      )}

      {shown.map((i) => {
        const st = TYPE_STYLE[i.type];
        const when = ago(i.time);
        return (
          <div key={i.id} style={{
            background: theme.bgCard, borderRadius: 8, padding: 13, marginBottom: 10,
            border: `1px solid ${theme.border}`, borderLeft: `3px solid ${st.color}`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
              <span style={{
                fontSize: 10.5, fontWeight: 700, color: st.color, border: `1px solid ${st.color}`,
                borderRadius: 999, padding: '1px 8px', textTransform: 'uppercase', letterSpacing: '0.03em',
              }}>
                {i.type === 'injury' || i.type === 'ev' || i.type === 'alt' ? i.badge : st.label}
              </span>
              <span style={{ fontSize: 11, color: theme.textMuted }}>
                {i.sport.toUpperCase()}{when ? ` · ${when}` : ''}
              </span>
            </div>
            <div style={{ marginTop: 7, fontWeight: 600, color: theme.textPrimary, fontSize: 14 }}>{i.title}</div>
            {i.subtitle && <div style={{ fontSize: 12.5, color: theme.textSecondary, marginTop: 2 }}>{i.subtitle}</div>}
            {i.risk && (
              <div style={{ fontSize: 12, marginTop: 5, color: theme.textSecondary }}>
                {i.risk.tier === 'longshot' && (
                  <span style={{
                    color: theme.warningText, border: `1px solid ${theme.warningText}`, borderRadius: 999,
                    padding: '0 7px', fontSize: 10.5, fontWeight: 700, marginRight: 6,
                  }}>LONG SHOT</span>
                )}
                Suggested stake: <strong style={{ color: theme.textPrimary }}>{i.risk.stake_pct}% of bankroll</strong>
              </div>
            )}
            {i.notes.length > 0 && (
              <ul style={{ margin: '7px 0 0', paddingLeft: 18, fontSize: 12.5, color: theme.textSecondary, lineHeight: 1.55 }}>
                {i.notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            )}
            {(i.link || i.bet) && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 9 }}>
                {i.link ? (
                  <Link to={i.link} style={{ fontSize: 12.5, color: theme.accent, textDecoration: 'none' }}>Open page →</Link>
                ) : <span />}
                {i.bet && (
                  <button
                    onClick={() => setBetting(i.bet)}
                    style={{
                      padding: '6px 12px', borderRadius: 6, border: `1px solid ${theme.accent}`,
                      background: 'transparent', color: theme.accent, fontWeight: 700, fontSize: 12.5, cursor: 'pointer',
                    }}
                  >
                    Bet this
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}

      <BetSheet key={betting ? JSON.stringify(betting) : 'none'} bet={betting} onClose={() => setBetting(null)} />
    </div>
  );
}
