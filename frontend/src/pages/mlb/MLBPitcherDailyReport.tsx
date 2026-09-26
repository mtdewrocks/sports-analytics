import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { getMLBPitcherDailyReport } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

import LineupVsUsual from '../../components/LineupVsUsual';
import type { VsUsual } from '../../components/LineupVsUsual';

interface PitcherRow {
  /** Today's opposing lineup vs its usual one against this pitcher's hand. */
  vs_usual: VsUsual | null;
  /** Derived for the desktop table: today's lineup wOBA minus usual, in points. */
  vs_usual_pts?: number | null;
  player: string;
  team: string;
  opposing_team: string;
  games: number;
  avg_outs: number | null;
  avg_hits: number | null;
  avg_er: number | null;
  avg_so: number | null;
  avg_bb: number | null;
  opp_avg: number | null;
  opp_k_pct: number | null;
  opp_bb_pct: number | null;
  high_k_hitter: number | null;
  high_bb_hitter: number | null;
  high_avg_hitter: number | null;
  low_avg_hitter: number | null;
  high_iso_hitter: number | null;
  high_woba_hitter: number | null;
}

type SortKey = keyof PitcherRow;

const columns: { key: SortKey; label: string; align?: 'left' | 'right' }[] = [
  { key: 'player', label: 'Pitcher', align: 'left' },
  { key: 'team', label: 'Team', align: 'left' },
  { key: 'opposing_team', label: 'Opponent', align: 'left' },
  { key: 'games', label: 'GP' },
  { key: 'avg_outs', label: 'Outs' },
  { key: 'avg_hits', label: 'H' },
  { key: 'avg_er', label: 'ER' },
  { key: 'avg_so', label: 'SO' },
  { key: 'avg_bb', label: 'BB' },
  { key: 'opp_avg', label: 'Opp AVG' },
  { key: 'opp_k_pct', label: 'Opp K%' },
  { key: 'opp_bb_pct', label: 'Opp BB%' },
  { key: 'vs_usual_pts', label: 'vs Usual' },
  { key: 'high_k_hitter', label: 'Hi K' },
  { key: 'high_bb_hitter', label: 'Hi BB' },
  { key: 'high_avg_hitter', label: 'Hi Avg' },
  { key: 'low_avg_hitter', label: 'Lo Avg' },
  { key: 'high_iso_hitter', label: 'Hi ISO' },
  { key: 'high_woba_hitter', label: 'Hi wOBA' },
];

/**
 * The six "extreme" fields are NOT stat values -- each is a COUNT of hitters in
 * today's opposing lineup clearing a fixed threshold (see HITTER_FLAG_THRESHOLDS
 * in backend/app/data/mlb.py). high_k_hitter = 4 means four of those nine
 * strike out at 20% or better.
 *
 * That's why they render as a pill row rather than more columns: they're single
 * digits out of nine, so all six fit on one line, and each one has a direction.
 * `favoursPitcher` drives the colour -- blue where the count is good news for
 * the pitcher, red where it's good news for the hitters.
 */
const LINEUP_FLAGS: { key: keyof PitcherRow; label: string; favoursPitcher: boolean }[] = [
  { key: 'high_k_hitter',    label: 'high K',       favoursPitcher: true },
  { key: 'low_avg_hitter',   label: 'low average',  favoursPitcher: true },
  { key: 'high_bb_hitter',   label: 'high BB',      favoursPitcher: false },
  { key: 'high_avg_hitter',  label: 'high average', favoursPitcher: false },
  { key: 'high_iso_hitter',  label: 'high ISO',     favoursPitcher: false },
  { key: 'high_woba_hitter', label: 'high wOBA',    favoursPitcher: false },
];

/** One labelled group inside a pitcher's card. */
function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 9.5, color: theme.textMuted, textTransform: 'uppercase',
      letterSpacing: '0.06em', marginTop: 9, marginBottom: 1,
    }}>
      {children}
    </div>
  );
}

