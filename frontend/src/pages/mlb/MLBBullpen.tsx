import React, { useState, useEffect } from 'react';
import { getMLBBullpenTeams, getMLBBullpen } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
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

export default function MLBBullpen() {
  const [teams, setTeams] = useState<string[]>([]);
  const [loadingTeams, setLoadingTeams] = useState(true);
  const [selectedTeam, setSelectedTeam] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<BullpenData | null>(null);

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
    <div style={{ display: 'flex', height: 'calc(100vh - 60px)', overflow: 'hidden', background: theme.bgPage }}>

      {/* ── Left Sidebar ── */}
      <div style={{
        width: 220, flexShrink: 0, background: theme.bgCard, padding: '20px 14px',
        overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16,
      }}>
        <div style={{ color: 'white', fontWeight: 700, fontSize: 15, marginBottom: 4 }}>Bullpen Usage</div>
        <div>
          <div style={{ color: theme.textSecondary, fontSize: 12, fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Team</div>
          {loadingTeams ? (
            <div style={{ color: theme.textSecondary, fontSize: 12, padding: '8px 4px' }}>Loading teams…</div>
          ) : (
            <SearchDropdown
              players={teams}
              value={selectedTeam}
              onSelect={(t) => { setSelectedTeam(t); fetchBullpen(t); }}
              placeholder="Search team..."
              inputStyle={{ padding: '7px 10px', fontSize: 13, width: '100%', boxSizing: 'border-box' }}
            />
          )}
        </div>
      </div>

      {/* ── Main Content ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px', background: theme.bgPage }}>

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
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 8 }}>
                  {([
                    { label: 'Last 1 Day', k: kpis['1_day'] },
                    { label: 'Last 3 Days', k: kpis['3_day'] },
                    { label: 'Last 7 Days', k: kpis['7_day'] },
                  ] as const).map(({ label, k }) => (
                    <div key={label} style={{ ...cardStyle, margin: 0, padding: '14px 16px' }}>
                      <div style={{ fontSize: 11, color: theme.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: theme.textPrimary }}>
                        {k.pitches}<span style={{ fontSize: 13, fontWeight: 400, color: theme.textSecondary }}> pitches</span>
                      </div>
                      <div style={{ fontSize: 14, color: theme.textSecondary, marginBottom: 8 }}>{k.ip} IP</div>
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

            {/* ── Workload table ── */}
            {relievers.length > 0 && (
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
