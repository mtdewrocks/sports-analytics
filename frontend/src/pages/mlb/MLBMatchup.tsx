import React, { useState, useEffect, useRef } from 'react';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import { getMLBPitchers, getMLBMatchup } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import { theme } from '../../theme';

const IMAGE_BASE = 'https://github.com/mtdewrocks/sports-analytics/raw/main/backend/data/mlb/pitcher_images';

interface PitcherSplit {
  avg?: number; woba?: number; slg?: number; iso?: number;
  k_pct?: number; bb_pct?: number; hr_pct?: number;
}

interface MatchupData {
  season_stats?: Record<string, any>;
  game_logs?: Record<string, any>[];
  splits?: Record<string, any>[];
  percentiles?: { Statistic: string; Percentile: number }[];
  opposing_hitters?: Record<string, any>[];
  pitcher_splits?: { vs_r?: PitcherSplit; vs_l?: PitcherSplit };
  [key: string]: any;
}

// ── Colorblind-safe tier system: red = tough matchup for the pitcher,
// blue = favorable, gray = neutral. Blue/red stays distinguishable for the
// common (red-green) forms of color blindness, since blue sits outside
// that confusion line entirely.
//
// Redesigned for the dark theme: DARK now means "most vivid/visible tier"
// (matching theme.dataRed/dataBlue) rather than "most saturated pastel" as
// in the old light-mode version, and NEUTRAL is now a dark fill that blends
// into the dark table -- the old light gray NEUTRAL (#eeeeee) would stand
// out as its own highlight against a dark background, which is backwards
// from its intended "nothing notable here" meaning. ──────────────────────
const RED_DARK = theme.dataRed;
const RED_MED = '#c2645a';
const BLUE_MED = '#0ea5e9';
const BLUE_DARK = '#1d4ed8';
const NEUTRAL = theme.bgCardHover;

function tier5(v: number | null | undefined, t90: number, t75: number, t25: number, t10: number): string | null {
  if (v == null || isNaN(v)) return null;
  if (v > t90) return RED_DARK;
  if (v > t75) return RED_MED;
  if (v > t25) return NEUTRAL;
  if (v > t10) return BLUE_MED;
  return BLUE_DARK;
}

// AVG/ISO: fixed thresholds (not percentile-derived).
function tierAvg(v: number | null | undefined): string | null {
  if (v == null || isNaN(v)) return null;
  if (v > 0.285) return RED_DARK;
  if (v >= 0.270) return RED_MED;
  if (v <= 0.200) return BLUE_DARK;
  if (v <= 0.225) return BLUE_MED;
  return NEUTRAL;
}
function tierIso(v: number | null | undefined): string | null {
  if (v == null || isNaN(v)) return null;
  if (v > 0.235) return RED_DARK;
  if (v > 0.195) return RED_MED;
  if (v <= 0.100) return BLUE_DARK;
  if (v <= 0.125) return BLUE_MED;
  return NEUTRAL;
}
// OBP/SLG/OPS/wOBA: real league-percentile-derived thresholds (90th/75th/25th/10th).
const tierObp = (v?: number | null) => tier5(v, 0.370, 0.345, 0.295, 0.265);
const tierSlg = (v?: number | null) => tier5(v, 0.495, 0.450, 0.365, 0.320);
const tierOps = (v?: number | null) => tier5(v, 0.850, 0.790, 0.670, 0.600);
const tierWoba = (v?: number | null) => tier5(v, 0.375, 0.355, 0.310, 0.280);

