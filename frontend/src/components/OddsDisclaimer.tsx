import { theme } from '../theme';

/** How stale the odds are, stated plainly, plus the attribution The Odds API's
 *  terms ask for.
 *
 *  This is not decoration. Every number on these pages is a snapshot of a
 *  price that a book can move or pull at any moment, and the gap between "what
 *  we fetched" and "what you can actually bet" is the entire risk a user
 *  carries. Saying so, with the timestamp attached, is the difference between
 *  showing data and implying a promise.
 *
 *  `fetchedAt` should be the max fetched_at across the rows actually on
 *  screen -- not the file's write time, which on a tiered refresh can be much
 *  newer than the particular game a user is looking at.
 */

function agoLabel(iso: string | null): { text: string; stale: boolean } {
  if (!iso) return { text: 'unknown', stale: true };
  const then = new Date(iso).getTime();
  if (isNaN(then)) return { text: 'unknown', stale: true };

  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  const stale = mins >= 120;
  if (mins < 1) return { text: 'just now', stale };
  if (mins < 60) return { text: `${mins} min ago`, stale };
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return { text: `${hrs} hour${hrs === 1 ? '' : 's'} ago`, stale };
  const days = Math.round(hrs / 24);
  return { text: `${days} day${days === 1 ? '' : 's'} ago`, stale: true };
}

export default function OddsDisclaimer({
  fetchedAt,
  compact = false,
}: {
  fetchedAt: string | null;
  compact?: boolean;
}) {
  const { text, stale } = agoLabel(fetchedAt);
  // Amber once the prices are old enough that treating them as live would be
  // a mistake, rather than a uniform grey note people stop reading.
  const accent = stale ? '#c08422' : theme.border;

  return (
    <div
      style={{
        border: `1px solid ${accent}`,
        borderLeft: `3px solid ${accent}`,
        borderRadius: 6,
        background: theme.bgCard,
        padding: compact ? '8px 11px' : '10px 13px',
        marginBottom: 14,
        fontSize: compact ? 11.5 : 12,
        color: theme.textSecondary,
        lineHeight: 1.5,
      }}
    >
      <div style={{ color: theme.textPrimary, fontWeight: 600, marginBottom: 3 }}>
        Odds last checked{' '}
        <span style={{ color: stale ? '#c08422' : theme.accent }}>{text}</span>
      </div>
      <div>
        Lines move constantly and books pull them without notice. These prices are a
        snapshot from when they were last queried. What you see here may no longer be
        available, and no odds shown are guaranteed. Always confirm the current price
        at the sportsbook before placing any bet.
      </div>
      <div style={{ marginTop: 5, color: theme.textMuted, fontSize: compact ? 10.5 : 11 }}>
        Odds data provided by{' '}
        <a
          href="https://the-odds-api.com/"
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: theme.dataBlue, textDecoration: 'none' }}
        >
          The Odds API
        </a>
        .
      </div>
    </div>
  );
}

/** Newest fetched_at across the rows on screen, or null if none carry one. */
export function latestFetchedAt(rows: Record<string, any>[], key = 'fetched_at'): string | null {
  let best: string | null = null;
  for (const r of rows) {
    const v = r[key];
    if (!v) continue;
    if (best === null || String(v) > best) best = String(v);
  }
  return best;
}
