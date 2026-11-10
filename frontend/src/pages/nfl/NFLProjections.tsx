import { useEffect, useMemo, useState } from 'react';
import { getNFLProjections, getNFLProjectionRecord } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import OddsDisclaimer from '../../components/OddsDisclaimer';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

/**
 * NFL Projections (app/data/nfl_projections.py). Every game is played out
 * 4,000 times snap by snap -- score, clock, field position, down and
 * distance -- so plays, time of possession, pass/run split and who gets the
 * ball when a team is chasing all come out of the game script rather than
 * an average. Player numbers blend that simulation with a direct model of
 * recent role and matchup. Nothing on the page is editable.
 */

interface Edge {
  label: string; line: number | null; projection: number; model?: number;
  side: 'over' | 'under' | 'yes' | null; tier: 'bet' | 'watch' | null;
  price: number | null; book: string | null; over_price: number | null; under_price: number | null; over_book?: string | null;
  prob_over: number | null; prob_under?: number | null; market_prob_over?: number | null;
  ev: number | null; suspect: boolean;
}
interface Player {
  game_id: string; player: string; player_id: string; team: string; opponent: string; position: string;
  status: string | null; injury: string | null; ruled_out?: boolean; sim_targets: number | null; snap_pct: number | null;
  projection: Record<string, number>; lines: Record<string, Edge>;
}
interface TeamFlow { team: string; sim_points: number; implied_points: number | null; plays: number; dropbacks: number; runs: number; top_min: number }
interface Game {
  game_id: string; kickoff: string; home: string; away: string;
  spread_line: number | null; total_line: number | null;
  model_margin: number | null; model_total: number | null; model_home_win: number | null; sim_home_win: number;
  sim_margin_p10_p90: [number, number]; teams: { home: TeamFlow; away: TeamFlow };
  roof: string | null; wind: number | null; temp: number | null;
}
interface Bet extends Edge { game_id: string; player: string; team: string; position: string; status: string | null; market: string }
interface Resp {
  season: number | null; week: number | null; generated_at?: string; lines_as_of: string | null;
  games: Game[]; players: Player[]; best_bets: Bet[]; watch: Bet[];
  accuracy?: Record<string, number[]>; min_ev?: number; min_prob_edge?: number;
}

const BOOK_NAMES: Record<string, string> = {
  betmgm: 'BetMGM', draftkings: 'DraftKings', fanduel: 'FanDuel', fanatics: 'Fanatics', espnbet: 'ESPN BET',
  williamhill_us: 'Caesars', betrivers: 'BetRivers', hardrockbet: 'Hard Rock',
};
const pct = (n: number | null | undefined) => (n == null ? '—' : `${Math.round(n * 100)}%`);
const odds = (n: number | null) => (n == null ? '' : n > 0 ? `+${n.toFixed(0)}` : n.toFixed(0));
const book = (b: string | null) => BOOK_NAMES[b || ''] || b || '';

function kick(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '' : d.toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });
}

function spreadText(g: Game): string {
  if (g.spread_line == null) return 'No line yet';
  const fav = g.spread_line > 0 ? g.home : g.away;
  const s = Math.abs(g.spread_line);
  return `${fav} -${s % 1 ? s.toFixed(1) : s.toFixed(0)} · total ${g.total_line}`;
}

function sideChance(e: Edge): { model: number | null; book: number | null } {
  if (e.side === 'under') return { model: e.prob_under ?? null, book: e.market_prob_over != null ? 1 - e.market_prob_over : null };
  if (e.side === 'yes') return { model: e.prob_over, book: e.price != null ? 1 / (1 + (e.price > 0 ? e.price / 100 : 100 / Math.abs(e.price))) : null };
  return { model: e.prob_over, book: e.market_prob_over ?? null };
}

function sideText(e: Edge): string {
  if (e.side === 'yes') return 'Anytime TD';
  return `${e.side === 'over' ? 'Over' : 'Under'} ${e.line} ${e.label}`;
}

function Trio({ model, vegas, blended }: { model: number; vegas: number; blended: number }) {
  const item = (label: string, v: number, strong = false) => (
    <span style={{ whiteSpace: 'nowrap' }}>
      <span style={{ color: theme.textMuted }}>{label} </span>
      <b style={{ color: strong ? theme.dataBlue : theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>{v.toFixed(1)}</b>
    </span>
  );
  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 12, margin: '2px 0' }}>
      {item('Model', model)}{item('Vegas', vegas)}{item('Blended', blended, true)}
    </div>
  );
}