// K%: INVERTED vs. the others -- a high strikeout rate is GOOD for the
// pitcher (easy out), so high K% is blue, not red.
function tierKpct(v: number | null | undefined): string | null {
  if (v == null || isNaN(v)) return null;
  if (v > 31) return BLUE_DARK;
  if (v > 25) return BLUE_MED;
  if (v < 14) return RED_DARK;
  if (v < 17) return RED_MED;
  return null;
}
function tierBb(v: number | null | undefined): string | null {
  if (v == null || isNaN(v)) return null;
  if (v > 13) return RED_DARK;
  if (v > 11) return RED_MED;
  if (v < 4.5) return BLUE_DARK;
  if (v < 6.5) return BLUE_MED;
  return null;
}
// Pitcher's OWN K rate -- high is good for the pitcher (blue). Only used in
// the PDF's restored mini split-table; the page relies on the fuller,
// pooled-season Splits table instead (see the duplicate-stats discussion).
function tierPitcherKpct(v: number | null | undefined): string | null {
  if (v == null || isNaN(v)) return null;
  if (v > 27) return BLUE_DARK;
  if (v > 23) return BLUE_MED;
  if (v < 16) return RED_DARK;
  if (v < 18) return RED_MED;
  return null;
}
function tierHrPct(v: number | null | undefined): string | null {
  if (v == null || isNaN(v)) return null;
  if (v > 4.0) return RED_DARK;
  if (v < 1.5) return BLUE_DARK;
  return null;
}

function cellStyle(color: string | null): React.CSSProperties {
  // Verified via WCAG contrast ratios against each specific fill: black
  // text clears 4.5:1 on RED_DARK (6.28), RED_MED (5.26), and BLUE_MED
  // (7.58). Two colors need light text instead: NEUTRAL is a dark fill
  // (blends into the dark table, 16.17:1 with light text), and BLUE_DARK
  // is a more saturated royal blue that actually FAILS with black text
  // (3.13:1) but passes comfortably with theme.textPrimary (5.37:1).
  if (!color) return {};
  const useLightText = color === NEUTRAL || color === BLUE_DARK;
  return { background: color, color: useLightText ? theme.textPrimary : '#000000', fontWeight: 600 };
}

function pctBarColor(pct: number) {
  if (pct >= 70) return theme.dataBlue;
  if (pct >= 40) return '#9ca3af';
  return theme.dataRed;
}

const num = (v: any) => (v === '' || v == null ? null : Number(v));

const SEASON_DISPLAY = ['Handedness', 'GS', 'W', 'L', 'ERA', 'IP', 'SO', 'K/IP', 'WHIP'];
const LOG_COLUMNS = ['Date', 'Opponent', 'W', 'L', 'IP', 'H', 'R', 'ER', 'HR', 'BB', 'SO', 'Pitches'];
const HITTER_COLUMNS = ['Batting Order', 'Player', 'Bats', 'Average', 'wOBA', 'OBP', 'SLG', 'OPS', 'ISO', 'K%', 'BB%', 'Last Week BA'];

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
const thStyle: React.CSSProperties = {
  padding: '8px 12px',
  fontWeight: 600,
  color: theme.textPrimary,
  whiteSpace: 'nowrap',
  background: theme.bgCardHover,
  textAlign: 'center',
};
const tdStyle: React.CSSProperties = {
  padding: '7px 12px',
  textAlign: 'center',
  whiteSpace: 'nowrap',
  borderBottom: `1px solid ${theme.border}`,
  color: theme.textPrimary,
};

// ── Shared pieces, reused by both the full page and the PDF summary, so the
// two views can't silently drift out of sync with each other. ─────────────

