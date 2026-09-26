import React, { useEffect, useState } from 'react';
import { getMLBMatchupEdge } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import StatCard from '../../components/StatCard';
import ChipRow from '../../components/ChipRow';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';
import { AltLines, formatOdds, prettyBook } from '../../components/PropsExplorer';

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
  /** Pitcher's strikeout rate against everyone, and the league rate for this
   *  batter's side -- the reference points on the card's bars. */
  pitcherAllK?: number;
  leagueK?: number;
  resolvedSide?: 'L' | 'R';
  /** Batter-strikeout prop: the over on Strikeout Risk, the under on
   *  Contact Matchups. main is 0.5 when any book hangs it. */
  strikeoutProp?: {
    side: 'over' | 'under';
    main: KPrice | null;
    alternates: KPrice[];
  };
}

interface KPrice { line: number; price: number; books: string[]; is_live: boolean }

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

const handWord = (h: string) => (h === 'L' ? 'left' : h === 'R' ? 'right' : h === 'S' ? 'switch' : h);

/** Bars run 0-40%: every realistic strikeout rate fits, and the league tick
 *  (~22%) lands just past the middle, so above/below reads at a glance. */
const K_BAR_MAX = 40;

function KBar({ label, value, league, highlight }: { label: string; value: number; league?: number; highlight?: string }) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / K_BAR_MAX) * 100))}%`;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr 44px', gap: 8, alignItems: 'center', fontSize: 11.5, margin: '5px 0' }}>
      <span style={{ color: theme.textSecondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
      <div style={{ position: 'relative', height: 8, background: theme.bgCardHover, borderRadius: 4 }}>
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: pct(value), borderRadius: 4, background: highlight ?? theme.borderStrong }} />
        {league != null && (
          <div style={{ position: 'absolute', top: -4, bottom: -4, width: 2, left: pct(league), background: theme.textPrimary, opacity: 0.7 }} />
        )}
      </div>
      <span style={{ textAlign: 'right', fontWeight: 600, color: highlight ?? theme.textPrimary, fontVariantNumeric: 'tabular-nums' }}>
        {value.toFixed(1)}%
      </span>
    </div>
  );
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 9.5, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 12, marginBottom: 2 }}>
      {children}
    </div>
  );
}

function StrikeoutProp({ prop }: { prop?: KRow['strikeoutProp'] }) {
  if (!prop) return null;
  const over = prop.side === 'over';
  const title = over ? 'Strikeouts over' : 'Strikeouts under';
  const sub = over ? 'Batter to strike out' : 'Batter does not strike out';
  const main = prop.main;
  return (
    <>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: 12, paddingTop: 10, borderTop: `1px solid ${theme.border}`,
      }}>
        <div style={{ fontSize: 13, color: theme.textPrimary }}>
          {title} {main ? main.line : '0.5'}
          <div style={{ fontSize: 11, color: theme.textMuted }}>{sub}</div>
        </div>
        {main ? (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: theme.dataBlue, lineHeight: 1.1, fontVariantNumeric: 'tabular-nums' }}>
              {formatOdds(main.price)}
            </div>
            <div style={{ fontSize: 11, color: theme.textMuted }}>
              {prettyBook(main.books[0])}{main.books.length > 1 ? ` +${main.books.length - 1}` : ''}
            </div>
          </div>
        ) : (
          <span style={{ fontSize: 12, color: theme.textMuted }}>No line posted yet</span>
        )}
      </div>
      <AltLines items={prop.alternates.map((a) => ({
        label: `${over ? 'Over' : 'Under'} ${a.line}`, price: a.price, book: a.books[0],
      }))} />
    </>
  );
}

/** Mobile Strikeout Risk / Contact Matchups card: plain-language bars in
 *  place of the old abbreviations, plus the batter's strikeout prop. */
function KCard({ r, color }: { r: KRow; color: string }) {
  const side = r.resolvedSide ?? (r.bats === 'L' || r.bats === 'R' ? r.bats : undefined);
  const pitcherSide = side ? `vs ${handWord(side)}-handed hitters` : 'vs this side';
  const batterSide = r.throws ? `vs ${handWord(r.throws)}-handed pitchers` : 'vs this hand';
  const gap = r.kLeagueGap;
  return (
    <div style={{ background: theme.bgCard, borderRadius: 8, padding: '12px 14px', marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary }}>{r.name}</div>
          <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 1 }}>
            Bats {handWord(r.bats)} · vs {r.pitcher} (throws {handWord(r.throws)})
          </div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color, lineHeight: 1.1 }}>{fmtGap(gap)}</div>
          <div style={{ fontSize: 10, color: theme.textMuted, maxWidth: 118 }}>
            pts {gap >= 0 ? 'above' : 'below'} league strikeout rate
          </div>
        </div>
      </div>

      <GroupLabel>Pitcher strikeout rate</GroupLabel>
      <KBar label={pitcherSide} value={r.splitKPitcher} league={r.leagueK} highlight={color} />
      {r.pitcherAllK != null && <KBar label="vs all hitters" value={r.pitcherAllK} league={r.leagueK} />}

      <GroupLabel>Batter strikeout rate</GroupLabel>
      <KBar label={batterSide} value={r.splitKBatter} league={r.leagueK} highlight={color} />
      <KBar label="season" value={r.seasonK} league={r.leagueK} />
      {r.leagueK != null && (
        <div style={{ fontSize: 10.5, color: theme.textMuted, marginTop: 3 }}>
          <span style={{ display: 'inline-block', width: 2, height: 9, background: theme.textPrimary, opacity: 0.7, verticalAlign: 'middle', marginRight: 5 }} />
          league average ({r.leagueK.toFixed(1)}%)
        </div>
      )}

      <StrikeoutProp prop={r.strikeoutProp} />
    </div>
  );
}

export default function MLBMatchupEdge() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [data, setData] = useState<MatchupEdgeData | null>(null);
  const [tab, setTab] = useState<TabKey>('avoid');
  const isMobile = useIsMobile();
  const [howOpen, setHowOpen] = useState(false);

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
            <> · League wOBA: {fmtWoba(data.leagueBenchmarks.R)} for right-handed hitters, {fmtWoba(data.leagueBenchmarks.L)} for left-handed</>
          )}
          {data.kLeagueBenchmarks.L != null && data.kLeagueBenchmarks.R != null && (
            <> · League strikeout rate: {data.kLeagueBenchmarks.R.toFixed(1)}% for right-handed hitters, {data.kLeagueBenchmarks.L.toFixed(1)}% for left-handed</>
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
                <KCard key={i} r={r} color={kRiskColor} />
              ))}
            </div>
          ) : (
            <div style={{ background: theme.bgCard, borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.4)', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Batter</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Batter strikeout rate (season)</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Batter strikeout rate vs this hand</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Pitcher strikeout rate vs this side</th>
                    <th style={{ padding: '10px 14px', textAlign: 'right' }}>Pts vs league</th>
                    <th style={{ padding: '10px 14px', textAlign: 'right' }}>Pts vs pitcher's overall</th>
                    <th style={{ padding: '10px 14px', textAlign: 'right' }}>{tab === 'kRisk' ? 'Strikeouts over 0.5' : 'Strikeouts under 0.5'}</th>
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
                        <div style={{ color: theme.textSecondary, fontSize: 12 }}>
                          {fmtPct(r.splitKPitcher)}{r.pitcherAllK != null ? ` (${fmtPct(r.pitcherAllK)} vs all hitters)` : ''}
                        </div>
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', fontWeight: 700, color: kRiskColor }}>{fmtGap(r.kLeagueGap)}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', fontWeight: 700, color: kRiskColor }}>{fmtGap(r.kWithinGap)}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {r.strikeoutProp?.main ? (
                          <>
                            <span style={{ fontWeight: 700, color: theme.dataBlue }}>{formatOdds(r.strikeoutProp.main.price)}</span>
                            <div style={{ fontSize: 11, color: theme.textMuted }}>
                              {r.strikeoutProp.main.line !== 0.5 ? `${r.strikeoutProp.main.line} · ` : ''}{prettyBook(r.strikeoutProp.main.books[0])}
                            </div>
                          </>
                        ) : <span style={{ color: theme.textMuted, fontSize: 12 }}>No line</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          <button
            onClick={() => setHowOpen((o) => !o)}
            style={{
              display: 'block', margin: '16px auto 0', background: 'none', border: 'none',
              color: theme.accent, fontSize: 12, fontWeight: 600, cursor: 'pointer', padding: '6px 0',
            }}
          >
            How these lists are built {howOpen ? '▴' : '▾'}
          </button>
          {howOpen && <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 6, textAlign: 'center' }}>
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
          </div>}
        </>
      )}
    </div>
  );
}