function PitcherCard({ r }: { r: PitcherRow }) {
  const hasForm = r.avg_outs != null || r.avg_so != null;
  const hasOpponent = r.opp_avg != null || r.opp_k_pct != null;
  const flags = LINEUP_FLAGS.map((f) => ({ ...f, count: r[f.key] as number | null }))
    .filter((f) => f.count != null);

  // Always one decimal, so a column of per-start averages lines up: the API
  // rounds to 1dp but JSON drops the trailing zero, which renders 2.0 as "2"
  // sitting next to "2.4".
  const fmt = (v: number | null | undefined, suffix = '') => (v == null ? '—' : `${v.toFixed(1)}${suffix}`);
  // Batting averages are conventionally written without the leading zero.
  const fmtAvg = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(3).replace(/^0/, ''));

  return (
    <div style={{ background: theme.bgCard, borderRadius: 8, padding: '12px 14px', marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 14, color: theme.textPrimary }}>
          <span style={{ fontWeight: 700 }}>{r.player}</span>
          <span style={{ color: theme.textMuted, fontSize: 11, marginLeft: 6 }}>{r.team}</span>
        </span>
        <span style={{ color: theme.textMuted, fontSize: 11, flexShrink: 0 }}>vs {r.opposing_team}</span>
      </div>

      <GroupLabel>{r.games ? `Form · last ${r.games} starts` : 'Form'}</GroupLabel>
      {hasForm ? (
        <div style={{ fontSize: 12, color: theme.textSecondary, fontVariantNumeric: 'tabular-nums' }}>
          {fmt(r.avg_outs)} outs · <span style={{ color: theme.textPrimary, fontWeight: 700 }}>{fmt(r.avg_so)}</span> SO
          {' · '}{fmt(r.avg_hits)} H · {fmt(r.avg_er)} ER · {fmt(r.avg_bb)} BB
        </div>
      ) : (
        <div style={{ fontSize: 12, color: theme.textMuted }}>No recent starts yet.</div>
      )}

      <GroupLabel>Opposing lineup average</GroupLabel>
      {hasOpponent ? (
        <div style={{ fontSize: 12, color: theme.textSecondary, fontVariantNumeric: 'tabular-nums' }}>
          {fmtAvg(r.opp_avg)} AVG
          {' · '}
          <span style={{
            fontWeight: 700,
            color: r.opp_k_pct == null ? theme.textSecondary
              : r.opp_k_pct >= 23 ? theme.dataBlue
              : r.opp_k_pct <= 19 ? theme.dataRed
              : theme.textPrimary,
          }}>
            {fmt(r.opp_k_pct, '%')}
          </span> K
          {' · '}{fmt(r.opp_bb_pct, '%')} BB
          {r.vs_usual && <LineupVsUsual v={r.vs_usual} compact />}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: theme.textMuted }}>Waiting on today's lineup.</div>
      )}

      {flags.length > 0 && (
        <>
          <GroupLabel>Hitters in that lineup · of 9</GroupLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 4 }}>
            {flags.map((f) => (
              <span
                key={String(f.key)}
                style={{
                  fontSize: 10.5, fontWeight: 600, padding: '3px 7px', borderRadius: 4,
                  fontVariantNumeric: 'tabular-nums',
                  background: f.count === 0 ? theme.bgPage
                    : f.favoursPitcher ? 'rgba(107,168,240,0.15)' : 'rgba(244,87,63,0.15)',
                  color: f.count === 0 ? theme.textMuted
                    : f.favoursPitcher ? theme.dataBlue : theme.dataRed,
                }}
              >
                {f.count} {f.label}
              </span>
            ))}
          </div>
        </>
      )}

      {/* An explicit link rather than making the whole card tappable, so a
          scroll that lands on a card can't navigate away by accident. */}
      <div style={{
        display: 'flex', justifyContent: 'flex-end',
        marginTop: 10, paddingTop: 9, borderTop: `1px solid ${theme.border}`,
      }}>
        <Link
          to={`/mlb/matchup?pitcher=${encodeURIComponent(r.player)}`}
          style={{ color: theme.accent, fontSize: 12, fontWeight: 600, textDecoration: 'none', padding: '2px 0' }}
        >
          Pitcher matchup →
        </Link>
      </div>
    </div>
  );
}

