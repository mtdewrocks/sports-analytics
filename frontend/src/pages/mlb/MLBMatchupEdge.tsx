import { useEffect, useState } from 'react';
import { getMLBMatchupEdge } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import StatCard from '../../components/StatCard';
import ChipRow from '../../components/ChipRow';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

// wOBA-shaped row -- Toughest Matchups, Best Matchups, Platoon Edge Finder
// all share this shape (see get_mlb_matchup_edge() in backend/app/data/mlb.py).
interface WobaRow {
  name: string;
  bats: string;
  seasonWoba: number;
  splitWobaBatter: number;
  pctl: number | null;
  pitcher: string;
  throws: string;
  splitWobaPitcher: number;
  leagueGap: number;
  withinGap: number;
  platoonGap: number;
  vsLeagueOwn: number;
  direction?: 'avoid' | 'target';
}

// K%-shaped row -- Strikeout Risk, Contact Matchups.
interface KRow {
  name: string;
  bats: string;
  seasonK: number;
  splitKBatter: number;
  kGap: number;
  kVsLeague: number;
  pitcher: string;
  throws: string;
  splitKPitcher: number;
  kLeagueGap: number;
  kWithinGap: number;
}

interface MatchupEdgeData {
  asOf: string | null;
  leagueBenchmarks: { L: number | null; R: number | null };
  kLeagueBenchmarks: { L: number | null; R: number | null };
  avoidFlat: WobaRow[];
  targetFlat: WobaRow[];
  platoonFinder: WobaRow[];
  kRisk: KRow[];
  contactMatchups: KRow[];
}

type TabKey = 'avoid' | 'target' | 'platoon' | 'kRisk' | 'contact';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'avoid', label: 'Toughest Matchups' },
  { key: 'target', label: 'Best Matchups' },
  { key: 'platoon', label: 'Platoon Edge Finder' },
  { key: 'kRisk', label: 'Strikeout Risk' },
  { key: 'contact', label: 'Contact Matchups' },
];

// Colorblind-safe blue/red -- the same pair already used on the NFL
// Matchup/Mismatches pages (see theme.ts's header comment), not a
// green/red scale.
function wobaColor(row: WobaRow): string {
  const dir = row.direction ?? (row.leagueGap < 0 ? 'avoid' : 'target');
  return dir === 'avoid' ? theme.dataRed : theme.dataBlue;
}
function fmtWoba(v: number): string {
  return v.toFixed(3).replace(/^0/, '');
}
function fmtGap(v: number): string {
  return v > 0 ? `+${v}` : `${v}`;
}
function fmtPct(v: number): string {
  return `${v.toFixed(1)}%`;
}