function BetRow({ b, game, onOpen }: { b: Bet; game?: Game; onOpen?: () => void }) {
  const { model, book: bk } = sideChance(b);
  const opp = game ? (b.team === game.home ? game.away : game.home) : '';
  return (
    <div onClick={onOpen} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '8px 0', borderTop: `1px solid ${theme.border}`, cursor: onOpen ? 'pointer' : 'default' }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13.5, color: theme.textPrimary }}>
          <b>{b.player}</b> <span style={{ color: theme.textMuted }}>{b.position} · {b.team}{opp ? ` vs ${opp}` : ''}</span>
        </div>
        <div style={{ fontSize: 12.5, color: theme.textSecondary }}>
          <b style={{ color: theme.textPrimary }}>{sideText(b)}</b> · {odds(b.price)} {book(b.book)}
        </div>
        {b.side !== 'yes' && b.line != null && <Trio model={b.model ?? b.projection} vegas={b.line} blended={b.projection} />}
        <div style={{ fontSize: 11.5, color: theme.textMuted }}>
          Chance it hits: ours {pct(model)}{bk != null ? `, book ${pct(bk)}` : ''}{b.status ? ` · ${b.status}` : ''}
          {b.suspect && <span style={{ color: theme.warningText }}> · a gap this big often means news the model doesn't know — check before betting</span>}
        </div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div style={{ fontSize: 16, fontWeight: 800, color: b.suspect ? theme.warningText : theme.dataBlue }}>+{Math.round((b.ev || 0) * 100)}%</div>
        <div style={{ fontSize: 10.5, color: theme.textMuted }}>exp. return</div>
      </div>
    </div>
  );
}

function BetList({ title, note, bets, games, onOpen, initial = 8 }: {
  title: string; note: string; bets: Bet[]; games: Game[]; onOpen: (gid: string) => void; initial?: number;
}) {
  const [all, setAll] = useState(false);
  const byId = useMemo(() => Object.fromEntries(games.map((g) => [g.game_id, g])), [games]);
  const shown = all ? bets : bets.slice(0, initial);
  return (
    <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '12px 14px', marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
        <b style={{ color: theme.textPrimary, fontSize: 15 }}>{title}</b>
        <span style={{ fontSize: 11.5, color: theme.textMuted }}>{bets.length ? `${bets.length} · tap to open the game` : ''}</span>
      </div>
      <div style={{ fontSize: 12, color: theme.textSecondary, margin: '4px 0 2px', lineHeight: 1.5 }}>{note}</div>
      {!bets.length && <div style={{ fontSize: 12.5, color: theme.textMuted, paddingTop: 6 }}>Nothing clears the bar right now. Lines move through the week; check back.</div>}
      {shown.map((b) => <BetRow key={`${b.player}-${b.market}`} b={b} game={byId[b.game_id]} onOpen={() => onOpen(b.game_id)} />)}
      {bets.length > initial && (
        <button onClick={() => setAll(!all)} style={{ marginTop: 6, background: 'none', border: 'none', padding: 0, color: theme.dataBlue, fontSize: 12, cursor: 'pointer' }}>
          {all ? `Show top ${initial}` : `Show all ${bets.length}`}
        </button>
      )}
    </div>
  );
}