function GameLogTable({ logs, title }: { logs: Record<string, any>[]; title: string }) {
  if (logs.length === 0) return null;
  return (
    <div style={{ ...cardStyle, flex: 2, minWidth: 400, marginBottom: 0 }}>
      <div style={cardHeaderStyle}>{title}</div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>{LOG_COLUMNS.filter((c) => c in logs[0]).map((col) => <th key={col} style={thStyle}>{col}</th>)}</tr>
          </thead>
          <tbody>
            {logs.map((row, i) => (
              <tr key={i} style={{ background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                {LOG_COLUMNS.filter((c) => c in row).map((col) => (
                  <td key={col} style={tdStyle}>{String(row[col] ?? '—')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MatchupSummaryTable({ flags }: { flags: { label: string; count: number }[] }) {
  if (flags.length === 0) return null;
  return (
    <div style={{ ...cardStyle, flex: 1, minWidth: 260, marginBottom: 0 }}>
      <div style={cardHeaderStyle}>Matchup Summary</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <tbody>
          {flags.map((f) => (
            <tr key={f.label} style={{ borderBottom: `1px solid ${theme.border}` }}>
              <td style={{ padding: '7px 14px', color: theme.textSecondary }}>{f.label}</td>
              <td style={{ padding: '7px 14px', textAlign: 'right', fontWeight: 700, color: theme.textPrimary }}>{f.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OpposingLineupTable({ hitters }: { hitters: Record<string, any>[] }) {
  if (hitters.length === 0) return null;
  return (
    <div style={cardStyle}>
      <div style={cardHeaderStyle}>Opposing Lineup (batting order)</div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              {HITTER_COLUMNS.filter((c) => c in hitters[0]).map((col) => <th key={col} style={thStyle}>{col}</th>)}
            </tr>
          </thead>
          <tbody>
            {hitters.map((row, i) => {
              const tierMap: Record<string, string | null> = {
                'Average': tierAvg(num(row['Average'])),
                'wOBA': tierWoba(num(row['wOBA'])),
                'OBP': tierObp(num(row['OBP'])),
                'SLG': tierSlg(num(row['SLG'])),
                'OPS': tierOps(num(row['OPS'])),
                'ISO': tierIso(num(row['ISO'])),
                'K%': tierKpct(num(row['K%'])),
                'BB%': tierBb(num(row['BB%'])),
              };
              return (
                <tr key={i} style={{ background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                  {HITTER_COLUMNS.filter((c) => c in row).map((col) => {
                    const v = row[col];
                    const displayVal = v === '' || v == null ? '—'
                      : col === 'Batting Order' ? String(Math.round(Number(v)))
                      : String(v);
                    return (
                      <td key={col} style={{ ...tdStyle, ...cellStyle(tierMap[col] ?? null) }}>
                        {displayVal}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: 11, color: theme.textMuted, fontStyle: 'italic', padding: '8px 16px' }}>
        Darker red = tougher matchup for the pitcher; darker blue = more favorable. K% runs opposite
        the others (a high strikeout rate favors the pitcher).
      </div>
    </div>
  );
}

function PitcherSplitTable({ label, d }: { label: string; d?: PitcherSplit }) {
  if (!d) return null;
  const rows: { stat: string; val: number | undefined; fmt: (v: number) => string; color: string | null }[] = [
    { stat: 'AVG', val: d.avg, fmt: (v) => v.toFixed(3), color: tierAvg(d.avg) },
    { stat: 'wOBA', val: d.woba, fmt: (v) => v.toFixed(3), color: tierWoba(d.woba) },
    { stat: 'SLG', val: d.slg, fmt: (v) => v.toFixed(3), color: tierSlg(d.slg) },
    { stat: 'ISO', val: d.iso, fmt: (v) => v.toFixed(3), color: tierIso(d.iso) },
    { stat: 'K%', val: d.k_pct, fmt: (v) => v.toFixed(1), color: tierPitcherKpct(d.k_pct) },
    { stat: 'BB%', val: d.bb_pct, fmt: (v) => v.toFixed(1), color: tierBb(d.bb_pct) },
    { stat: 'HR%', val: d.hr_pct, fmt: (v) => v.toFixed(1), color: tierHrPct(d.hr_pct) },
  ];
  return (
    <table style={{ borderCollapse: 'collapse', fontSize: 13, width: '100%' }}>
      <thead>
        <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
          <th colSpan={2} style={{ padding: '7px 12px', fontWeight: 700 }}>{label}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.stat} style={{ borderBottom: `1px solid ${theme.border}` }}>
            <td style={{ padding: '6px 12px', fontWeight: 600, color: theme.textSecondary }}>{r.stat}</td>
            <td style={{ padding: '6px 12px', textAlign: 'center', ...cellStyle(r.color) }}>
              {r.val != null ? r.fmt(r.val) : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function MLBMatchup() {
  const [pitchers, setPitchers] = useState<string[]>([]);
  const [loadingPitchers, setLoadingPitchers] = useState(true);
  const [selectedPitcher, setSelectedPitcher] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [matchupData, setMatchupData] = useState<MatchupData | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const pdfRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoadingPitchers(true);
    getMLBPitchers()
      .then((res) => setPitchers(res.data))
      .catch(() => setPitchers([]))
      .finally(() => setLoadingPitchers(false));
  }, []);

  const fetchMatchup = async (pitcher: string) => {
    if (!pitcher) return;
    setLoading(true);
    setError('');
    setMatchupData(null);
    try {
      const res = await getMLBMatchup(pitcher);
      setMatchupData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch matchup data.');
    } finally {
      setLoading(false);
    }
  };

  const downloadPdf = async () => {
    const el = pdfRef.current;
    if (!el || !matchupData) return;
    setDownloadingPdf(true);
    try {
      const canvas = await html2canvas(el, { scale: 2, backgroundColor: theme.bgPage, useCORS: true });
      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'letter' });
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const margin = 20;
      const maxWidth = pageWidth - margin * 2;
      const maxHeight = pageHeight - margin * 2;
      const ratio = canvas.width / canvas.height;
      let w = maxWidth, h = w / ratio;
      if (h > maxHeight) { h = maxHeight; w = h * ratio; }
      pdf.addImage(imgData, 'PNG', (pageWidth - w) / 2, (pageHeight - h) / 2, w, h);
      pdf.save(`${selectedPitcher.replace(/\s+/g, '_')}_matchup_summary.pdf`);
    } catch {
      setError('Failed to generate PDF. Please try again.');
    } finally {
      setDownloadingPdf(false);
    }
  };

  const seasonStats = matchupData?.season_stats;
  const allGameLogs = matchupData?.game_logs ?? [];
  const gameLogsFull = allGameLogs.slice(0, 10);   // full page: last 10
  const gameLogsPdf = allGameLogs.slice(0, 5);      // PDF summary: last 5
  const splits = matchupData?.splits ?? [];
  const percentiles = matchupData?.percentiles ?? [];
  const opposingHitters = matchupData?.opposing_hitters ?? [];
  const pitcherSplits = matchupData?.pitcher_splits ?? {};
  const splitsColumns = splits.length > 0 ? Object.keys(splits[0]) : [];

  const seasonDisplay = seasonStats
    ? SEASON_DISPLAY.filter((k) => k in seasonStats).map((k) => ({ key: k, val: seasonStats[k] }))
    : [];

  const photoUrl = selectedPitcher ? `${IMAGE_BASE}/${encodeURIComponent(selectedPitcher)}.jpg` : '';

  // Matchup summary: count opposing hitters clearing each threshold. Shared
  // by both the page and the PDF, since it's derived from the same
  // opposingHitters data either way.
  const summaryFlags: { label: string; count: number }[] = opposingHitters.length > 0 ? [
    { label: 'Tough AVG (>.270)', count: opposingHitters.filter((h) => { const c = tierAvg(num(h['Average'])); return c === RED_DARK || c === RED_MED; }).length },
    { label: 'Favorable AVG (<.250)', count: opposingHitters.filter((h) => { const c = tierAvg(num(h['Average'])); return c === BLUE_DARK || c === BLUE_MED; }).length },
    { label: 'Tough ISO (>.150)', count: opposingHitters.filter((h) => { const c = tierIso(num(h['ISO'])); return c === RED_DARK || c === RED_MED; }).length },
    { label: 'Favorable K (K%>25)', count: opposingHitters.filter((h) => tierKpct(num(h['K%'])) && [BLUE_DARK, BLUE_MED].includes(tierKpct(num(h['K%']))!)).length },
    { label: 'Tough contact (K%<17)', count: opposingHitters.filter((h) => tierKpct(num(h['K%'])) && [RED_DARK, RED_MED].includes(tierKpct(num(h['K%']))!)).length },
    { label: 'Tough BB (BB%>11)', count: opposingHitters.filter((h) => tierBb(num(h['BB%'])) && [RED_DARK, RED_MED].includes(tierBb(num(h['BB%']))!)).length },
  ] : [];

  const hasPitcherSplits = !!(pitcherSplits.vs_r || pitcherSplits.vs_l);

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 60px)', overflow: 'hidden', background: theme.bgPage }}>

      {/* ── Left Sidebar ── */}
      <div style={{
        width: 220, flexShrink: 0, background: theme.bgCard, padding: '20px 14px',
        overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16,
      }}>
        <div style={{ color: 'white', fontWeight: 700, fontSize: 15, marginBottom: 4 }}>MLB Matchup</div>
        <div>
          <div style={{ color: theme.textSecondary, fontSize: 12, fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Pitcher</div>
          {loadingPitchers ? (
            <div style={{ color: theme.textSecondary, fontSize: 12, padding: '8px 4px' }}>Loading pitchers…</div>
          ) : (
            <SearchDropdown
              players={pitchers}
              value={selectedPitcher}
              onSelect={(p) => { setSelectedPitcher(p); fetchMatchup(p); }}
              placeholder="Search pitcher..."
              inputStyle={{ padding: '7px 10px', fontSize: 13, width: '100%', boxSizing: 'border-box' }}
            />
          )}
        </div>
        {matchupData && (
          <button
            onClick={downloadPdf}
            disabled={downloadingPdf}
            style={{
              padding: '9px 0', background: downloadingPdf ? theme.bgCardHover : theme.accent, color: downloadingPdf ? theme.textMuted : 'white',
              border: 'none', borderRadius: 4, fontWeight: 700, fontSize: 13,
              cursor: downloadingPdf ? 'not-allowed' : 'pointer',
            }}
          >
            {downloadingPdf ? 'Generating PDF...' : 'Download Matchup Summary Report'}
          </button>
        )}
      </div>

      {/* ── Main Content (full detail) ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
        {loading && <LoadingSpinner />}
        {error && (
          <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
            {error}
          </div>
        )}

        {!loading && matchupData && (
          <div style={{ background: theme.bgPage, padding: 4 }}>

            {/* ── Pitcher Photo + Season Stats ── */}
            <div style={{ ...cardStyle, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
              <img
                src={photoUrl}
                alt={selectedPitcher}
                onError={(e) => { (e.target as HTMLImageElement).style.visibility = 'hidden'; }}
                style={{ width: 80, height: 80, borderRadius: '50%', objectFit: 'cover', border: `3px solid ${theme.border}`, flexShrink: 0 }}
              />
              <div>
                <div style={{ fontWeight: 700, fontSize: 18, color: theme.textPrimary, marginBottom: 10 }}>{selectedPitcher}</div>
                {seasonDisplay.length > 0 && (
                  <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                        {seasonDisplay.map(({ key }) => (
                          <th key={key} style={{ padding: '7px 14px', fontWeight: 600, whiteSpace: 'nowrap' }}>{key}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        {seasonDisplay.map(({ key, val }) => (
                          <td key={key} style={{ padding: '7px 14px', textAlign: 'center', fontWeight: 700, color: theme.textPrimary, whiteSpace: 'nowrap', borderTop: `1px solid ${theme.border}` }}>
                            {String(val ?? '—')}
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* ── Last 10 Starts + Matchup Summary side by side ── */}
            <div style={{ display: 'flex', gap: 20, marginBottom: 20, flexWrap: 'wrap' }}>
              <GameLogTable logs={gameLogsFull} title="Last 10 Starts" />
              <MatchupSummaryTable flags={summaryFlags} />
            </div>

            {/* ── Splits + Percentiles (full detail only -- not in the PDF) ── */}
            {(splits.length > 0 || percentiles.length > 0) && (
              <div style={{ display: 'flex', gap: 20, marginBottom: 20, flexWrap: 'wrap' }}>
                {splits.length > 0 && (
                  <div style={{ ...cardStyle, flex: 1, minWidth: 300, marginBottom: 0 }}>
                    <div style={cardHeaderStyle}>Splits (vs L / vs R) — 2025–2026</div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                        <thead>
                          <tr>{splitsColumns.map((col) => <th key={col} style={thStyle}>{col}</th>)}</tr>
                        </thead>
                        <tbody>
                          {splits.map((row, i) => (
                            <tr key={i} style={{ background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                              {splitsColumns.map((col) => (
                                <td key={col} style={{ ...tdStyle, fontWeight: col === 'Statistic' ? 600 : 400 }}>
                                  {String(row[col] ?? '—')}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div style={{ fontSize: 11, color: theme.textMuted, fontStyle: 'italic', padding: '8px 16px' }}>
                      2026 plate appearances count double relative to 2025 when the two seasons are combined.
                    </div>
                  </div>
                )}
                {percentiles.length > 0 && (
                  <div style={{ ...cardStyle, flex: 1, minWidth: 300, marginBottom: 0 }}>
                    <div style={cardHeaderStyle}>2026 Percentile Rankings</div>
                    <div style={{ padding: '12px 16px' }}>
                      {percentiles.map((row, i) => {
                        const pct = Math.round(Number(row.Percentile));
                        const color = pctBarColor(pct);
                        return (
                          <div key={i} style={{ marginBottom: 10 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 3 }}>
                              <span style={{ fontWeight: 600, color: theme.textSecondary }}>{row.Statistic}</span>
                              <span style={{ fontWeight: 700, color }}>{pct}th</span>
                            </div>
                            <div style={{ background: theme.bgCardHover, borderRadius: 4, height: 10, overflow: 'hidden' }}>
                              <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.4s ease' }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── Opposing Hitters, with conditional formatting -- kept as
                 the LAST section, matching the order used across every PDF
                 draft we iterated on. ── */}
            <OpposingLineupTable hitters={opposingHitters} />
          </div>
        )}

        {!loading && !error && !matchupData && (
          <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 80 }}>
            Select a pitcher to load matchup data.
          </div>
        )}
      </div>

      {/* ── Hidden PDF-only layout: a shorter one-page summary, not a
           screenshot of the full page above. Rendered off-screen at a
           fixed width so it always captures the same landscape layout
           regardless of the browser's actual size. ── */}
      {matchupData && (
        <div
          ref={pdfRef}
          style={{ position: 'fixed', top: 0, left: -10000, width: 1300, background: theme.bgPage, padding: 12 }}
        >
          <div style={{ ...cardStyle, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
            <img
              src={photoUrl}
              alt={selectedPitcher}
              crossOrigin="anonymous"
              style={{ width: 80, height: 80, borderRadius: '50%', objectFit: 'cover', border: `3px solid ${theme.border}`, flexShrink: 0 }}
            />
            <div>
              <div style={{ fontWeight: 700, fontSize: 18, color: theme.textPrimary, marginBottom: 10 }}>{selectedPitcher}</div>
              {seasonDisplay.length > 0 && (
                <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                      {seasonDisplay.map(({ key }) => (
                        <th key={key} style={{ padding: '7px 14px', fontWeight: 600, whiteSpace: 'nowrap' }}>{key}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      {seasonDisplay.map(({ key, val }) => (
                        <td key={key} style={{ padding: '7px 14px', textAlign: 'center', fontWeight: 700, color: theme.textPrimary, whiteSpace: 'nowrap', borderTop: `1px solid ${theme.border}` }}>
                          {String(val ?? '—')}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              )}
            </div>
            {hasPitcherSplits && (
              <div style={{ display: 'flex', gap: 12, marginLeft: 'auto' }}>
                {pitcherSplits.vs_r && <div style={{ width: 200 }}><PitcherSplitTable label="vs. RHB" d={pitcherSplits.vs_r} /></div>}
                {pitcherSplits.vs_l && <div style={{ width: 200 }}><PitcherSplitTable label="vs. LHB" d={pitcherSplits.vs_l} /></div>}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: 20, marginBottom: 20, flexWrap: 'wrap' }}>
            <GameLogTable logs={gameLogsPdf} title="Last 5 Starts" />
            <MatchupSummaryTable flags={summaryFlags} />
          </div>

          <OpposingLineupTable hitters={opposingHitters} />
        </div>
      )}
    </div>
  );
}
