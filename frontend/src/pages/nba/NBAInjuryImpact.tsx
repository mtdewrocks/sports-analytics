import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { getNBAInjuryImpact } from '../../api/nba';
import LoadingSpinner from '../../components/LoadingSpinner';
import SegmentedToggle from '../../components/SegmentedToggle';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

/**
 * NBA Injury Impact -- everyone on the injury report who plays a real role,
 * and the teammates whose numbers move when he sits (app/data/nba_injury_impact.py).
 * The In/Out page answers "what happens to X without Y" one pair at a time;
 * this runs that comparison for the whole report and puts tonight's games first.
 */

type Stat = 'min' | 'pts' | 'reb' | 'ast' | 'fga' | 'pra';

interface Mate {
  player: string;
  games_with: number;
  games_without: number;
  with: Record<Stat, number>;
  without: Record<Stat, number>;
  delta: Record<Stat, number>;
  flags: Stat[];
}

interface Card {
  player: string;
  team: string;
  status: string | null;
  detail: string | null;
  updated: string | null;
  role: { games: number; min: number | null; pts: number | null };
  next_game: { date: string; opponent: string; home: boolean; start_utc: string; today: boolean } | null;
  basis: 'current' | 'both';
  basis_label: string | null;
  also_out: string[];
  beneficiaries: Mate[];
}

interface Resp {
  season: string | null;
  updated_at: string | null;
  stat_labels: Record<Stat, string>;
  players: Card[];
}

const SHORT: Record<Stat, string> = { min: 'MIN', pts: 'PTS', reb: 'REB', ast: 'AST', fga: 'FGA', pra: 'PRA' };
const SHOWN: Stat[] = ['min', 'pts', 'reb', 'ast', 'fga'];

function signed(n: number): string {
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}`;
}

function gameLabel(g: Card['next_game']): string | null {
  if (!g) return null;
  const when = g.today
    ? new Date(g.start_utc).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
    : new Date(`${g.date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  return `${g.today ? 'Tonight' : 'Next'} ${g.home ? 'vs' : '@'} ${g.opponent} · ${when}`;
}

