import React, { useState, useEffect } from 'react';
import { getMLBBullpenTeams, getMLBBullpen } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import StatCard from '../../components/StatCard';
import FilterPanel from '../../components/FilterPanel';
import { usePanelLayout } from '../../components/filterStyles';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

interface DayCell {
  pitches: number;
  ip: string;
  h: number;
  er: number;
  bb: number;
}

interface Reliever {
  pitcher_id: number;
  name: string;
  role: string;
  hand: string;
  era: number | null;
  whip: number | null;
  k_pct: number | null;
  bb_pct: number | null;
  days: (DayCell | null)[];
}

interface KpiWindow {
  pitches: number;
  ip: string;
  level: 'fresh' | 'neutral' | 'tired';
}

interface BullpenData {
  team: string;
  days: string[];
  kpis: { '1_day': KpiWindow; '3_day': KpiWindow; '7_day': KpiWindow };
  relievers: Reliever[];
  freshness: 'fresh' | 'neutral' | 'tired' | 'unknown';
}

const cardStyle: React.CSSProperties = {
  background: theme.bgCard,
  borderRadius: 8,
  boxShadow: '0 2px 12px rgba(0,0,0,0.4)',
  marginBottom: 20,
  overflow: 'hidden',
};
const cardHeaderStyle: React.CSSProperties = {
  background: theme.bgCardHover,
  color: theme.textPrimary,
  padding: '10px 16px',
  fontWeight: 700,
  fontSize: 14,
  textAlign: 'center',
};

// Black text on these fills, not white -- verified via contrast check:
// white-on-fill fails (2.5-3.3:1) since these colors were tuned to be
// readable AS TEXT on a dark card, not as a solid fill with white on top.
// Black comfortably passes (6.3-8.5:1) on all three.
const FRESHNESS_COLOR: Record<string, string> = {
  fresh: theme.dataBlue,
  neutral: '#9ca3af',
  tired: theme.dataRed,
  unknown: theme.textMuted,
};

function FreshBadge({ level }: { level: string }) {
  const color = FRESHNESS_COLOR[level] ?? FRESHNESS_COLOR.unknown;
  return (
    <span style={{
      background: color, color: '#000000', fontWeight: 700, fontSize: 11,
      padding: '3px 10px', borderRadius: 4, textTransform: 'uppercase', letterSpacing: 0.5,
    }}>
      {level}
    </span>
  );
}

// Same reasoning as FRESHNESS_COLOR above -- black text renders on top of
// these cells (see the table body below), not white.
function loadCellColor(pitches: number | undefined) {
  if (!pitches) return theme.bgCardHover;
  if (pitches <= 15) return theme.dataBlue;
  if (pitches <= 22) return '#9ca3af';
  return theme.dataRed;
}

/** "2026-09-12" -> "9/12". Anything else is passed through, since the API
 *  decides this label and it isn't guaranteed to be ISO. */
function shortDay(label: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(label);
  if (!m) return label;
  return `${parseInt(m[2], 10)}/${parseInt(m[3], 10)}`;
}

/**
 * The day columns of the workload table, as a strip inside one pitcher's card.
 *
 * The day grid is the reason to open this page and it's the half that falls off
 * a phone screen, so rather than dropping it, each pitcher's row of days
 * becomes a pill strip: worked-versus-rested reads as a shape before you read a
 * number, and the dates sit above the pills so a gap is anchored to a real day
 * rather than just being "three columns back".
 */
