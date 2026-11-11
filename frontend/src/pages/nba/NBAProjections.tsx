import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getNBAProjections, postNBAProjections, getNBAProjectionRecord } from '../../api/nba';
import LoadingSpinner from '../../components/LoadingSpinner';
import OddsDisclaimer from '../../components/OddsDisclaimer';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';
import { nameKey, readMinutesFile } from '../../utils/minutesUpload';

/**
 * NBA Projections -- Shawn's stat model (app/data/nba_projections.py) with
 * minutes you can edit. Default minutes come from recent minutes, the injury
 * report and who's newly out or back; change any of them and that game's
 * projections rerun (usage is re-balanced across the team, the way the
 * original model did it).
 */

type Stat = 'PTS' | 'REB' | 'AST' | '3PM' | 'PRA' | 'STL' | 'BLK' | 'TOV';

interface LineEdge {
  label: string; line: number; projection: number; diff: number;
  side: 'over' | 'under' | null; price: number | null; book: string | null;
  over_price: number | null; under_price: number | null; threshold: number | null;
  prob_over: number | null; prob_under: number | null; market_prob_over: number | null;
  model_prob_over?: number | null; model_prob_under?: number | null;
  ev: number | null; suspect: boolean;
}

interface PlayerRow {
  player: string; status: string | null; injury: string | null;
  default_min: number; minutes: number; edited: boolean;
  projection: Record<Stat, number>;
  lines: Record<string, LineEdge>;
}

interface TeamBlock { team: string; home: boolean; minutes_total: number; players: PlayerRow[] }
interface Game { game_id: number; start_utc: string | null; away: string; home: string; teams: TeamBlock[] }
interface Resp {
  date: string | null;
  model: {
    trained_through: string; holdout_mae: Record<string, number>; holdout_days: number;
    minutes_holdout_mae?: number | null; uses_vegas?: boolean;
  } | null;
  lines_as_of: string | null;
  min_ev?: number;
  games: Game[];
}

function pct(n: number | null | undefined): string {
  return n == null ? '—' : `${Math.round(n * 100)}%`;
}

function chance(e: LineEdge): { model: number | null; book: number | null } {
  if (e.side === 'under') {
    return { model: e.prob_under, book: e.market_prob_over != null ? 1 - e.market_prob_over : null };
  }
  return { model: e.prob_over, book: e.market_prob_over };
}

interface Flag { p: PlayerRow; e: LineEdge; team: string; opp: string; game: Game }

function flagsFor(games: Game[]): Flag[] {
  const out: Flag[] = [];
  games.forEach((g) => g.teams.forEach((t) => t.players.forEach((p) => {
    Object.values(p.lines).forEach((e) => {
      if (e.side && e.ev != null) out.push({ p, e, team: t.team, opp: t.team === g.home ? g.away : g.home, game: g });
    });
  })));
  return out.sort((a, b) => (b.e.ev || 0) - (a.e.ev || 0));
}

function FlagRow({ f, onOpen }: { f: Flag; onOpen?: () => void }) {
  const { model, book } = chance(f.e);
  return (
    <div
      onClick={onOpen}
      style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '8px 0', borderTop: `1px solid ${theme.border}`, cursor: onOpen ? 'pointer' : 'default' }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13.5, color: theme.textPrimary }}>
          <b>{f.p.player}</b> <span style={{ color: theme.textMuted }}>{f.team} vs {f.opp}</span>
        </div>
        <div style={{ fontSize: 12.5, color: theme.textSecondary }}>
          <b style={{ color: theme.textPrimary }}>{f.e.side === 'over' ? 'Over' : 'Under'} {f.e.line} {f.e.label}</b>
          {' '}· {odds(f.e.price)} {BOOK_NAMES[f.e.book || ''] || f.e.book}
          {' '}· projects {f.e.projection.toFixed(1)} at {f.p.minutes} min
        </div>
        <div style={{ fontSize: 11.5, color: theme.textMuted }}>
          Chance it hits: ours {pct(model)}{book != null ? `, book ${pct(book)}` : ''}
          {f.e.model_prob_over != null && (() => {
            const raw = f.e.side === 'over' ? f.e.model_prob_over : f.e.model_prob_under;
            return raw != null ? ` (model alone ${pct(raw)})` : '';
          })()}
          {f.p.status ? ` · ${f.p.status}` : ''}
          {f.e.suspect && <span style={{ color: theme.warningText }}> · gap this big often means news the model doesn't know — check before betting</span>}
        </div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div style={{ fontSize: 16, fontWeight: 800, color: f.e.suspect ? theme.warningText : theme.dataBlue }}>+{Math.round((f.e.ev || 0) * 100)}%</div>
        <div style={{ fontSize: 10.5, color: theme.textMuted }}>exp. return</div>
      </div>
    </div>
  );
}