function MateRow({ m, isMobile }: { m: Mate; isMobile: boolean }) {
  return (
    <div style={{ padding: '8px 0', borderTop: `1px solid ${theme.border}` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
        <b style={{ color: theme.textPrimary, fontSize: 13 }}>{m.player}</b>
        <span style={{ fontSize: 11, color: theme.textMuted, whiteSpace: 'nowrap' }}>
          {m.games_with} with / {m.games_without} without
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${isMobile ? 3 : 5}, 1fr)`, gap: 6 }}>
        {SHOWN.map((s) => {
          const d = m.delta[s];
          const flagged = m.flags.includes(s);
          return (
            <div key={s} style={{
              background: theme.bgPage, borderRadius: 4, padding: '4px 6px',
              border: `1px solid ${flagged ? theme.dataBlue : theme.border}`,
            }}>
              <div style={{ fontSize: 10, color: theme.textMuted }}>{SHORT[s]}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: flagged ? theme.dataBlue : d < 0 ? theme.textSecondary : theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>
                {signed(d)}
              </div>
              <div style={{ fontSize: 10, color: theme.textMuted, fontVariantNumeric: 'tabular-nums' }}>
                {m.with[s].toFixed(1)} → {m.without[s].toFixed(1)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function InjuryCard({ c, isMobile }: { c: Card; isMobile: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const lead = c.beneficiaries[0];
  const shown = expanded ? c.beneficiaries : c.beneficiaries.slice(0, 3);
  const hidden = c.beneficiaries.length - shown.length;
  const out = c.status === 'Out';
  const statusColor = out ? theme.warningText : theme.textSecondary;
  return (
    <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: theme.textPrimary }}>
            {c.player} <span style={{ color: theme.textMuted, fontWeight: 500 }}>· {c.team}</span>
          </div>
          <div style={{ fontSize: 12, color: theme.textSecondary }}>
            <b style={{ color: statusColor }}>{c.status}</b>{c.detail ? ` · ${c.detail}` : ''}
            {c.role.min != null && ` · usually ${c.role.min} min, ${c.role.pts} pts`}
          </div>
        </div>
        {c.next_game && (
          <div style={{ fontSize: 12, color: c.next_game.today ? theme.textPrimary : theme.textSecondary, fontWeight: c.next_game.today ? 700 : 400 }}>
            {gameLabel(c.next_game)}
          </div>
        )}
      </div>

      {lead && (
        <div style={{ fontSize: 13, color: theme.textSecondary, margin: '10px 0 4px', lineHeight: 1.5 }}>
          Without him, <b style={{ color: theme.textPrimary }}>{lead.player}</b> has averaged{' '}
          <b style={{ color: theme.dataBlue }}>{signed(lead.delta.pts)} points</b> and{' '}
          <b style={{ color: theme.dataBlue }}>{signed(lead.delta.min)} minutes</b>
          {' '}({lead.with.pts.toFixed(1)} → {lead.without.pts.toFixed(1)} pts).
        </div>
      )}

      {shown.map((m) => <MateRow key={m.player} m={m} isMobile={isMobile} />)}
      {(hidden > 0 || expanded) && c.beneficiaries.length > 3 && (
        <button
          onClick={() => setExpanded(!expanded)}
          style={{ marginTop: 6, background: 'none', border: 'none', padding: 0, color: theme.dataBlue, fontSize: 12, cursor: 'pointer' }}
        >
          {expanded ? 'Show fewer' : `Show ${hidden} more teammate${hidden === 1 ? '' : 's'}`}
        </button>
      )}

      <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 8, lineHeight: 1.5 }}>
        Based on {c.basis_label || 'this season'} games with {c.team}
        {c.basis === 'both' && ' — not enough games without him this season yet, so last season is included'}.
        {c.also_out.length > 0 && <> Also out: {c.also_out.join(', ')} — their absences overlap, so these numbers partly reflect them too.</>}
      </div>
    </div>
  );
}

export default function NBAInjuryImpact() {
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [scope, setScope] = useState<'today' | 'all'>('today');
  const [statusFilter, setStatusFilter] = useState<'all' | 'out'>('all');
  const isMobile = useIsMobile();

  useEffect(() => {
    getNBAInjuryImpact()
      .then((r) => setData(r.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load the injury report.'))
      .finally(() => setLoading(false));
  }, []);

  const todayCount = useMemo(() => (data?.players || []).filter((c) => c.next_game?.today).length, [data]);
  const cards = useMemo(() => (data?.players || []).filter((c) =>
    (scope === 'all' || todayCount === 0 || c.next_game?.today)
    && (statusFilter === 'all' || c.status === 'Out')), [data, scope, statusFilter, todayCount]);

  return (
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 900, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NBA Injury Impact</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 12, lineHeight: 1.55 }}>
        Every player on the injury report who plays a real role, and the teammates whose numbers jump
        when he sits — minutes, points, rebounds, assists and shots, comparing games with him against
        games without him{data?.season ? ` (${data.season} season)` : ''}. Boxes outlined in blue are big moves.
        For any other pairing, use <Link to="/nba/in-out" style={{ color: theme.dataBlue }}>In/Out</Link>.
      </div>
      {data?.updated_at && (
        <div style={{ fontSize: 12, color: theme.textMuted, marginBottom: 12 }}>
          Injury report updated {new Date(data.updated_at).toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })}.
          Statuses change up to tip-off — confirm before betting.
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
        <SegmentedToggle
          value={scope}
          onChange={setScope}
          options={[{ value: 'today', label: `Playing tonight${todayCount ? ` (${todayCount})` : ''}` }, { value: 'all', label: 'Everyone' }]}
        />
        <SegmentedToggle
          value={statusFilter}
          onChange={setStatusFilter}
          options={[{ value: 'all', label: 'Out + day-to-day' }, { value: 'out', label: 'Out only' }]}
        />
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>{error}</div>
      )}
      {!loading && !error && cards.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40 }}>
          No injured rotation players{scope === 'today' ? ' on tonight\'s teams' : ''} with enough games to compare.
        </div>
      )}
      <div style={{ display: 'grid', gap: 12 }}>
        {cards.map((c) => <InjuryCard key={`${c.team}-${c.player}`} c={c} isMobile={isMobile} />)}
      </div>
      <div style={{ marginTop: 20, fontSize: 12, color: theme.textMuted, lineHeight: 1.6 }}>
        Averages, not projections: a handful of "without" games can swing on one blowout or a
        coach's choice. The game counts on each row tell you how much to trust it.
      </div>
    </div>
  );
}