function DayStrip({ days, cells }: { days: string[]; cells: (DayCell | null)[] }) {
  return (
    <div style={{ display: 'flex', gap: 4, marginTop: 9, overflowX: 'auto', scrollbarWidth: 'none' }}>
      {days.map((d, i) => {
        const cell = cells[i] ?? null;
        return (
          <div key={d} style={{ flex: '1 0 42px', minWidth: 42, textAlign: 'center' }}>
            <div style={{ fontSize: 9, color: theme.textMuted, marginBottom: 3, whiteSpace: 'nowrap' }}>
              {shortDay(d)}
            </div>
            <div
              title={cell ? `${cell.pitches}p · ${cell.ip} IP · ${cell.h}H ${cell.er}ER ${cell.bb}BB` : 'did not pitch'}
              style={{
                borderRadius: 4, padding: '5px 0', fontSize: 11, fontWeight: 700,
                fontVariantNumeric: 'tabular-nums',
                background: cell ? loadCellColor(cell.pitches) : theme.bgPage,
                color: cell ? '#000000' : theme.textMuted,
              }}
            >
              {cell ? cell.pitches : '—'}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Worked 3 of the last 4 days is the availability signal the desktop grid
 *  leaves you to infer by counting across a row. */
function workloadFlag(cells: (DayCell | null)[]): string | null {
  const recent = cells.slice(-4);
  const worked = recent.filter(Boolean).length;
  if (worked >= 3) return `Pitched ${worked} of the last ${recent.length} days — likely unavailable`;
  return null;
}

export default function MLBBullpen() {
  const [teams, setTeams] = useState<string[]>([]);
  const [loadingTeams, setLoadingTeams] = useState(true);
  const [selectedTeam, setSelectedTeam] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<BullpenData | null>(null);
  const isMobile = useIsMobile();
  const panelLayout = usePanelLayout();

  useEffect(() => {
    setLoadingTeams(true);
    getMLBBullpenTeams()
      .then((res) => setTeams(res.data))
      .catch(() => setTeams([]))
      .finally(() => setLoadingTeams(false));
  }, []);

  const fetchBullpen = async (team: string) => {
    if (!team) return;
    setLoading(true);
    setError('');
    setData(null);
    try {
      const res = await getMLBBullpen(team);
      setData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch bullpen data.');
    } finally {
      setLoading(false);
    }
  };

  const days = data?.days ?? [];
  const relievers = data?.relievers ?? [];
  const kpis = data?.kpis;

  return (
    <div style={{ ...panelLayout, overflow: isMobile ? 'visible' : 'hidden', background: theme.bgPage }}>

      {/* ── Team picker ── */}
      <FilterPanel title="Bullpen Usage" width={220}>
        <div style={{ color: theme.textSecondary, fontSize: 12, fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Team</div>
        {loadingTeams ? (
          <div style={{ color: theme.textSecondary, fontSize: 12, padding: '8px 4px' }}>Loading teams…</div>
        ) : (
          <SearchDropdown
            players={teams}
            value={selectedTeam}
            onSelect={(t) => { setSelectedTeam(t); fetchBullpen(t); }}
            placeholder="Search team..."
            inputStyle={{ padding: '9px 10px', fontSize: 14, width: '100%', boxSizing: 'border-box' }}
          />
        )}
      </FilterPanel>

      {/* ── Main Content ── */}
      <div style={{
        flex: 1,
        overflowY: isMobile ? 'visible' : 'auto',
        padding: isMobile ? 16 : '20px 24px',
        background: theme.bgPage,
      }}>

        {loading && <LoadingSpinner />}
        {error && (
          <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
            {error}
          </div>
        )}

        {!loading && data && (
          <>
            {/* ── Header + freshness badge ── */}
            <div style={{ ...cardStyle }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px' }}>
                <div style={{ fontWeight: 700, fontSize: 18, color: theme.textPrimary }}>{data.team} — Bullpen</div>
                <FreshBadge level={data.freshness} />
              </div>
            </div>

            {/* ── KPI strip ── */}
            {kpis && (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: isMobile ? 8 : 16, marginBottom: 8 }}>
                  {([
                    { label: isMobile ? '1 Day' : 'Last 1 Day', k: kpis['1_day'] },
                    { label: isMobile ? '3 Days' : 'Last 3 Days', k: kpis['3_day'] },
                    { label: isMobile ? '7 Days' : 'Last 7 Days', k: kpis['7_day'] },
                  ] as const).map(({ label, k }) => (
                    <div key={label} style={{ ...cardStyle, margin: 0, padding: isMobile ? '10px 9px' : '14px 16px' }}>
                      <div style={{ fontSize: isMobile ? 10 : 11, color: theme.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: isMobile ? 18 : 22, fontWeight: 700, color: theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>
                        {k.pitches}<span style={{ fontSize: isMobile ? 11 : 13, fontWeight: 400, color: theme.textSecondary }}> {isMobile ? 'p' : 'pitches'}</span>
                      </div>
                      <div style={{ fontSize: isMobile ? 12 : 14, color: theme.textSecondary, marginBottom: 8 }}>{k.ip} IP</div>
                      <FreshBadge level={k.level} />
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 11, color: theme.textMuted, fontStyle: 'italic', marginBottom: 20 }}>
                  Fresh/Neutral/Tired reflects the bottom 25%, middle 50%, and top 25% of real 2026 league-wide
                  bullpen workload -- calculated separately for each window, since a 7-day average naturally
                  runs in a narrower range than a single day's total.
                </div>
              </>
            )}

            {/* ── Workload, as cards on a phone ── */}
            {relievers.length > 0 && isMobile && (
              <div>
                <div style={{
                  color: theme.textSecondary, fontSize: 11, textTransform: 'uppercase',
                  letterSpacing: 0.5, marginBottom: 8,
                }}>
                  Reliever Workload
                </div>
                {relievers.map((r) => {
                  const flag = workloadFlag(r.days);
                  return (
                    <StatCard
                      key={r.pitcher_id}
                      title={<span style={{ fontWeight: 700 }}>{r.name}{r.hand ? ` (${r.hand})` : ''}</span>}
                      titleAside={r.role}
                      value={r.era ?? '—'}
                      valueLabel="ERA"
                      valueColor={r.era != null && r.era < 3 ? theme.dataBlue : theme.textPrimary}
                      meta={[
                        <>{r.whip ?? '—'} WHIP</>,
                        <>{r.k_pct != null ? `${r.k_pct}%` : '—'} K</>,
                        <>{r.bb_pct != null ? `${r.bb_pct}%` : '—'} BB</>,
                      ]}
                      footer={flag}
                      footerColor={flag ? theme.dataRed : undefined}
                    >
                      <DayStrip days={days} cells={r.days} />
                    </StatCard>
                  );
                })}
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', padding: '4px 2px 0', fontSize: 11, color: theme.textSecondary }}>
                  <span>Load:</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: theme.dataBlue, display: 'inline-block', borderRadius: 2 }} /> ≤15p</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: '#9ca3af', display: 'inline-block', borderRadius: 2 }} /> 16–22p</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: theme.dataRed, display: 'inline-block', borderRadius: 2 }} /> 23p+</span>
                </div>
              </div>
            )}

            {/* ── Workload table ── */}
            {relievers.length > 0 && !isMobile && (
              <div style={cardStyle}>
                <div style={cardHeaderStyle}>Reliever Workload</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ borderCollapse: 'collapse', fontSize: 12, minWidth: 780 }}>
                    <thead>
                      <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                        <th style={{ padding: '8px 12px', textAlign: 'left', minWidth: 130 }}>Pitcher</th>
                        <th style={{ padding: '8px 8px' }}>ERA</th>
                        <th style={{ padding: '8px 8px' }}>WHIP</th>
                        <th style={{ padding: '8px 8px' }}>K%</th>
                        <th style={{ padding: '8px 8px' }}>BB%</th>
                        {days.map((d) => (
                          <th key={d} style={{ padding: '8px 6px', fontWeight: 600, whiteSpace: 'nowrap' }}>{d}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {relievers.map((r, i) => (
                        <tr key={r.pitcher_id} style={{ background: i % 2 === 0 ? theme.bgCard : theme.bgPage, color: theme.textPrimary }}>
                          <td style={{ padding: '6px 12px', borderBottom: `1px solid ${theme.border}` }}>
                            <div style={{ fontWeight: 600 }}>{r.name}{r.hand ? ` (${r.hand})` : ''}</div>
                            <div style={{ fontSize: 10, color: theme.textMuted }}>{r.role}</div>
                          </td>
                          <td style={{ padding: '6px 8px', textAlign: 'center', borderBottom: `1px solid ${theme.border}` }}>{r.era ?? '—'}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'center', borderBottom: `1px solid ${theme.border}` }}>{r.whip ?? '—'}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'center', borderBottom: `1px solid ${theme.border}` }}>{r.k_pct != null ? `${r.k_pct}%` : '—'}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'center', borderBottom: `1px solid ${theme.border}` }}>{r.bb_pct != null ? `${r.bb_pct}%` : '—'}</td>
                          {r.days.map((cell, di) => (
                            <td key={di} style={{
                              padding: '4px 6px', textAlign: 'center', borderBottom: `1px solid ${theme.border}`,
                              background: loadCellColor(cell?.pitches), color: '#000000',
                            }}>
                              {cell ? (
                                <div style={{ lineHeight: 1.3 }}>
                                  <div style={{ fontWeight: 700 }}>{cell.pitches}p</div>
                                  <div style={{ fontSize: 10 }}>{cell.ip}ip</div>
                                  <div style={{ fontSize: 9, color: '#333333' }}>{cell.h}H {cell.er}ER {cell.bb}BB</div>
                                </div>
                              ) : null}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '10px 16px', fontSize: 11, color: theme.textSecondary }}>
                  <span>Load:</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: theme.bgCardHover, display: 'inline-block', borderRadius: 2 }} /> none</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: theme.dataBlue, display: 'inline-block', borderRadius: 2 }} /> light (≤15p)</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: '#9ca3af', display: 'inline-block', borderRadius: 2 }} /> moderate (16–22p)</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: theme.dataRed, display: 'inline-block', borderRadius: 2 }} /> heavy (23p+)</span>
                </div>
              </div>
            )}

            {relievers.length === 0 && (
              <div style={{ color: theme.textSecondary, fontSize: 13, padding: 20 }}>
                No appearances logged yet for {data.team} in the current window.
              </div>
            )}
          </>
        )}

        {!loading && !data && !error && (
          <div style={{ color: theme.textSecondary, fontSize: 13, padding: 20 }}>Select a team to see bullpen workload.</div>
        )}
      </div>
    </div>
  );
}