function BestBets({ games, onOpen }: { games: Game[]; onOpen: (gid: number) => void }) {
  const [all, setAll] = useState(false);
  const flags = flagsFor(games);
  if (!flags.length) {
    return (
      <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 13, color: theme.textSecondary }}>
        <b style={{ color: theme.textPrimary }}>Best bets tonight</b> — nothing clears the bar right now. Lines post through the day; check back.
      </div>
    );
  }
  const shown = all ? flags : flags.slice(0, 8);
  return (
    <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '12px 14px', marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <b style={{ color: theme.textPrimary, fontSize: 15 }}>Best bets tonight</b>
        <span style={{ fontSize: 11.5, color: theme.textMuted }}>{flags.length} across {new Set(flags.map((f) => f.game.game_id)).size} games · tap to open</span>
      </div>
      {shown.map((f) => <FlagRow key={`${f.p.player}-${f.e.label}`} f={f} onOpen={() => onOpen(f.game.game_id)} />)}
      {flags.length > 8 && (
        <button onClick={() => setAll(!all)} style={{ marginTop: 6, background: 'none', border: 'none', padding: 0, color: theme.dataBlue, fontSize: 12, cursor: 'pointer' }}>
          {all ? 'Show top 8' : `Show all ${flags.length}`}
        </button>
      )}
    </div>
  );
}

const COLS: { stat: Stat; market?: string }[] = [
  { stat: 'PTS', market: 'points' }, { stat: 'REB', market: 'rebounds' }, { stat: 'AST', market: 'assists' },
  { stat: '3PM', market: 'threes' }, { stat: 'PRA', market: 'points_rebounds_assists' },
  { stat: 'STL', market: 'steals' }, { stat: 'BLK', market: 'blocks' }, { stat: 'TOV', market: 'turnovers' },
];

const BOOK_NAMES: Record<string, string> = {
  betmgm: 'BetMGM', draftkings: 'DraftKings', fanduel: 'FanDuel', fanatics: 'Fanatics', espnbet: 'ESPN BET',
};

function odds(n: number | null): string {
  if (n == null) return '';
  return n > 0 ? `+${n.toFixed(0)}` : n.toFixed(0);
}

