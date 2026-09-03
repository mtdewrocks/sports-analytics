import React, { useState, useEffect } from 'react';
import { getMLBBullpenTeams, getMLBBullpen } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';

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
  background: 'white',
  borderRadius: 8,
  boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
  marginBottom: 20,
  overflow: 'hidden',
};
const cardHeaderStyle: React.CSSProperties = {
  background: '#1a1a2e',
  color: 'white',
  padding: '10px 16px',
  fontWeight: 700,
  fontSize: 14,
  textAlign: 'center',
};

const FRESHNESS_COLOR: Record<string, string> = {
  fresh: '#1a7a3a',
  neutral: '#e59400',
  tired: '#b71c1c',
  unknown: '#888',
};

function FreshBadge({ level }: { level: string }) {
  const color = FRESHNESS_COLOR[level] ?? FRESHNESS_COLOR.unknown;
  return (
    <span style={{
      background: color, color: 'white', fontWeight: 700, fontSize: 11,
      padding: '3px 10px', borderRadius: 4, textTransform: 'uppercase', letterSpacing: 0.5,
    }}>
      {level}
    </span>
  );
}

function loadCellColor(pitches: number | undefined) {
  if (!pitches) return '#eceff1';
  if (pitches <= 15) return '#a5d6a7';
  if (pitches <= 22) return '#ffcc80';
  return '#ef9a9a';
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
    <div style={{ display: 'flex', height: 'calc(100vh - 60px)', overflow: 'hidden', background: '#f5f6fa' }}>

      {/* ── Left Sidebar ── */}
      <div style={{
        width: 220, flexShrink: 0, background: '#1a1a2e', padding: '20px 14px',
        overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16,
      }}>
        <div style={{ color: 'white', fontWeight: 700, fontSize: 15, marginBottom: 4 }}>Bullpen Usage</div>
        <div>
          <div style={{ color: '#aaa', fontSize: 12, fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Team</div>
          {loadingTeams ? (
            <div style={{ color: '#aaa', fontSize: 12, padding: '8px 4px' }}>Loading teams…</div>
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
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>

        {loading && <LoadingSpinner />}
        {error && (
          <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b', marginBottom: 16 }}>
            {error}
          </div>
        )}

        {!loading && data && (
          <>
            {/* ── Header + freshness badge ── */}
            <div style={{ ...cardStyle }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px' }}>
                <div style={{ fontWeight: 700, fontSize: 18, color: '#1a1a2e' }}>{data.team} — Bullpen</div>
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
                      <div style={{ fontSize: 11, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: '#1a1a2e' }}>
                        {k.pitches}<span style={{ fontSize: 13, fontWeight: 400, color: '#888' }}> pitches</span>
                      </div>
                      <div style={{ fontSize: 14, color: '#444', marginBottom: 8 }}>{k.ip} IP</div>
                      <FreshBadge level={k.level} />
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 11, color: '#999', fontStyle: 'italic', marginBottom: 20 }}>
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
                      <tr style={{ background: '#f0f0f0' }}>
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
                        <tr key={r.pitcher_id} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                          <td style={{ padding: '6px 12px', borderBottom: '1px solid #f0f0f0' }}>
                            <div style={{ fontWeight: 600 }}>{r.name}{r.hand ? ` (${r.hand})` : ''}</div>
                            <div style={{ fontSize: 10, color: '#999' }}>{r.role}</div>
                          </td>
                          <td style={{ padding: '6px 8px', textAlign: 'center', borderBottom: '1px solid #f0f0f0' }}>{r.era ?? '—'}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'center', borderBottom: '1px solid #f0f0f0' }}>{r.whip ?? '—'}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'center', borderBottom: '1px solid #f0f0f0' }}>{r.k_pct != null ? `${r.k_pct}%` : '—'}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'center', borderBottom: '1px solid #f0f0f0' }}>{r.bb_pct != null ? `${r.bb_pct}%` : '—'}</td>
                          {r.days.map((cell, di) => (
                            <td key={di} style={{
                              padding: '4px 6px', textAlign: 'center', borderBottom: '1px solid #f0f0f0',
                              background: loadCellColor(cell?.pitches),
                            }}>
                              {cell ? (
                                <div style={{ lineHeight: 1.3 }}>
                                  <div style={{ fontWeight: 700 }}>{cell.pitches}p</div>
                                  <div style={{ fontSize: 10 }}>{cell.ip}ip</div>
                                  <div style={{ fontSize: 9, color: '#555' }}>{cell.h}H {cell.er}ER {cell.bb}BB</div>
                                </div>
                              ) : null}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '10px 16px', fontSize: 11, color: '#666' }}>
                  <span>Load:</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: '#eceff1', display: 'inline-block', borderRadius: 2 }} /> none</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: '#a5d6a7', display: 'inline-block', borderRadius: 2 }} /> light (≤15p)</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: '#ffcc80', display: 'inline-block', borderRadius: 2 }} /> moderate (16–22p)</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 12, height: 12, background: '#ef9a9a', display: 'inline-block', borderRadius: 2 }} /> heavy (23p+)</span>
                </div>
              </div>
            )}

            {relievers.length === 0 && (
              <div style={{ color: '#888', fontSize: 13, padding: 20 }}>
                No appearances logged yet for {data.team} in the current window.
              </div>
            )}
          </>
        )}

        {!loading && !data && !error && (
          <div style={{ color: '#888', fontSize: 13, padding: 20 }}>Select a team to see bullpen workload.</div>
        )}
      </div>
    </div>
  );
}
