import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getNFLMatchups, getNFLMatchupDeepDive } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import ChipRow from '../../components/ChipRow';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

/**
 * Matchup Deep Dive -- reached from the Matchup page's "Deeper dive" button.
 * Every efficiency stat shows both pairings at once: the away offense against
 * the home defense (left box) and the home offense against the away defense
 * (right box), each number with its rank of 32. Built by
 * backend/app/data/nfl_efficiency.py from nflverse play-by-play.
 */

interface Cell { value: number | null; display: string; rank: number | null }
interface Pair { off: Cell; def: Cell; edge: 'off' | 'def' | null }
interface Stat {
  stat: string; label: string; colored: boolean; lower_better: boolean;
  away_off: Pair; home_off: Pair;
}
interface Tab { key: string; title: string; sections: { title: string; stats: Stat[] }[] }
interface DeepDive {
  away: string; home: string; window: 'season' | 'last4'; season: number | null;
  last4_available: boolean; last4_from_games: number;
  games: Record<string, number>; tabs: Tab[]; error?: string;
}

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

/** Same tiers as the Matchup page: top 10 blue, bottom 10 red. */
function tierColor(rank: number | null, colored: boolean): string {
  if (!colored || rank == null) return theme.textPrimary;
  if (rank <= 10) return theme.dataBlue;
  if (rank >= 23) return theme.dataRed;
  return theme.textPrimary;
}

function Box({ pair, colored }: { pair: Pair; colored: boolean }) {
  const one = (c: Cell) => (
    <div style={{ textAlign: 'center', fontVariantNumeric: 'tabular-nums' }}>
      <div style={{ fontSize: 13.5, fontWeight: 600, color: tierColor(c.rank, colored) }}>{c.display}</div>
      <div style={{ fontSize: 10, color: theme.textMuted }}>{c.rank != null ? ordinal(c.rank) : '—'}</div>
    </div>
  );
  return (
    <div style={{
      background: theme.bgPage, borderRadius: 6, padding: '6px 8px',
      display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', gap: 4,
      outline: pair.edge ? `1px solid ${theme.accent}` : 'none',
    }}>
      {one(pair.off)}
      <span style={{ fontSize: 9.5, color: theme.textMuted }}>vs</span>
      {one(pair.def)}
    </div>
  );
}

