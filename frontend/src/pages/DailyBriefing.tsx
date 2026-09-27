import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import LoadingSpinner from '../components/LoadingSpinner';
import ChipRow from '../components/ChipRow';
import BetSheet from '../components/BetSheet';
import { getBriefing } from '../api/betting';
import type { BetDraft } from '../api/betting';
import useIsMobile from '../hooks/useIsMobile';
import { theme } from '../theme';

/**
 * Daily Briefing -- what changed, grouped into sections you can open and
 * close (injuries, weather, usage trends, lineups, line moves), then the
 * day's games, one card each, with the context from every research page in
 * one place and at most two plays per game. Built by
 * backend/app/data/briefing.py.
 */

interface Change {
  kind: 'injury' | 'weather' | 'usage' | 'lineup' | 'move';
  sport: 'nfl' | 'mlb' | 'nba';
  time: string | null;
  tag: string;
  title: string;
  detail: string | null;
  /** Injuries: has props posted, volume we can see moving, or a QB. */
  key?: boolean;
  /** Injuries: the status before this change. */
  was?: string | null;
  /** Weather: warn when it's strong enough to matter. */
  tone?: Flag['tone'];
}

interface Starter {
  team: string;
  pitcher: string | null;
  throws?: string | null;
  games?: number | null;
  avg_so?: number | null;
  avg_outs?: number | null;
  avg_er?: number | null;
}

interface Flag { kind: string; tone: 'good' | 'bad' | 'warn' | 'neutral'; text: string; why?: string | null }
interface Play { label: string; note: string; longshot: boolean; bet: BetDraft }

interface Game {
  sport: 'nfl' | 'mlb' | 'nba';
  event_id: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  upcoming: boolean;
  line: string | null;
  starters: Starter[];
  flags: Flag[];
  lineups_posted: boolean | null;
  lineups_missing?: string[];
  plays: Play[];
  links: { label: string; to: string }[];
}

const TONE: Record<Flag['tone'], { bg: string; fg: string }> = {
  good: { bg: 'rgba(107,168,240,0.15)', fg: theme.dataBlue },
  bad: { bg: 'rgba(244,87,63,0.15)', fg: theme.dataRed },
  warn: { bg: 'rgba(232,163,61,0.15)', fg: theme.warningText },
  neutral: { bg: theme.bgPage, fg: theme.textSecondary },
};

/** Alert sections, in page order. All start open except a long injury list
 *  (a Sunday's worth), which starts closed so the rest stay in reach. */
const GROUPS: { kind: Change['kind']; label: string }[] = [
  { kind: 'injury', label: 'Injuries' },
  { kind: 'weather', label: 'Weather' },
  { kind: 'usage', label: 'Usage trends' },
  { kind: 'lineup', label: 'Lineups' },
  { kind: 'move', label: 'Line moves' },
];
const OPEN_IF_AT_MOST = 5;
const KEY_SHOWN = 6;

/** Tag colour for one alert row. */
function tone(c: Change): Flag['tone'] {
  if (c.kind === 'injury') {
    if (c.tag === 'ACTIVE') return 'good';
    return c.tag === 'QUESTIONABLE' || c.tag === 'DAY-TO-DAY' ? 'warn' : 'bad';
  }
  if (c.kind === 'weather') return c.tone ?? 'neutral';
  if (c.kind === 'usage') return c.tag === 'UP' ? 'good' : 'bad';
  if (c.kind === 'move') return 'warn';
  return 'good';
}

const FILTERS = [
  { key: 'all', label: 'All' }, { key: 'nfl', label: 'NFL' },
  { key: 'mlb', label: 'MLB' }, { key: 'nba', label: 'NBA' },
];

function ago(iso: string | null): string | null {
  if (!iso) return null;
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (isNaN(mins) || mins < 0) return null;
  return mins < 60 ? `${mins}m ago` : `${Math.round(mins / 60)}h ago`;
}

function start(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
}

/** Nickname: "Kansas City Royals" -> "Royals", but "Red Sox", "White Sox"
 *  and "Blue Jays" keep both words so the two Sox stay distinguishable. */