function FlowRow({ label, a, h, fmt = (n: number) => n.toFixed(1) }: { label: string; a: number; h: number; fmt?: (n: number) => string }) {
  return (
    <tr>
      <td style={{ padding: '4px 0', color: theme.textSecondary }}>{label}</td>
      <td style={{ padding: '4px 8px', textAlign: 'right', color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>{fmt(a)}</td>
      <td style={{ padding: '4px 0', textAlign: 'right', color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>{fmt(h)}</td>
    </tr>
  );
}

function GameCard({ g }: { g: Game }) {
  const homeWin = g.model_home_win ?? g.sim_home_win;
  const fav = homeWin >= 0.5 ? g.home : g.away;
  const favPct = homeWin >= 0.5 ? homeWin : 1 - homeWin;
  const A = g.teams.away; const H = g.teams.home;
  const passRate = (t: TeamFlow) => `${Math.round((100 * t.dropbacks) / Math.max(1, t.dropbacks + t.runs))}%`;
  const [lo, hi] = g.sim_margin_p10_p90;
  const rangeText = (m: number) => (m === 0 ? 'tie' : `${m > 0 ? g.home : g.away} by ${Math.abs(Math.round(m))}`);
  return (
    <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '12px 14px', marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
        <b style={{ color: theme.textPrimary, fontSize: 16 }}>{g.away} @ {g.home}</b>
        <span style={{ fontSize: 12, color: theme.textMuted }}>{kick(g.kickoff)} · {spreadText(g)}</span>
      </div>
      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', margin: '10px 0 8px' }}>
        <div>
          <div style={{ fontSize: 11, color: theme.textMuted }}>Win chance</div>
          <div style={{ fontSize: 20, fontWeight: 800, color: theme.textPrimary }}>{fav} {pct(favPct)}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: theme.textMuted }}>Projected score</div>
          <div style={{ fontSize: 20, fontWeight: 800, color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>
            {g.away} {A.sim_points.toFixed(0)} – {H.sim_points.toFixed(0)} {g.home}
          </div>
        </div>
        {g.model_total != null && (
          <div>
            <div style={{ fontSize: 11, color: theme.textMuted }}>Ratings model</div>
            <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 4 }}>
              {g.model_margin! >= 0 ? g.home : g.away} by {Math.abs(g.model_margin!).toFixed(1)}, total {g.model_total.toFixed(1)}
            </div>
          </div>
        )}
      </div>
      <div style={{ fontSize: 11.5, color: theme.textMuted, marginBottom: 8 }}>
        8 in 10 simulations land between {rangeText(lo)} and {rangeText(hi)}.
        {g.roof === 'outdoors' && g.wind != null && g.wind >= 15 ? ` Wind ${g.wind} mph.` : ''}
      </div>
      <table style={{ width: '100%', maxWidth: 380, borderCollapse: 'collapse', fontSize: 12.5 }}>
        <thead>
          <tr style={{ color: theme.textMuted, fontSize: 11 }}>
            <th style={{ textAlign: 'left', fontWeight: 400 }}>Game flow (simulated)</th>
            <th style={{ textAlign: 'right', fontWeight: 600, padding: '0 8px' }}>{g.away}</th>
            <th style={{ textAlign: 'right', fontWeight: 600 }}>{g.home}</th>
          </tr>
        </thead>
        <tbody>
          <FlowRow label="Offensive plays" a={A.plays} h={H.plays} fmt={(n) => n.toFixed(0)} />
          <FlowRow label="Time of possession" a={A.top_min} h={H.top_min} fmt={(n) => `${Math.floor(n)}:${String(Math.round((n % 1) * 60)).padStart(2, '0')}`} />
          <FlowRow label="Dropbacks" a={A.dropbacks} h={H.dropbacks} fmt={(n) => n.toFixed(0)} />
          <FlowRow label="Designed runs" a={A.runs} h={H.runs} fmt={(n) => n.toFixed(0)} />
          <tr>
            <td style={{ padding: '4px 0', color: theme.textSecondary }}>Pass rate</td>
            <td style={{ padding: '4px 8px', textAlign: 'right', color: theme.textPrimary }}>{passRate(A)}</td>
            <td style={{ padding: '4px 0', textAlign: 'right', color: theme.textPrimary }}>{passRate(H)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

type Col = { key: string; label: string; market?: string; td?: boolean };
const QB_COLS: Col[] = [
  { key: 'pass_yds', label: 'Pass yds', market: 'pass_yds' }, { key: 'pass_att', label: 'Att', market: 'pass_attempts' },
  { key: 'pass_cmp', label: 'Cmp', market: 'pass_completions' }, { key: 'pass_tds', label: 'TD', market: 'pass_tds' },
  { key: 'rush_yds', label: 'Rush yds', market: 'rush_yds' },
];
const SKILL_COLS: Col[] = [
  { key: 'rec', label: 'Rec', market: 'receptions' }, { key: 'rec_yds', label: 'Rec yds', market: 'reception_yds' },
  { key: 'rush_att', label: 'Car', market: 'rush_attempts' }, { key: 'rush_yds', label: 'Rush yds', market: 'rush_yds' },
  { key: 'anytime_td', label: 'TD', market: 'anytime_td', td: true },
];
const POS_ORDER: Record<string, number> = { QB: 0, RB: 1, FB: 1, WR: 2, TE: 3 };

function Cell({ p, c }: { p: Player; c: Col }) {
  const v = p.projection[c.key];
  const e = c.market ? p.lines[c.market] : undefined;
  if (v == null) return <td style={{ padding: '6px 6px', textAlign: 'center', color: theme.textMuted }}>—</td>;
  const flagged = !!e?.side;
  const tag = e ? (c.td ? odds(e.over_price) : flagged ? `${e.side === 'over' ? 'O' : 'U'} ${e.line}` : String(e.line)) : '';
  return (
    <td style={{ padding: '6px 6px', textAlign: 'center', verticalAlign: 'top' }}>
      <div style={{ fontWeight: 700, color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>{c.td ? pct(v) : v.toFixed(1)}</div>
      {e && (
        <div
          title={c.td ? `Best price ${odds(e.over_price)} at ${book(e.over_book ?? null)}`
            : `Model ${(e.model ?? e.projection).toFixed(1)} · Vegas ${e.line} · Blended ${e.projection.toFixed(1)} · over ${pct(e.prob_over)}${e.market_prob_over != null ? ` (book ${pct(e.market_prob_over)})` : ''}${flagged ? ` · ${e.side} ${odds(e.price)} at ${book(e.book)}, +${Math.round((e.ev || 0) * 100)}%` : ''}`}
          style={{
            fontSize: 10.5, marginTop: 2, borderRadius: 3, padding: '0 3px', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap',
            color: flagged ? theme.bgPage : theme.textMuted,
            background: flagged ? (e.tier === 'bet' ? theme.dataBlue : theme.textMuted) : 'transparent',
            fontWeight: flagged ? 700 : 400,
          }}
        >
          {tag}
        </div>
      )}
    </td>
  );
}

function PlayerTable({ title, rows, cols, isMobile }: { title: string; rows: Player[]; cols: Col[]; isMobile: boolean }) {
  if (!rows.length) return null;
  return (
    <div style={{ overflowX: 'auto', border: `1px solid ${theme.border}`, borderRadius: 8, marginBottom: 10 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, background: theme.bgCard }}>
        <thead>
          <tr style={{ color: theme.textSecondary, background: theme.bgCardHover }}>
            <th style={{ textAlign: 'left', padding: '7px 8px', position: 'sticky', left: 0, background: theme.bgCardHover }}>{title}</th>
            {cols.map((c) => <th key={c.key} style={{ padding: '7px 6px', whiteSpace: 'nowrap' }}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.player_id} style={{ borderTop: `1px solid ${theme.border}`, opacity: p.ruled_out ? 0.5 : 1 }}>
              <td style={{ padding: '6px 8px', position: 'sticky', left: 0, background: theme.bgCard, minWidth: isMobile ? 104 : 170 }}>
                <div style={{ color: theme.textPrimary, fontWeight: 600 }}>{p.player} <span style={{ color: theme.textMuted, fontWeight: 400, fontSize: 11 }}>{p.position}</span></div>
                <div style={{ fontSize: 10.5, color: p.status ? theme.warningText : theme.textMuted }}>
                  {p.status ? `${p.status}${p.injury ? ` · ${p.injury}` : ''}` : p.snap_pct != null ? `${Math.round(p.snap_pct * 100)}% of snaps` : ''}
                  {!p.status && p.sim_targets != null && p.sim_targets >= 1 ? ` · ${p.sim_targets.toFixed(1)} targets` : ''}
                </div>
              </td>
              {cols.map((c) => <Cell key={c.key} p={p} c={c} />)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TeamBlock({ team, players, isMobile }: { team: string; players: Player[]; isMobile: boolean }) {
  const rows = players.filter((p) => p.team === team);
  const qbs = rows.filter((p) => p.position === 'QB' && p.projection.pass_yds != null);
  const skill = rows
    .filter((p) => p.position !== 'QB' && ((p.projection.rec_yds ?? 0) + (p.projection.rush_yds ?? 0) >= 3 || Object.keys(p.lines).length))
    .sort((a, b) => (POS_ORDER[a.position] - POS_ORDER[b.position])
      || ((b.projection.rec_yds ?? 0) + (b.projection.rush_yds ?? 0)) - ((a.projection.rec_yds ?? 0) + (a.projection.rush_yds ?? 0)));
  return (
    <div style={{ marginBottom: 18 }}>
      <b style={{ color: theme.textPrimary, fontSize: 15, display: 'block', marginBottom: 6 }}>{team}</b>
      <PlayerTable title="Quarterback" rows={qbs} cols={QB_COLS} isMobile={isMobile} />
      <PlayerTable title="Skill players" rows={skill} cols={SKILL_COLS} isMobile={isMobile} />
    </div>
  );
}

interface RecordResp {
  accuracy: { player_games: number; weeks: number; mae: Record<string, { mae: number; n: number }> } | null;
  plays: { plays: number; wins: number; losses: number; win_pct: number | null; units: number; roi_pct: number } | null;
  watch: { plays: number; wins: number; losses: number; win_pct: number | null; units: number; roi_pct: number } | null;
  by_market: { market: string; label: string; plays: number; wins: number; losses: number; units: number; roi_pct: number }[];
}
const STAT_NAMES: Record<string, string> = {
  rec: 'receptions', rec_yds: 'receiving yds', rush_att: 'carries', rush_yds: 'rushing yds', pass_yds: 'passing yds',
  pass_att: 'pass attempts', pass_cmp: 'completions', pass_tds: 'passing TDs', rush_rec_yds: 'rush + rec yds',
};

function TrackRecord({ accuracy }: { accuracy?: Record<string, number[]> }) {
  const [rec, setRec] = useState<RecordResp | null>(null);
  useEffect(() => { getNFLProjectionRecord().then((r) => setRec(r.data)).catch(() => setRec(null)); }, []);
  const cell = { padding: '6px 8px', borderBottom: `1px solid ${theme.border}`, fontSize: 12 } as const;
  const line = (s: RecordResp['plays']) => s && (
    <><b>{s.wins}-{s.losses}</b>{s.win_pct != null && ` (${s.win_pct}%)`}, {s.units > 0 ? '+' : ''}{s.units} units ({s.roi_pct > 0 ? '+' : ''}{s.roi_pct}%)</>
  );
  return (
    <div style={{ marginTop: 26 }}>
      <h3 style={{ color: theme.textPrimary, marginBottom: 6 }}>Track record</h3>
      {accuracy && (
        <div style={{ fontSize: 12.5, color: theme.textSecondary, marginBottom: 10, lineHeight: 1.6 }}>
          Tested on every 2025 and 2026 game before going live (models trained only on earlier seasons): average miss of{' '}
          {accuracy.rec?.[1]} receptions, {accuracy.rec_yds?.[1]} receiving yds, {accuracy.rush_yds?.[1]} rushing yds (backs) and{' '}
          {accuracy.pass_yds?.[1]} passing yds — against {accuracy.rec?.[0]}, {accuracy.rec_yds?.[0]}, {accuracy.rush_yds?.[0]} and{' '}
          {accuracy.pass_yds?.[0]} for a player's recent average.
        </div>
      )}
      {(!rec || (!rec.accuracy && !rec.plays && !rec.watch)) && (
        <div style={{ fontSize: 12, color: theme.textMuted }}>Live grading starts once this week's games are final.</div>
      )}
      {rec?.accuracy && (
        <div style={{ fontSize: 12.5, color: theme.textSecondary, marginBottom: 10, lineHeight: 1.6 }}>
          Live, over {rec.accuracy.weeks} week{rec.accuracy.weeks === 1 ? '' : 's'} ({rec.accuracy.player_games} player-games): missed by{' '}
          {Object.entries(rec.accuracy.mae).filter(([s]) => STAT_NAMES[s]).map(([s, v]) => `${v.mae} ${STAT_NAMES[s]}`).join(', ')}.
        </div>
      )}
      {rec?.plays && <div style={{ fontSize: 13, color: theme.textPrimary, marginBottom: 4 }}>Best bets: {line(rec.plays)}</div>}
      {rec?.watch && <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 8 }}>Tracking-only flags: {line(rec.watch)}</div>}
      {!!rec?.by_market.length && (
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
      )}
    </div>
  );
}

export default function NFLProjections() {
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [gameId, setGameId] = useState<string | null>(null);
  const isMobile = useIsMobile();

  useEffect(() => {
    getNFLProjections()
      .then((r) => { setData(r.data); if (r.data.games?.length) setGameId(r.data.games[0].game_id); })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load projections.'))
      .finally(() => setLoading(false));
  }, []);

  const game = useMemo(() => data?.games.find((g) => g.game_id === gameId) || null, [data, gameId]);
  const gamePlayers = useMemo(() => (data?.players || []).filter((p) => p.game_id === gameId), [data, gameId]);
  const open = (gid: string) => { setGameId(gid); setTimeout(() => document.getElementById('nfl-game')?.scrollIntoView({ behavior: 'smooth' }), 50); };
  const ev = Math.round((data?.min_ev ?? 0.05) * 100);

  return (
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 1100, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>
        NFL Projections{data?.week ? <span style={{ color: theme.textMuted, fontWeight: 400, fontSize: 16 }}> · Week {data.week}</span> : null}
      </h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 12, lineHeight: 1.55 }}>
        Every game is played out 4,000 times, snap by snap, with the score, clock, field position and down
        tracked the whole way. A team that falls behind throws more and hurries; a team ahead runs and
        bleeds clock — so plays, time of possession and each player's share of the ball <b style={{ color: theme.textPrimary }}>in
        that situation</b> come out of the game script, not a season average. Player numbers blend that simulation
        with a model of recent role, snap share and matchup. Each game is anchored to its Vegas total and spread:
        neither of our game models beat the betting line in testing, so game lines aren't flagged as bets.
      </div>

      {data?.lines_as_of && <OddsDisclaimer fetchedAt={data.lines_as_of} compact={isMobile} />}
      {loading && <LoadingSpinner />}
      {error && <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>{error}</div>}
      {!loading && !error && !data?.games.length && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40 }}>No projections yet — they publish with the morning NFL update.</div>
      )}

      {!!data?.games.length && (
        <>
          <BetList
            title="Best bets this week" bets={data.best_bets} games={data.games} onOpen={open}
            note={`Receptions and receiving yards where the model's chance beats the price by ${ev}%+ and the book's own fair chance by ${Math.round((data.min_prob_edge ?? 0.08) * 100)} points. Our number is blended 50/50 with the line before it's priced — the mix beat either one alone in testing — so a flag means a real disagreement, not noise. These are the markets that held up against closing lines.`}
          />
          <BetList
            title="Also flagged — tracking only" bets={data.watch} games={data.games} onOpen={open} initial={4}
            note="Rushing, passing and anytime-TD spots that clear the same bar. For these the line itself was more accurate than our model in testing, so our number leans mostly on the line and they're graded separately until the live record says otherwise."
          />
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4, marginBottom: 14 }}>
            {data.games.map((g) => (
              <button
                key={g.game_id} onClick={() => setGameId(g.game_id)}
                style={{
                  flex: '0 0 auto', padding: '8px 12px', borderRadius: 6, cursor: 'pointer', textAlign: 'left',
                  background: g.game_id === gameId ? theme.bgCardHover : theme.bgCard, color: theme.textPrimary,
                  border: `1px solid ${g.game_id === gameId ? theme.dataBlue : theme.border}`,
                }}
              >
                <div style={{ fontWeight: 700, fontSize: 14 }}>{g.away} @ {g.home}</div>
                <div style={{ fontSize: 11, color: theme.textSecondary }}>{kick(g.kickoff)}</div>
              </button>
            ))}
          </div>
        </>
      )}

      {game && (
        <div id="nfl-game">
          <GameCard g={game} />
          <div style={{ fontSize: 11.5, color: theme.textMuted, marginBottom: 10 }}>
            Under each number: the main line across books. Blue = best bet; grey = tracking-only flag. TD column is the chance of scoring, with the best price under it.
          </div>
          {[game.away, game.home].map((t) => <TeamBlock key={t} team={t} players={gamePlayers} isMobile={isMobile} />)}
        </div>
      )}

      <TrackRecord accuracy={data?.accuracy} />
      <div style={{ marginTop: 18, fontSize: 12, color: theme.textMuted, lineHeight: 1.6 }}>
        Projections are estimates, not guarantees. Players listed Out or Doubtful are left out, and the player
        model accounts for teammates who've newly dropped out of the lineup. The injury report is re-checked every
        time the page loads. Interceptions, longest-play and kicking props aren't projected.
      </div>
    </div>
  );
}