export default function NFLMatchupDeepDive() {
  const isMobile = useIsMobile();
  const [params, setParams] = useSearchParams();
  const matchup = params.get('m') || '';
  const [matchups, setMatchups] = useState<string[]>([]);
  const [tab, setTab] = useState('passing_rushing');
  const [span, setSpan] = useState<'season' | 'last4'>('season');
  // Results are stored with the request they answer, so "loading" is simply
  // "the stored answer isn't for what's selected now" -- no state to reset
  // inside the effect.
  const key = `${matchup}|${span}`;
  const [result, setResult] = useState<{ key: string; data: DeepDive | null; error: string } | null>(null);
  const loading = !!matchup && result?.key !== key;
  const data = result?.key === key ? result.data : null;
  const error = result?.key === key ? result.error : '';

  useEffect(() => {
    getNFLMatchups()
      .then((res) => {
        setMatchups(res.data);
        if (!params.get('m') && res.data.length) setParams({ m: res.data[0] }, { replace: true });
      })
      .catch(() => setMatchups([]));
    // Only on first load: the selector below drives the URL after that.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!matchup) return;
    let live = true;
    const k = `${matchup}|${span}`;
    getNFLMatchupDeepDive(matchup, span)
      .then((res) => { if (live) setResult({ key: k, data: res.data, error: '' }); })
      .catch((err) => {
        if (live) setResult({ key: k, data: null, error: err?.response?.data?.detail || 'Failed to load.' });
      });
    return () => { live = false; };
  }, [matchup, span]);

  const current = data?.tabs.find((t) => t.key === tab) ?? data?.tabs[0];

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 820, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <Link
        to="/nfl/matchup"
        style={{ fontSize: 13, color: theme.accent, textDecoration: 'none' }}
      >← Back to matchup</Link>
      <h2 style={{ margin: '6px 0 10px', color: theme.textPrimary, fontSize: isMobile ? 20 : 24 }}>
        {data ? `${data.away} @ ${data.home}` : 'Matchup'} · Deep Dive
      </h2>

      <select
        value={matchup}
        onChange={(e) => setParams({ m: e.target.value })}
        style={{
          padding: '7px 10px', border: `1px solid ${theme.border}`, borderRadius: 6, fontSize: 14,
          minWidth: 200, background: theme.bgCard, color: theme.textPrimary, marginBottom: 12,
        }}
      >
        {!matchups.includes(matchup) && matchup && <option value={matchup}>{matchup}</option>}
        {matchups.map((m) => <option key={m} value={m}>{m}</option>)}
      </select>

      <ChipRow
        chips={[{ key: 'season', label: 'Season' }, { key: 'last4', label: 'Last 4 games' }]}
        value={data?.last4_available ? span : 'season'}
        onChange={(k) => { if (data?.last4_available || k === 'season') setSpan(k as 'season' | 'last4'); }}
        style={{ marginBottom: 4 }}
      />
      {data && !data.last4_available && (
        <div style={{ fontSize: 11.5, color: theme.textMuted, marginBottom: 12 }}>
          Last 4 games starts once every team has played {data.last4_from_games} — until then it matches the season.
        </div>
      )}

      {data && (
        <ChipRow
          chips={data.tabs.map((t) => ({ key: t.key, label: t.title }))}
          value={current?.key ?? ''}
          onChange={setTab}
          style={{ margin: '8px 0 12px' }}
        />
      )}

      {loading && <LoadingSpinner />}
      {error && <div style={{ color: theme.dataRed }}>{error}</div>}
      {data?.error && <div style={{ color: theme.dataRed }}>{data.error}</div>}
      {!loading && data && !data.error && data.tabs.length === 0 && (
        <div style={{ color: theme.textMuted, fontSize: 13 }}>Efficiency stats aren't available yet.</div>
      )}

      {!loading && data && current && (
        <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 10, padding: '12px 14px' }}>
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 11, fontWeight: 700,
            color: theme.textSecondary, textAlign: 'center', marginBottom: 4,
          }}>
            <div>{data.away} offense vs {data.home} D</div>
            <div>{data.home} offense vs {data.away} D</div>
          </div>
          <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 6, lineHeight: 1.45 }}>
            Rank of 32 under each number. 1st = best at it: gaining for an offense, stopping it for a defense.
            Blue = top 10, red = bottom 10. A green outline means one side ranks {15}+ spots better.
          </div>

          {current.sections.map((sec) => (
            <div key={sec.title}>
              {current.sections.length > 1 && (
                <div style={{
                  fontSize: 11, fontWeight: 700, color: theme.textSecondary, textTransform: 'uppercase',
                  letterSpacing: '0.05em', margin: '12px 0 2px',
                }}>{sec.title}</div>
              )}
              {sec.stats.map((s) => (
                <div key={s.stat} style={{
                  display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '8px 0',
                  borderTop: `1px solid ${theme.border}`,
                }}>
                  <div style={{ gridColumn: '1 / -1', fontSize: 13, color: theme.textPrimary }}>
                    {s.label}
                    {s.lower_better && (
                      <span style={{ fontSize: 10.5, color: theme.textMuted, marginLeft: 6 }}>lower is better on offense</span>
                    )}
                    {!s.colored && (
                      <span style={{ fontSize: 10.5, color: theme.textMuted, marginLeft: 6 }}>1st = most</span>
                    )}
                  </div>
                  <Box pair={s.away_off} colored={s.colored} />
                  <Box pair={s.home_off} colored={s.colored} />
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 11, color: theme.textMuted, textAlign: 'center', marginTop: 14 }}>
        Data: nflverse play-by-play{data?.season ? `, ${data.season} regular season` : ''}. Neutral = 1st–3rd quarter, win probability 20–80%.
      </div>
    </div>
  );
}