function tip(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '' : d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

const storeKey = (date: string | null, gid: number) => `nba-proj-mins:${date}:${gid}`;
function loadEdits(date: string | null, gid: number): Record<string, number> {
  try { return JSON.parse(localStorage.getItem(storeKey(date, gid)) || '{}'); } catch { return {}; }
}
function saveEdits(date: string | null, gid: number, edits: Record<string, number>) {
  try { localStorage.setItem(storeKey(date, gid), JSON.stringify(edits)); } catch { /* private mode etc. */ }
}

function StatCell({ value, edge }: { value: number; edge?: LineEdge }) {
  const flagged = !!edge?.side;
  return (
    <td style={{ padding: '6px 6px', textAlign: 'center', verticalAlign: 'top' }}>
      <div style={{ fontWeight: 700, color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>{value.toFixed(1)}</div>
      {edge && (
        <div
          title={`Line ${edge.line} · over ${pct(edge.prob_over)} (book ${pct(edge.market_prob_over)})${flagged ? ` · ${edge.side === 'over' ? 'Over' : 'Under'} ${odds(edge.price)} at ${BOOK_NAMES[edge.book || ''] || edge.book}, +${Math.round((edge.ev || 0) * 100)}%` : ''}`}
          style={{
            fontSize: 10.5, marginTop: 2, borderRadius: 3, padding: '0 3px', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap',
            color: flagged ? theme.bgPage : theme.textMuted,
            background: flagged ? theme.dataBlue : 'transparent',
            fontWeight: flagged ? 700 : 400,
          }}
        >
          {flagged ? `${edge.side === 'over' ? 'O' : 'U'} ${edge.line}` : edge.line}
        </div>
      )}
    </td>
  );
}

function MinutesInput({ row, pending, onChange, compact }: {
  row: PlayerRow; pending?: number | null; onChange: (v: number | null) => void; compact?: boolean;
}) {
  // pending: typed but not run yet (undefined = nothing pending; null = back to default)
  const shown = pending === undefined ? row.minutes : pending === null ? row.default_min : pending;
  const [text, setText] = useState(String(shown));
  useEffect(() => { setText(String(shown)); }, [shown]);
  const isPending = pending !== undefined;
  const commit = () => {
    const v = parseFloat(text);
    if (text.trim() === '' || isNaN(v)) { onChange(null); return; }
    onChange(Math.max(0, Math.min(48, v)));
  };
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <input
        type="number" inputMode="decimal" min={0} max={48} step={0.5} value={text}
        onFocus={(e) => e.target.select()}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
        aria-label={`Minutes for ${row.player}`}
        style={{
          width: compact ? 44 : 54, padding: compact ? '5px 4px' : '5px 6px', fontSize: 13, borderRadius: 4, textAlign: 'right',
          background: theme.bgPage, color: theme.textPrimary, fontVariantNumeric: 'tabular-nums',
          border: `1px ${isPending ? 'dashed' : 'solid'} ${isPending ? theme.dataBlue : row.edited ? theme.warningText : theme.border}`,
        }}
      />
      {(row.edited || (isPending && pending !== null)) && (
        <button
          onClick={() => onChange(null)}
          title={`Back to default (${row.default_min})`}
          style={{ background: 'none', border: 'none', color: theme.textMuted, cursor: 'pointer', fontSize: 12, padding: 0 }}
        >
          ↺
        </button>
      )}
    </div>
  );
}

function TeamTable({ t, pending, onMinutes, onRun, busy, isMobile }: {
  t: TeamBlock; pending: Record<string, number | null>; onMinutes: (p: string, v: number | null) => void;
  onRun: (team: string) => void; busy: boolean; isMobile: boolean;
}) {
  const nPending = t.players.filter((p) => p.player in pending).length;
  // minutes total as typed, so the 240 check is useful before running
  const typedTotal = t.players.reduce((a, p) => {
    const v = pending[p.player];
    return a + (v === undefined ? p.minutes : v === null ? p.default_min : v);
  }, 0);
  const off = Math.abs(typedTotal - 240) > 5;
  const cols = isMobile ? COLS.slice(0, 4) : COLS;
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <b style={{ color: theme.textPrimary, fontSize: 15 }}>{t.team}{t.home ? ' (home)' : ''}</b>
        <span style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <span style={{ fontSize: 12, color: off ? theme.warningText : theme.textSecondary, fontVariantNumeric: 'tabular-nums' }}>
            {typedTotal.toFixed(0)} / 240 minutes{off ? (typedTotal > 240 ? ' — over' : ' — under') : ''}
          </span>
          {nPending > 0 && (
            <button
              onClick={() => onRun(t.team)} disabled={busy}
              style={{
                background: theme.dataBlue, color: theme.bgPage, border: 'none', borderRadius: 4, padding: '5px 12px',
                fontSize: 12.5, fontWeight: 700, cursor: busy ? 'wait' : 'pointer', opacity: busy ? 0.6 : 1,
              }}
            >
              {busy ? 'Updating…' : `Update ${t.team} projections (${nPending} change${nPending === 1 ? '' : 's'})`}
            </button>
          )}
        </span>
      </div>
      <div style={{ overflowX: 'auto', border: `1px solid ${theme.border}`, borderRadius: 8 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, background: theme.bgCard }}>
          <thead>
            <tr style={{ color: theme.textSecondary, background: theme.bgCardHover }}>
              <th style={{ textAlign: 'left', padding: '7px 8px', position: 'sticky', left: 0, background: theme.bgCardHover }}>Player</th>
              <th style={{ padding: '7px 6px', textAlign: 'left' }}>Min</th>
              {cols.map((c) => <th key={c.stat} style={{ padding: '7px 6px' }}>{c.stat}</th>)}
            </tr>
          </thead>
          <tbody>
            {t.players.map((p) => {
              const out = p.status === 'Out';
              return (
                <tr key={p.player} style={{ borderTop: `1px solid ${theme.border}`, opacity: out && p.minutes === 0 ? 0.55 : 1 }}>
                  <td style={{ padding: '6px 8px', position: 'sticky', left: 0, background: theme.bgCard, minWidth: isMobile ? 96 : 160 }}>
                    <div style={{ color: theme.textPrimary, fontWeight: 600 }}>{p.player}</div>
                    {p.status && (
                      <div style={{ fontSize: 10.5, color: out ? theme.warningText : theme.textMuted }}>
                        {p.status}{p.injury ? ` · ${p.injury}` : ''}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '6px 6px' }}>
                    <MinutesInput row={p} pending={pending[p.player]} onChange={(v) => onMinutes(p.player, v)} compact={isMobile} />
                  </td>
                  {cols.map((c) => (
                    <StatCell key={c.stat} value={p.projection[c.stat]} edge={c.market ? p.lines[c.market] : undefined} />
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Plays({ game }: { game: Game }) {
  const flags = flagsFor([game]);
  if (!flags.length) return null;
  return (
    <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '10px 14px', marginBottom: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: theme.textPrimary }}>Flagged in this game</div>
      {flags.map((f) => <FlagRow key={`${f.p.player}-${f.e.label}`} f={f} />)}
    </div>
  );
}


interface RecordResp {
  accuracy: { games: number; since: string; minutes_mae: number; mae: Record<string, number> } | null;
  plays: { plays: number; wins: number; losses: number; win_pct: number | null; units: number; roi_pct: number } | null;
  by_market: { market: string; label: string; plays: number; wins: number; losses: number; win_pct: number | null; units: number; roi_pct: number }[];
}

function TrackRecord() {
  const [rec, setRec] = useState<RecordResp | null>(null);
  useEffect(() => { getNBAProjectionRecord().then((r) => setRec(r.data)).catch(() => setRec(null)); }, []);
  if (!rec || (!rec.accuracy && !rec.plays)) {
    return <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 20 }}>Track record starts once the first projected games are final.</div>;
  }
  const cell = { padding: '6px 8px', borderBottom: `1px solid ${theme.border}`, fontSize: 12 } as const;
  return (
    <div style={{ marginTop: 26 }}>
      <h3 style={{ color: theme.textPrimary, marginBottom: 6 }}>Track record</h3>
      {rec.accuracy && (
        <div style={{ fontSize: 12.5, color: theme.textSecondary, marginBottom: 10, lineHeight: 1.6 }}>
          At default minutes since {rec.accuracy.since} ({rec.accuracy.games} player-games), projections have missed by{' '}
          {Object.entries(rec.accuracy.mae).map(([s, v]) => `${v} ${s}`).join(', ')} on average; default minutes by {rec.accuracy.minutes_mae}.
        </div>
      )}
      {rec.plays && (
        <>
          <div style={{ fontSize: 13, color: theme.textPrimary, marginBottom: 8 }}>
            Plays past the threshold: <b>{rec.plays.wins}-{rec.plays.losses}</b>
            {rec.plays.win_pct != null && ` (${rec.plays.win_pct}%)`}, {rec.plays.units > 0 ? '+' : ''}{rec.plays.units} units at the price logged
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', color: theme.textPrimary }}>
            <thead><tr style={{ color: theme.textSecondary, textAlign: 'left' }}>
              <th style={cell}>Market</th><th style={cell}>Record</th><th style={cell}>Units</th><th style={cell}>Return</th>
            </tr></thead>
            <tbody>
              {rec.by_market.map((m) => (
                <tr key={m.market}>
                  <td style={cell}>{m.label}</td><td style={cell}>{m.wins}-{m.losses}</td>
                  <td style={{ ...cell, color: m.units > 0 ? theme.dataBlue : theme.warningText }}>{m.units > 0 ? '+' : ''}{m.units}</td>
                  <td style={cell}>{m.roi_pct > 0 ? '+' : ''}{m.roi_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

export default function NBAProjections() {
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [gameId, setGameId] = useState<number | null>(null);
  const [edits, setEdits] = useState<Record<string, number>>({});
  // typed but not run yet: player -> minutes (null = back to default)
  const [pending, setPending] = useState<Record<string, number | null>>({});
  const [busy, setBusy] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ text: string; warn: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const isMobile = useIsMobile();
  const req = useRef(0);

  useEffect(() => {
    getNBAProjections()
      .then((r) => {
        setData(r.data);
        if (r.data.games?.length) setGameId(r.data.games[0].game_id);
      })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load projections.'))
      .finally(() => setLoading(false));
  }, []);

  const rerun = useCallback((gid: number, next: Record<string, number>) => {
    const id = ++req.current;
    setBusy(true);
    postNBAProjections({ game_id: gid, minutes: next })
      .then((r) => {
        if (id !== req.current || !r.data.games?.length) return;
        const fresh = r.data.games[0];
        setData((d) => (d ? { ...d, games: d.games.map((g) => (g.game_id === gid ? fresh : g)) } : d));
      })
      .catch(() => {})
      .finally(() => { if (id === req.current) setBusy(false); });
  }, []);

  // Switching games restores that game's saved edits (this browser only)
  useEffect(() => {
    if (gameId == null || !data) return;
    const saved = loadEdits(data.date, gameId);
    setEdits(saved);
    setPending({});
    if (Object.keys(saved).length) rerun(gameId, saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId, data?.date]);

  // Typing only stages a change; the team's "Update" button runs the model,
  // so a user can rework a whole rotation (and check the 240) in one go.
  const onMinutes = (player: string, v: number | null) => {
    const current = edits[player];
    setPending((pd) => {
      const next = { ...pd };
      if ((v === null && current === undefined) || (v !== null && v === current)) delete next[player];
      else next[player] = v;
      return next;
    });
  };

  const runTeam = (team: string) => {
    if (gameId == null || !game) return;
    const roster = new Set(game.teams.find((t) => t.team === team)?.players.map((p) => p.player) || []);
    const next = { ...edits };
    const left: Record<string, number | null> = {};
    Object.entries(pending).forEach(([p, v]) => {
      if (!roster.has(p)) { left[p] = v; return; }
      if (v === null) delete next[p]; else next[p] = v;
    });
    setEdits(next);
    setPending(left);
    saveEdits(data?.date ?? null, gameId, next);
    rerun(gameId, next);
  };

  // A sheet of player + minutes, applied to every game it covers tonight.
  // Saved like hand edits (this browser), so switching games keeps them.
  const onUpload = async (file: File) => {
    if (!data) return;
    let rows;
    try { rows = await readMinutesFile(file); } catch (e) {
      setUploadMsg({ text: (e as Error).message || 'Couldn’t read that file.', warn: true }); return;
    }
    if (!rows.length) { setUploadMsg({ text: 'No player + minutes rows found in that file.', warn: true }); return; }
    const where = new Map<string, { gid: number; player: string }>();
    data.games.forEach((g) => g.teams.forEach((t) => t.players.forEach((p) => where.set(nameKey(p.player), { gid: g.game_id, player: p.player }))));
    const byGame = new Map<number, Record<string, number>>();
    const missing: string[] = [];
    rows.forEach((r) => {
      const hit = where.get(nameKey(r.player));
      if (!hit) { missing.push(r.player); return; }
      const g = byGame.get(hit.gid) || {};
      g[hit.player] = r.minutes;
      byGame.set(hit.gid, g);
    });
    let n = 0;
    byGame.forEach((m, gid) => {
      const merged = { ...loadEdits(data.date, gid), ...m };
      saveEdits(data.date, gid, merged);
      n += Object.keys(m).length;
      if (gid === gameId) { setEdits(merged); setPending({}); rerun(gid, merged); }
    });
    setUploadMsg({
      text: `Updated ${n} player${n === 1 ? '' : 's'} across ${byGame.size} game${byGame.size === 1 ? '' : 's'}.`
        + (missing.length ? ` Not on tonight's slate: ${missing.slice(0, 8).join(', ')}${missing.length > 8 ? ` +${missing.length - 8} more` : ''}.` : ''),
      warn: missing.length > 0,
    });
  };

  const resetAll = () => {
    if (gameId == null) return;
    setEdits({});
    setPending({});
    saveEdits(data?.date ?? null, gameId, {});
    rerun(gameId, {});
  };

  const game = useMemo(() => data?.games.find((g) => g.game_id === gameId) || null, [data, gameId]);
  const mae = data?.model?.holdout_mae;

  return (
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 1100, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NBA Projections</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 12, lineHeight: 1.55 }}>
        Projected stats for every player tonight, from recent form, opponent defense, pace, rest and
        usage — <b style={{ color: theme.textPrimary }}>given his minutes</b>. Minutes start from a default
        built on recent minutes and the injury report; change any of them, then tap <b style={{ color: theme.textPrimary }}>Update</b> on that team to rerun it.
        Lines under each number are the main line across books. A line turns blue when the model's chance
        of that side beats the price by {Math.round((data?.min_ev ?? 0.05) * 100)}% or more — the chance comes from how
        results have actually spread around projections like it, so a 5-point gap on a 20.5 line counts
        for more than on a 35.5 line.
        {mae && <> With the right minutes the model misses by about {mae.PTS} points, {mae.REB} rebounds and {mae.AST} assists a game
          (last {data?.model?.holdout_days} days){data?.model?.minutes_holdout_mae ? <>; the default minutes miss by about {data.model.minutes_holdout_mae}</> : ''} —
          so minutes are where your own read matters most.</>}
        {data?.model && (
          <> {data.model.uses_vegas
            ? 'Tonight\'s Vegas totals and spreads are part of the projection.'
            : 'Vegas totals and spreads aren\'t in the model yet — they switch on automatically once there\'s enough line history and they test better.'}</>
        )}
      </div>

      {data?.lines_as_of && <OddsDisclaimer fetchedAt={data.lines_as_of} compact={isMobile} />}

      {loading && <LoadingSpinner />}
      {error && <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>{error}</div>}
      {!loading && !error && !data?.games.length && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40 }}>No projections yet — they publish with the morning NBA update.</div>
      )}

      {!!data?.games.length && <BestBets games={data.games} onOpen={(gid) => setGameId(gid)} />}

      {!!data?.games.length && (
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4, marginBottom: 14 }}>
          {data.games.map((g) => (
            <button
              key={g.game_id}
              onClick={() => setGameId(g.game_id)}
              style={{
                flex: '0 0 auto', padding: '8px 12px', borderRadius: 6, cursor: 'pointer', textAlign: 'left',
                background: g.game_id === gameId ? theme.bgCardHover : theme.bgCard, color: theme.textPrimary,
                border: `1px solid ${g.game_id === gameId ? theme.dataBlue : theme.border}`,
              }}
            >
              <div style={{ fontWeight: 700, fontSize: 14 }}>{g.away} @ {g.home}</div>
              <div style={{ fontSize: 11, color: theme.textSecondary }}>{tip(g.start_utc)}</div>
            </button>
          ))}
        </div>
      )}

      {game && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, minHeight: 24 }}>
            <span style={{ fontSize: 12, color: theme.textMuted }}>
              {busy ? 'Updating…' : Object.keys(edits).length ? `${Object.keys(edits).length} minute${Object.keys(edits).length === 1 ? '' : 's'} edited (saved in this browser)` : 'Default minutes'}
            </span>
            <span style={{ display: 'flex', gap: 8 }}>
            <input
              ref={fileRef} type="file" accept=".xlsx,.xlsm,.csv,.txt" style={{ display: 'none' }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ''; }}
            />
            <button
              onClick={() => fileRef.current?.click()}
              title="Excel or CSV with a player column and a minutes column"
              style={{ background: 'none', border: `1px solid ${theme.dataBlue}`, borderRadius: 4, color: theme.dataBlue, fontSize: 12, padding: '4px 10px', cursor: 'pointer' }}
            >
              Upload minutes
            </button>
            {Object.keys(edits).length > 0 && (
              <button onClick={resetAll} style={{ background: 'none', border: `1px solid ${theme.border}`, borderRadius: 4, color: theme.textSecondary, fontSize: 12, padding: '4px 10px', cursor: 'pointer' }}>
                Reset all minutes
              </button>
            )}
            </span>
          </div>
          {uploadMsg && (
            <div style={{ fontSize: 12, marginBottom: 10, color: uploadMsg.warn ? theme.warningText : theme.textSecondary }}>
              {uploadMsg.text}{' '}
              <button onClick={() => setUploadMsg(null)} style={{ background: 'none', border: 'none', color: theme.textMuted, cursor: 'pointer', fontSize: 12 }}>✕</button>
            </div>
          )}
          <Plays game={game} />
          {game.teams.map((t) => (
            <TeamTable key={t.team} t={t} pending={pending} onMinutes={onMinutes} onRun={runTeam} busy={busy} isMobile={isMobile} />
          ))}
        </>
      )}

      <TrackRecord />
      <div style={{ marginTop: 18, fontSize: 12, color: theme.textMuted, lineHeight: 1.6 }}>
        Projections are estimates, not guarantees. Usage shifts too: the model knows how much of the team's
        usage is on the floor, so setting a high-usage player to 0 raises his teammates' scoring and
        assists at the same minutes, in proportion to how much of the offense each one already runs
        (Luka out: Reaves about +5 points, close to the +20% he's scored in real games without him). His minutes don't move
        to anyone on their own — add them where you think they'll go.
      </div>
    </div>
  );
}