export default function MLBMatchupEdge() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [data, setData] = useState<MatchupEdgeData | null>(null);
  const [tab, setTab] = useState<TabKey>('avoid');
  const isMobile = useIsMobile();

  useEffect(() => {
    getMLBMatchupEdge()
      .then((res) => setData(res.data))
      .catch(() => setError('Failed to load matchup edge data.'))
      .finally(() => setLoading(false));
  }, []);

  const wobaRows: WobaRow[] =
    tab === 'avoid' ? data?.avoidFlat ?? [] :
    tab === 'target' ? data?.targetFlat ?? [] :
    tab === 'platoon' ? data?.platoonFinder ?? [] : [];
  const kRows: KRow[] =
    tab === 'kRisk' ? data?.kRisk ?? [] :
    tab === 'contact' ? data?.contactMatchups ?? [] : [];
  const isKTab = tab === 'kRisk' || tab === 'contact';
  const kRiskColor = tab === 'kRisk' ? theme.dataRed : theme.dataBlue;

  return (
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 1200, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>Matchup Edge</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 4 }}>
        Who's set up to struggle or succeed today, split into a pitcher signal (is he unusually
        weak or strong against this handedness, beyond his own average and league average) and a
        batter signal (does his own split back it up).
      </div>
      {data?.asOf && (
        <div style={{ fontSize: 12, color: theme.textMuted, marginBottom: 20 }}>
          Matchups as of {data.asOf}
          {data.leagueBenchmarks.L != null && data.leagueBenchmarks.R != null && (
            <> · League wOBA benchmark: {fmtWoba(data.leagueBenchmarks.R)} vs R, {fmtWoba(data.leagueBenchmarks.L)} vs L</>
          )}
          {data.kLeagueBenchmarks.L != null && data.kLeagueBenchmarks.R != null && (
            <> · League K%: {data.kLeagueBenchmarks.R.toFixed(1)}% vs R, {data.kLeagueBenchmarks.L.toFixed(1)}% vs L</>
          )}
        </div>
      )}

      <ChipRow
        chips={TABS.map((t) => ({ key: t.key, label: t.label }))}
        value={tab}
        onChange={(k) => setTab(k as TabKey)}
        scroll={isMobile}
        bleed={isMobile ? 16 : 0}
        style={{ marginBottom: 20 }}
      />

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {!loading && !error && data && (
        <>
          {!isKTab && wobaRows.length === 0 && (
            <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40 }}>
              No matchups clear these thresholds on today's slate -- check back once more games are announced.
            </div>
          )}
          {isKTab && kRows.length === 0 && (
            <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40 }}>
              No matchups clear these thresholds on today's slate -- check back once more games are announced.
            </div>
          )}

          {/* --- wOBA tabs (Toughest / Best / Platoon Edge Finder) --- */}
          {!isKTab && wobaRows.length > 0 && (isMobile ? (
            <div>
              {wobaRows.map((r, i) => {
                const color = wobaColor(r);
                return (
                  <StatCard
                    key={i}
                    title={<span style={{ fontWeight: 700 }}>{r.name} <span style={{ color: theme.textMuted, fontWeight: 400 }}>({r.bats})</span></span>}
                    value={fmtGap(r.leagueGap)}
                    valueColor={color}
                    valueLabel="vs league"
                    meta={[
                      `vs ${r.pitcher} (${r.throws})`,
                      `Season wOBA ${fmtWoba(r.seasonWoba)}${r.pctl != null ? ` · ${r.pctl}th pctl` : ''}`,
                    ]}
                    metaSecondary={[
                      `Split wOBA ${fmtWoba(r.splitWobaBatter)} (batter)`,
                      `${fmtWoba(r.splitWobaPitcher)} allowed (pitcher, this side)`,
                    ]}
                    footer={`vs pitcher's own avg: ${fmtGap(r.withinGap)} pts`}
                  />
                );
              })}
            </div>
          ) : (
            <div style={{ background: theme.bgCard, borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.4)', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Batter</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Season wOBA (pctl)</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>wOBA vs this hand</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Pitcher (this side)</th>
                    <th style={{ padding: '10px 14px', textAlign: 'right' }}>vs League</th>
                    <th style={{ padding: '10px 14px', textAlign: 'right' }}>vs Pitcher's Own Avg</th>
                  </tr>
                </thead>
                <tbody>
                  {wobaRows.map((r, i) => {
                    const color = wobaColor(r);
                    return (
                      <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                        <td style={{ padding: '9px 14px' }}>
                          <span style={{ fontWeight: 700, color: theme.textPrimary }}>{r.name}</span>{' '}
                          <span style={{ color: theme.textMuted }}>({r.bats})</span>
                        </td>
                        <td style={{ padding: '9px 14px', color: theme.textSecondary }}>
                          {fmtWoba(r.seasonWoba)}{r.pctl != null ? ` (${r.pctl}th)` : ''}
                        </td>
                        <td style={{ padding: '9px 14px' }}>
                          <span style={{ color: theme.textPrimary }}>{fmtWoba(r.splitWobaBatter)}</span>{' '}
                          <span style={{ color: theme.textMuted, fontSize: 12 }}>({fmtGap(r.platoonGap)} vs season)</span>
                        </td>
                        <td style={{ padding: '9px 14px' }}>
                          <span style={{ fontWeight: 700, color: theme.textPrimary }}>{r.pitcher}</span>{' '}
                          <span style={{ color: theme.textMuted }}>({r.throws})</span>
                          <div style={{ color: theme.textSecondary, fontSize: 12 }}>{fmtWoba(r.splitWobaPitcher)} allowed</div>
                        </td>
                        <td style={{ padding: '9px 14px', textAlign: 'right', fontWeight: 700, color }}>{fmtGap(r.leagueGap)}</td>
                        <td style={{ padding: '9px 14px', textAlign: 'right', fontWeight: 700, color }}>{fmtGap(r.withinGap)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}

          {/* --- K% tabs (Strikeout Risk / Contact Matchups) --- */}
          {isKTab && kRows.length > 0 && (isMobile ? (
            <div>
              {kRows.map((r, i) => (
                <StatCard
                  key={i}
                  title={<span style={{ fontWeight: 700 }}>{r.name} <span style={{ color: theme.textMuted, fontWeight: 400 }}>({r.bats})</span></span>}
                  value={fmtGap(r.kLeagueGap)}
                  valueColor={kRiskColor}
                  valueLabel="vs league"
                  meta={[
                    `vs ${r.pitcher} (${r.throws})`,
                    `Season K% ${fmtPct(r.seasonK)}`,
                  ]}
                  metaSecondary={[
                    `Split K% ${fmtPct(r.splitKBatter)} (batter)`,
                    `${fmtPct(r.splitKPitcher)} pitcher K%, this side`,
                  ]}
                  footer={`vs pitcher's own avg: ${fmtGap(r.kWithinGap)} pts`}
                />
              ))}
            </div>
          ) : (
            <div style={{ background: theme.bgCard, borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.4)', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Batter</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Season K%</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>K% vs this hand</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Pitcher (this side)</th>
                    <th style={{ padding: '10px 14px', textAlign: 'right' }}>vs League</th>
                    <th style={{ padding: '10px 14px', textAlign: 'right' }}>vs Pitcher's Own Avg</th>
                  </tr>
                </thead>
                <tbody>
                  {kRows.map((r, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                      <td style={{ padding: '9px 14px' }}>
                        <span style={{ fontWeight: 700, color: theme.textPrimary }}>{r.name}</span>{' '}
                        <span style={{ color: theme.textMuted }}>({r.bats})</span>
                      </td>
                      <td style={{ padding: '9px 14px', color: theme.textSecondary }}>{fmtPct(r.seasonK)}</td>
                      <td style={{ padding: '9px 14px' }}>
                        <span style={{ color: theme.textPrimary }}>{fmtPct(r.splitKBatter)}</span>{' '}
                        <span style={{ color: theme.textMuted, fontSize: 12 }}>({fmtGap(r.kGap)} vs season)</span>
                      </td>
                      <td style={{ padding: '9px 14px' }}>
                        <span style={{ fontWeight: 700, color: theme.textPrimary }}>{r.pitcher}</span>{' '}
                        <span style={{ color: theme.textMuted }}>({r.throws})</span>
                        <div style={{ color: theme.textSecondary, fontSize: 12 }}>{fmtPct(r.splitKPitcher)} K%</div>
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', fontWeight: 700, color: kRiskColor }}>{fmtGap(r.kLeagueGap)}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', fontWeight: 700, color: kRiskColor }}>{fmtGap(r.kWithinGap)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 16, textAlign: 'center' }}>
            Filters: pitcher-side splits require 60+ plate appearances against that handedness this
            season; batter-side splits require 30+ plate appearances. wOBA tables need a 50+ pt gap
            vs league average and a 15+ pt gap vs the pitcher's own average, confirmed by the
            batter's own split being 25+ pts off his season line in the matching direction (or
            already on the wrong side of league average). Strikeout tables use the same shape at a
            5+ pt bar throughout. Platoon Edge Finder is different: it's a batter-skill-only list --
            a fixed-handed batter (not a switch hitter, who always gets the favorable box) who is
            25+ pts better against the opposite handedness than his own season line, facing that
            opposite hand today -- the classic "lefty who mashes right-handed pitching." It doesn't
            require anything about the pitcher himself.
          </div>
        </>
      )}
    </div>
  );
}