export default function MLBPitcherDailyReport() {
  const [rows, setRows] = useState<PitcherRow[]>([]);
  const [date, setDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('player');
  const [sortDesc, setSortDesc] = useState(false);
  const isMobile = useIsMobile();

  useEffect(() => {
    getMLBPitcherDailyReport()
      .then((res) => {
        setDate(res.data.date);
        setRows(res.data.pitchers.map((p: PitcherRow) => ({
          ...p,
          vs_usual_pts: p.vs_usual ? Math.round(p.vs_usual.diff.woba * 1000) : null,
        })));
      })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to fetch pitcher report.'))
      .finally(() => setLoading(false));
  }, []);

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'string') return sortDesc ? String(bv).localeCompare(av) : av.localeCompare(String(bv));
      return sortDesc ? (bv as number) - (av as number) : (av as number) - (bv as number);
    });
    return copy;
  }, [rows, sortKey, sortDesc]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      setSortDesc(false);
    }
  };

  return (
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 1300, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>MLB Pitcher Daily Report</h2>
      {date && (
        <div style={{ fontSize: 14, color: theme.textPrimary, fontWeight: 600, marginBottom: 4 }}>
          {new Date(date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
        </div>
      )}
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 20 }}>
        Every starting pitcher on today's slate -- recent-form averages (last up to 10 starts) alongside
        today's opposing lineup's toughness. Opponent-lineup figures show a dash until that specific
        game's lineup has posted; a pitcher's own recent-form stats appear as soon as they're announced
        as today's starter.{!isMobile && ' Click a column to sort.'}
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {!loading && !error && rows.length === 0 && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40 }}>
          No starting pitchers found for today's slate.
        </div>
      )}

      {/* Mobile: one card per starter, three labelled groups, no controls.
          Eighteen columns can't be scanned on a phone, and making the sort the
          primary control would mean picking a stat before the page tells you
          anything -- so instead every card carries all three groups and the
          order stays as it is on desktop (alphabetical). */}
      {!loading && !error && rows.length > 0 && isMobile && (
        <div>
          {sorted.map((r) => <PitcherCard key={r.player} r={r} />)}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', marginTop: 12, fontSize: 11, color: theme.textSecondary }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 11, height: 11, borderRadius: 2, background: 'rgba(107,168,240,0.6)' }} /> favours the pitcher
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 11, height: 11, borderRadius: 2, background: 'rgba(244,87,63,0.6)' }} /> favours the hitters
            </span>
          </div>
        </div>
      )}

      {!loading && !error && rows.length > 0 && !isMobile && (
        <div style={{ background: theme.bgCard, borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.4)', overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', fontSize: 13, minWidth: 1200 }}>
            <thead>
              <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                {columns.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    style={{
                      padding: '9px 10px', textAlign: col.align ?? 'right', cursor: 'pointer',
                      whiteSpace: 'nowrap', userSelect: 'none',
                    }}
                  >
                    {col.label}{sortKey === col.key ? (sortDesc ? ' ▼' : ' ▲') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr key={r.player} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage, color: theme.textPrimary }}>
                  <td style={{ padding: '7px 10px', fontWeight: 600 }}>{r.player}</td>
                  <td style={{ padding: '7px 10px', color: theme.textSecondary }}>{r.team}</td>
                  <td style={{ padding: '7px 10px', color: theme.textSecondary }}>{r.opposing_team}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.games}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.avg_outs ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.avg_hits ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.avg_er ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.avg_so ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.avg_bb ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.opp_avg ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.opp_k_pct ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.opp_bb_pct ?? '—'}</td>
                  <td
                    title={r.vs_usual?.missing.length ? `Missing: ${r.vs_usual.missing.map((m) => m.player).join(', ')}` : undefined}
                    style={{
                      padding: '7px 10px', textAlign: 'right',
                      color: r.vs_usual_pts == null || Math.abs(r.vs_usual_pts) < 15 ? theme.textSecondary
                        : r.vs_usual_pts < 0 ? theme.accent : theme.dataRed,
                    }}
                  >
                    {r.vs_usual_pts == null ? '—' : `${r.vs_usual_pts > 0 ? '+' : ''}${r.vs_usual_pts}`}
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.high_k_hitter ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.high_bb_hitter ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.high_avg_hitter ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.low_avg_hitter ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.high_iso_hitter ?? '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>{r.high_woba_hitter ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 16, textAlign: 'center' }}>
        {isMobile ? '"Hitters in that lineup"' : '"Hi/Lo X" columns'} count{isMobile ? 's' : ''} how many opposing
        batters clear a fixed threshold (e.g. K% ≥ 20, AVG ≥ .270) against this pitcher's specific throwing
        hand -- not a ranking relative to today's other games.
      </div>
    </div>
  );
}