const short = (team: string) => {
  const w = team.split(' ');
  return /^(Sox|Jays)$/.test(w[w.length - 1]) && w.length > 1 ? w.slice(-2).join(' ') : w[w.length - 1];
};

const Section = ({ title, aside }: { title: string; aside?: string }) => (
  <div style={{
    display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
    fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
    color: theme.textMuted, margin: '20px 0 8px',
  }}>
    <span>{title}</span>
    {aside && <span style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 400 }}>{aside}</span>}
  </div>
);

export default function DailyBriefing() {
  const isMobile = useIsMobile();
  const [changes, setChanges] = useState<Change[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [generated, setGenerated] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sport, setSport] = useState('all');
  const [betting, setBetting] = useState<BetDraft | null>(null);
  /** Sections the user opened or closed; unset ones use the size rule. */
  const [open, setOpen] = useState<Partial<Record<Change['kind'], boolean>>>({});
  const [allInjuries, setAllInjuries] = useState(false);
  const [moreKey, setMoreKey] = useState(false);

  useEffect(() => {
    getBriefing()
      .then((res) => {
        setChanges(res.data.changes);
        setGames(res.data.games);
        setGenerated(res.data.generated_at);
      })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load.'))
      .finally(() => setLoading(false));
  }, []);

  const shownChanges = useMemo(() => changes.filter((c) => sport === 'all' || c.sport === sport), [changes, sport]);
  const shownGames = useMemo(() => games.filter((g) => sport === 'all' || g.sport === sport), [games, sport]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    games.forEach((g) => { c[g.sport] = (c[g.sport] || 0) + 1; });
    return c;
  }, [games]);

  const today = new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
  const summary = [
    counts.nfl ? `${counts.nfl} NFL game${counts.nfl === 1 ? '' : 's'}` : null,
    counts.mlb ? `${counts.mlb} MLB game${counts.mlb === 1 ? '' : 's'}` : null,
    counts.nba ? `${counts.nba} NBA game${counts.nba === 1 ? '' : 's'}` : null,
    ago(generated) ? `updated ${ago(generated)}` : null,
  ].filter(Boolean).join(' · ');

  return (
    <div style={{
      padding: isMobile ? 16 : 24, maxWidth: 1100, margin: '0 auto',
      background: theme.bgPage, minHeight: 'calc(100vh - 60px)',
    }}>
      <h1 style={{ margin: 0, fontSize: 24, color: theme.textPrimary }}>Daily Briefing</h1>
      <div style={{ color: theme.textSecondary, fontSize: 13, margin: '2px 0 14px' }}>
        {today}{summary ? ` · ${summary}` : ''}
      </div>

      <ChipRow chips={FILTERS} value={sport} onChange={setSport} />

      {loading && <LoadingSpinner />}
      {error && <div style={{ color: theme.dataRed, marginTop: 12 }}>{error}</div>}

      {!loading && !error && (
        <>
          <Section title="What changed" aside="injuries and line moves: last 12 hours" />
          {shownChanges.length === 0 && (
            <div style={{
              background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 10,
              padding: '10px 14px', fontSize: 13, color: theme.textMuted,
            }}>
              Nothing notable yet. Injuries, weather, usage trends, lineups and line moves show up here as they happen.
            </div>
          )}
          {GROUPS.map((grp) => {
            const rows = shownChanges.filter((c) => c.kind === grp.kind);
            if (rows.length === 0) return null;
            const isOpen = open[grp.kind] ?? (grp.kind !== 'injury' || rows.length <= OPEN_IF_AT_MOST);
            const keyRows = grp.kind === 'injury' ? rows.filter((c) => c.key) : rows;
            const pool = grp.kind === 'injury' && !allInjuries ? keyRows : rows;
            const list = grp.kind === 'injury' && !allInjuries && !moreKey ? pool.slice(0, KEY_SHOWN) : pool;
            return (
              <div key={grp.kind} style={{
                background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 10, marginBottom: 8,
              }}>
                <button
                  onClick={() => setOpen((o) => ({ ...o, [grp.kind]: !isOpen }))}
                  aria-expanded={isOpen}
                  style={{
                    width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '11px 14px',
                    background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left',
                  }}
                >
                  <span aria-hidden style={{
                    fontSize: 10, color: theme.textMuted, display: 'inline-block',
                    transform: isOpen ? 'rotate(90deg)' : 'none', transition: 'transform .15s',
                  }}>▶</span>
                  <span style={{ fontWeight: 600, fontSize: 14, color: theme.textPrimary }}>{grp.label}</span>
                  <span style={{
                    fontSize: 11, color: theme.textSecondary, background: theme.bgPage, borderRadius: 999, padding: '0 8px',
                  }}>{rows.length}</span>
                  {!isOpen && (
                    <span style={{
                      marginLeft: 'auto', fontSize: 12, color: theme.textMuted, minWidth: 0,
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '55%',
                    }}>{(keyRows[0] ?? rows[0]).title}</span>
                  )}
                </button>

                {isOpen && (
                  <div style={{ padding: '0 14px 8px' }}>
                    {grp.kind === 'injury' && (
                      <div style={{ display: 'flex', gap: 6, margin: '0 0 6px' }}>
                        {[
                          { on: !allInjuries, label: `Key players (${keyRows.length})`, v: false },
                          { on: allInjuries, label: `All ${rows.length}`, v: true },
                        ].map((t) => (
                          <button key={t.label} onClick={() => setAllInjuries(t.v)} style={{
                            fontSize: 11.5, padding: '2px 10px', borderRadius: 999, cursor: 'pointer', background: 'transparent',
                            border: `1px solid ${t.on ? theme.accent : theme.border}`,
                            color: t.on ? theme.accent : theme.textSecondary,
                          }}>{t.label}</button>
                        ))}
                      </div>
                    )}
                    {grp.kind === 'injury' && list.length === 0 && (
                      <div style={{ fontSize: 12.5, color: theme.textMuted, padding: '6px 0' }}>
                        No key players changed status. Tap "All" for everyone else.
                      </div>
                    )}
                    {list.map((c) => {
                      const t = TONE[tone(c)];
                      return (
                        <div key={`${c.kind}-${c.title}`} style={{
                          display: 'flex', gap: 8, padding: '8px 0', borderTop: `1px solid ${theme.border}`,
                        }}>
                          <span style={{
                            flex: '0 0 auto', height: 'fit-content', marginTop: 2, fontSize: 9.5, fontWeight: 700,
                            background: t.bg, color: t.fg, borderRadius: 4, padding: '1px 6px', letterSpacing: '0.03em',
                          }}>{c.tag}</span>
                          <div style={{ fontSize: 13.5, color: theme.textPrimary, minWidth: 0 }}>
                            {c.title}
                            <span style={{ fontSize: 11, color: theme.textMuted }}>
                              {' · '}{[
                                c.was ? `was ${c.was}` : null,
                                c.sport.toUpperCase(),
                                ago(c.time),
                              ].filter(Boolean).join(' · ')}
                            </span>
                            {c.detail && <div style={{ fontSize: 12.5, color: theme.textSecondary, marginTop: 2 }}>{c.detail}</div>}
                          </div>
                        </div>
                      );
                    })}
                    {grp.kind === 'injury' && !allInjuries && !moreKey && pool.length > KEY_SHOWN && (
                      <button onClick={() => setMoreKey(true)} style={{
                        background: 'transparent', border: 'none', padding: '6px 0 2px', cursor: 'pointer',
                        fontSize: 12.5, color: theme.accent,
                      }}>Show {pool.length - KEY_SHOWN} more key player{pool.length - KEY_SHOWN === 1 ? '' : 's'}</button>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          <Section title="The slate" aside="by start time" />
          {shownGames.length === 0 && (
            <div style={{ fontSize: 13, color: theme.textMuted }}>No games with lines posted in the next day.</div>
          )}
          <div style={{
            display: 'grid', gap: 12,
            gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(340px, 1fr))',
          }}>
            {shownGames.map((g) => (
              <div key={g.event_id} style={{
                background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 10, padding: '12px 14px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 15, color: theme.textPrimary }}>
                    {short(g.away_team)} @ {short(g.home_team)}
                  </span>
                  <span style={{ fontSize: 11, color: theme.textMuted }}>{g.sport.toUpperCase()}</span>
                </div>
                <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 8 }}>
                  {start(g.commence_time)}{g.line ? ` · ${g.line}` : ''}{g.upcoming ? ' · upcoming' : ''}
                </div>

                {g.starters.length > 0 && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
                    {g.starters.map((s) => (
                      <div key={s.team} style={{ background: theme.bgPage, borderRadius: 6, padding: '7px 9px' }}>
                        <div style={{ fontSize: 10.5, color: theme.textMuted }}>{short(s.team)} starter</div>
                        {s.pitcher ? (
                          <>
                            <div style={{ fontWeight: 600, fontSize: 13, color: theme.textPrimary }}>
                              {s.pitcher}{s.throws ? <span style={{ color: theme.textMuted, fontWeight: 400 }}> ({s.throws})</span> : null}
                            </div>
                            <div style={{ fontSize: 11, color: theme.textMuted, fontVariantNumeric: 'tabular-nums' }}>
                              {s.games
                                ? `Last ${s.games}: ${s.avg_so ?? '—'} K · ${s.avg_outs ?? '—'} outs · ${s.avg_er ?? '—'} ER`
                                : 'No recent starts'}
                            </div>
                          </>
                        ) : (
                          <div style={{ fontSize: 12, color: theme.textMuted }}>Not announced</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <div style={{ fontSize: 12.5, color: theme.textSecondary, lineHeight: 1.65 }}>
                  {g.flags.map((f, i) => (
                    <div key={i}>
                      <span style={{
                        display: 'inline-block', fontSize: 9.5, fontWeight: 700, borderRadius: 4, padding: '0 6px',
                        marginRight: 6, textTransform: 'uppercase', letterSpacing: '0.03em',
                        background: TONE[f.tone].bg, color: TONE[f.tone].fg,
                      }}>{f.kind}</span>
                      {f.text}
                      {f.why && <div style={{ fontSize: 11.5, color: theme.textMuted, lineHeight: 1.45, margin: '1px 0 3px' }}>{f.why}</div>}
                    </div>
                  ))}
                  {g.sport === 'mlb' && (g.lineups_missing?.length ?? 0) > 0 && (
                    <div style={{ color: theme.textMuted }}>
                      {g.lineups_missing!.length === 2 ? 'Lineups' : `${short(g.lineups_missing![0])} lineup`} not posted yet
                      (usually 1–4 hours before first pitch).
                    </div>
                  )}
                </div>

                {g.plays.length > 0 && (
                  <div style={{ marginTop: 9, borderTop: `1px solid ${theme.border}`, paddingTop: 8 }}>
                    {g.plays.map((p) => (
                      <div key={p.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, padding: '3px 0' }}>
                        <div style={{ fontSize: 12.5, color: theme.textPrimary }}>
                          {p.label}
                          {p.longshot && <span style={{ color: theme.warningText, fontSize: 10, fontWeight: 700, marginLeft: 6 }}>LONG SHOT</span>}
                          <div style={{ fontSize: 11, color: theme.textMuted }}>{p.note}</div>
                        </div>
                        <button
                          onClick={() => setBetting(p.bet)}
                          style={{
                            padding: '5px 11px', borderRadius: 6, border: `1px solid ${theme.accent}`,
                            background: 'transparent', color: theme.accent, fontWeight: 700, fontSize: 12, cursor: 'pointer',
                          }}
                        >Bet</button>
                      </div>
                    ))}
                  </div>
                )}

                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8, fontSize: 12 }}>
                  {g.links.map((l) => (
                    <Link key={l.to} to={l.to} style={{ color: theme.accent, textDecoration: 'none' }}>{l.label} →</Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <BetSheet key={betting ? JSON.stringify(betting) : 'none'} bet={betting} onClose={() => setBetting(null)} />
    </div>
  );
}
