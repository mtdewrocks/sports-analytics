import { useState, useEffect } from 'react';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import { getNFLMatchups, getNFLMatchup, getNFLGameScript } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import { NAV_HEIGHT, CHIPBAR_HEIGHT } from '../../components/Navbar';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

interface StatRow {
  stat: string;
  value: number | null;
  rank: number | null;
}

interface MatchupData {
  matchup: string;
  away_team: string;
  home_team: string;
  away_stats: StatRow[];
  home_stats: StatRow[];
  stats_season: number | null;
  stats_through_week: number | null;
  is_fallback: boolean;
}

interface TeamGameScript {
  team: string;
  implied_situation: string;
  implied_total: number | null;
  weekly_scoring_rank: number | null;
  weekly_scoring_favorable: boolean | null;
  baseline_pass_pct: number | null;
  projected_pass_pct: number | null;
  error?: string;
}

interface GameScriptData {
  matchup: string;
  away_team: string;
  home_team: string;
  spread_line: number;
  total_line: number | null;
  away: TeamGameScript;
  home: TeamGameScript;
  error?: string;
}

function ordinal(n: number): string {
  const rem100 = n % 100;
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1: return `${n}st`;
    case 2: return `${n}nd`;
    case 3: return `${n}rd`;
    default: return `${n}th`;
  }
}

function situationLabel(s: string): string {
  const labels: Record<string, string> = {
    trailing_big: 'trailing big', trailing: 'trailing', tied: 'a close game',
    leading: 'leading', leading_big: 'leading big',
  };
  return labels[s] ?? s;
}

function rankColor(rank: number | null | undefined): string {
  if (rank == null) return theme.textPrimary;
  if (rank <= 10) return theme.dataBlue;
  if (rank >= 23) return theme.dataRed;
  return theme.textPrimary;
}

const LOGO_SIZE = 56;

function TeamLogo({ teamAbbr }: { teamAbbr: string }) {
  return (
    <img
      src={`/nfl-logos/${teamAbbr}.jpg`}
      alt={`${teamAbbr} logo`}
      width={LOGO_SIZE}
      height={LOGO_SIZE}
      style={{ width: LOGO_SIZE, height: LOGO_SIZE, objectFit: 'contain', borderRadius: 4, background: 'white' }}
      onError={(e) => { (e.target as HTMLImageElement).style.visibility = 'hidden'; }}
    />
  );
}

function TeamCard({ teamAbbr, stats, impliedTotal, weeklyRank, weeklyFavorable }: {
  teamAbbr: string; stats: StatRow[]; impliedTotal?: number | null;
  weeklyRank?: number | null; weeklyFavorable?: boolean | null;
}) {
  const badgeColor = weeklyFavorable === true ? theme.dataBlue : weeklyFavorable === false ? theme.dataRed : theme.textSecondary;
  return (
    <div style={{ flex: 1, minWidth: 320, background: theme.bgCard, borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.4)', overflow: 'hidden' }}>
      <div style={{ background: theme.bgCardHover, color: theme.textPrimary, padding: '14px 20px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
        <TeamLogo teamAbbr={teamAbbr} />
        <span style={{ fontWeight: 700, fontSize: 20 }}>{teamAbbr}</span>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 18 }}>
        <thead>
          <tr style={{ background: theme.bgCardHover }}>
            <th style={{ padding: '11px 16px', textAlign: 'left', fontSize: 14, color: theme.textSecondary }}>Stat</th>
            <th style={{ padding: '11px 16px', textAlign: 'right', fontSize: 14, color: theme.textSecondary }}>Value</th>
            <th style={{ padding: '11px 16px', textAlign: 'right', fontSize: 14, color: theme.textSecondary }}>Rank</th>
          </tr>
        </thead>
        <tbody>
          {impliedTotal != null && (
            <tr style={{ borderBottom: `1px solid ${theme.border}`, background: theme.bgCard }}>
              <td style={{ padding: '10px 16px', fontWeight: 600, color: theme.textPrimary }}>Projected Points</td>
              <td style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 700, color: theme.textPrimary }}>{impliedTotal}</td>
              <td style={{ padding: '10px 16px', textAlign: 'right' }}>
                {weeklyRank != null && (
                  <span style={{ fontSize: 11, fontWeight: 700, color: badgeColor, border: `1px solid ${badgeColor}`, borderRadius: 4, padding: '2px 6px' }}>
                    {ordinal(weeklyRank)} WK
                  </span>
                )}
              </td>
            </tr>
          )}
          {stats.map((row, i) => {
            const color = rankColor(row.rank);
            return (
              <tr key={row.stat} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                <td style={{ padding: '10px 16px', fontWeight: 600, color: theme.textPrimary }}>{row.stat}</td>
                <td style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 700, color }}>{row.value ?? '—'}</td>
                <td style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 600, color }}>{row.rank != null ? ordinal(row.rank) : '—'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * One stat, both teams, on a phone.
 *
 * The two team cards side by side are the whole point of this page, and at
 * 390px they stack -- which means comparing two numbers costs a scroll. So on
 * mobile the stat label moves to the middle and the two values flank it, and
 * the bar underneath is a diverging split rather than a magnitude bar: it shows
 * WHO is better and by how much, coloured with the leader's own rank tier.
 */
/** Width of each value column. The sticky team header uses the same number, so
 *  each abbreviation sits directly over the column it labels. */
const H2H_COL = 64;

/** Rank gaps at or under this are noise, not an edge -- two adjacent ranks can
 *  be a tenth of a yard apart. */
const EVEN_THRESHOLD = 2;

function HeadToHeadRow({ label, away, home, awayTeam, homeTeam }: {
  label: string;
  away: { value: number | null; rank: number | null };
  home: { value: number | null; rank: number | null };
  awayTeam: string;
  homeTeam: string;
}) {
  const bothRanked = away.rank != null && home.rank != null;
  const gap = bothRanked ? Math.abs(away.rank! - home.rank!) : 0;
  const awayLeads = bothRanked && away.rank! < home.rank!;
  const even = bothRanked && gap <= EVEN_THRESHOLD;

  // The bar is anchored at the centre and grows toward the leader, with its
  // length set by the SIZE of the rank gap (out of 31 possible). An earlier
  // version sized it by the ratio of the two ranks, which drew 17th-vs-16th as
  // half the row -- a one-rank difference reading as a decisive edge.
  const barPct = bothRanked ? Math.min((gap / 31) * 100, 50) : 0;

  return (
    <div style={{ background: theme.bgCard, borderRadius: 8, padding: '11px 13px', marginBottom: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{
          fontSize: 17, fontWeight: 700, fontVariantNumeric: 'tabular-nums',
          color: rankColor(away.rank), flex: `0 0 ${H2H_COL}px`, width: H2H_COL,
        }}>
          {away.value ?? '—'}
        </span>
        <span style={{
          fontSize: 10, color: theme.textMuted, textTransform: 'uppercase',
          letterSpacing: '0.05em', textAlign: 'center', flex: 1, lineHeight: 1.25, minWidth: 0,
        }}>
          {label}
        </span>
        <span style={{
          fontSize: 17, fontWeight: 700, fontVariantNumeric: 'tabular-nums',
          color: rankColor(home.rank), flex: `0 0 ${H2H_COL}px`, width: H2H_COL, textAlign: 'right',
        }}>
          {home.value ?? '—'}
        </span>
      </div>

      {bothRanked && (
        <div style={{
          position: 'relative', height: 4, borderRadius: 2,
          background: theme.border, marginTop: 8,
        }}>
          {/* Centre tick, so a short bar still reads as "grows from the middle"
              rather than as a stub floating in a track. */}
          <div style={{
            position: 'absolute', left: '50%', top: -2, width: 1, height: 8,
            background: theme.borderStrong, transform: 'translateX(-0.5px)',
          }} />
          {!even && (
            <div style={{
              position: 'absolute', top: 0, height: '100%', borderRadius: 2,
              width: `${barPct}%`,
              [awayLeads ? 'right' : 'left']: '50%',
              background: rankColor(awayLeads ? away.rank : home.rank),
            }} />
          )}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginTop: 5 }}>
        <span style={{
          fontSize: 10.5, color: rankColor(away.rank), fontWeight: 600,
          flex: `0 0 ${H2H_COL}px`, width: H2H_COL,
        }}>
          {away.rank != null ? ordinal(away.rank) : '—'}
        </span>
        <span style={{ flex: 1, textAlign: 'center', fontSize: 10.5, minWidth: 0 }}>
          {!bothRanked ? null : even ? (
            <span style={{ color: theme.textMuted }}>Even</span>
          ) : (
            <span style={{ color: theme.textSecondary }}>
              Advantage:{' '}
              <span style={{ color: theme.textPrimary, fontWeight: 700 }}>
                {awayLeads ? awayTeam : homeTeam}
              </span>
            </span>
          )}
        </span>
        <span style={{
          fontSize: 10.5, color: rankColor(home.rank), fontWeight: 600,
          flex: `0 0 ${H2H_COL}px`, width: H2H_COL, textAlign: 'right',
        }}>
          {home.rank != null ? ordinal(home.rank) : '—'}
        </span>
      </div>
    </div>
  );
}

function HeadToHead({ data, gameScript }: { data: MatchupData; gameScript: GameScriptData | null }) {
  // Match by stat name rather than by index -- the two arrays should align, but
  // a mismatch would silently compare the wrong two numbers, which is worse
  // than showing a dash.
  const rows = data.away_stats.map((a) => ({
    stat: a.stat,
    away: a,
    home: data.home_stats.find((h) => h.stat === a.stat) ?? { stat: a.stat, value: null, rank: null },
  }));

  const awayTotal = gameScript?.away?.implied_total;
  const homeTotal = gameScript?.home?.implied_total;

  return (
    <div>
      {/* Sticky, and the abbreviations are pinned to the same column widths the
          values use -- so each team name sits directly over its own numbers and
          stays there once you've scrolled past the top of the page. Without
          this you're twelve rows deep guessing which column is which. */}
      <div style={{
        position: 'sticky', top: NAV_HEIGHT + CHIPBAR_HEIGHT, zIndex: 5,
        background: theme.bgCard, borderRadius: 8, padding: '10px 13px', marginBottom: 8,
        boxShadow: `0 4px 14px ${theme.bgPage}`, border: `1px solid ${theme.border}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <span style={{
            fontSize: 16, fontWeight: 700, color: theme.textPrimary,
            flex: `0 0 ${H2H_COL}px`, width: H2H_COL,
          }}>
            {data.away_team}
          </span>
          <span style={{ flex: 1, textAlign: 'center', fontSize: 11, color: theme.textSecondary, minWidth: 0 }}>
            {gameScript?.total_line != null ? (
              <>
                O/U {gameScript.total_line}
                {gameScript.spread_line != null && (
                  <>
                    <br />
                    <span style={{ color: theme.textMuted }}>
                      spread {gameScript.spread_line > 0 ? '+' : ''}{gameScript.spread_line} (home)
                    </span>
                  </>
                )}
              </>
            ) : (
              <span style={{ color: theme.textMuted }}>@</span>
            )}
          </span>
          <span style={{
            fontSize: 16, fontWeight: 700, color: theme.textPrimary,
            flex: `0 0 ${H2H_COL}px`, width: H2H_COL, textAlign: 'right',
          }}>
            {data.home_team}
          </span>
        </div>
      </div>

      {(awayTotal != null || homeTotal != null) && (
        <HeadToHeadRow
          label="Projected Points"
          away={{ value: awayTotal ?? null, rank: gameScript?.away?.weekly_scoring_rank ?? null }}
          home={{ value: homeTotal ?? null, rank: gameScript?.home?.weekly_scoring_rank ?? null }}
          awayTeam={data.away_team}
          homeTeam={data.home_team}
        />
      )}

      {rows.map((r) => (
        <HeadToHeadRow
          key={r.stat}
          label={r.stat}
          away={r.away}
          home={r.home}
          awayTeam={data.away_team}
          homeTeam={data.home_team}
        />
      ))}
    </div>
  );
}

function GameScriptTeamPanel({ data }: { data: TeamGameScript }) {
  if (data.error) {
    return <div style={{ flex: 1, minWidth: 280, color: theme.textSecondary, fontSize: 13 }}>{data.error}</div>;
  }
  const delta = data.projected_pass_pct != null && data.baseline_pass_pct != null
    ? data.projected_pass_pct - data.baseline_pass_pct : null;
  return (
    <div style={{ flex: 1, minWidth: 280, background: theme.bgCard, borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.4)', padding: 16 }}>
      <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4, color: theme.textPrimary }}>{data.team}</div>
      <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 10 }}>Implied script: {situationLabel(data.implied_situation)}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 26, fontWeight: 700, color: theme.textPrimary }}>{data.projected_pass_pct ?? '—'}%</span>
        <span style={{ fontSize: 12, color: theme.textSecondary }}>projected pass rate</span>
      </div>
      <div style={{ fontSize: 12, color: theme.textSecondary }}>
        close-game rate {data.baseline_pass_pct ?? '—'}%
        {delta != null && (
          <span style={{ color: delta < 0 ? theme.dataBlue : theme.dataRed, fontWeight: 600 }}> ({delta > 0 ? '+' : ''}{delta.toFixed(1)})</span>
        )}
      </div>
    </div>
  );
}

export default function NFLMatchup() {
  const [matchups, setMatchups] = useState<string[]>([]);
  const [selectedMatchup, setSelectedMatchup] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetchingMatchups, setFetchingMatchups] = useState(true);
  const [error, setError] = useState('');
  const [matchupData, setMatchupData] = useState<MatchupData | null>(null);
  const [gameScript, setGameScript] = useState<GameScriptData | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const isMobile = useIsMobile();

  useEffect(() => {
    getNFLMatchups()
      .then((res) => {
        setMatchups(res.data);
        if (res.data.length > 0) setSelectedMatchup(res.data[0]);
      })
      .catch(() => setMatchups([]))
      .finally(() => setFetchingMatchups(false));
  }, []);

  const analyze = async () => {
    if (!selectedMatchup) return;
    setLoading(true);
    setError('');
    setMatchupData(null);
    setGameScript(null);
    try {
      const [matchupRes, scriptRes] = await Promise.all([
        getNFLMatchup(selectedMatchup),
        getNFLGameScript(selectedMatchup).catch(() => ({ data: null })),
      ]);
      setMatchupData(matchupRes.data);
      setGameScript(scriptRes.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch matchup data.');
    } finally {
      setLoading(false);
    }
  };

  const downloadPdf = async () => {
    const page = document.getElementById('pdf-page-1');
    if (!page || !matchupData) return;

    setDownloadingPdf(true);
    try {
      const canvas = await html2canvas(page, { scale: 2, backgroundColor: theme.bgPage });
      const imgData = canvas.toDataURL('image/png');

      const pdf = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'letter' });
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const margin = 24;
      const maxWidth = pageWidth - margin * 2;
      const maxHeight = pageHeight - margin * 2;

      const imgRatio = canvas.width / canvas.height;
      let renderWidth = maxWidth;
      let renderHeight = renderWidth / imgRatio;
      if (renderHeight > maxHeight) {
        renderHeight = maxHeight;
        renderWidth = renderHeight * imgRatio;
      }
      const x = (pageWidth - renderWidth) / 2;
      const y = (pageHeight - renderHeight) / 2;

      pdf.addImage(imgData, 'PNG', x, y, renderWidth, renderHeight);
      pdf.save(`${matchupData.away_team}_at_${matchupData.home_team}.pdf`);
    } catch (err) {
      setError('Failed to generate PDF. Please try again.');
    } finally {
      setDownloadingPdf(false);
    }
  };

  return (
    <div style={{
      padding: isMobile ? 16 : 24,
      // `overflow-y: auto` here makes THIS element the scroll container for any
      // descendant using position: sticky -- and since the document is what
      // actually scrolls, a sticky child would never move. The page scrolls
      // fine without it, so on mobile it stays visible and the team header
      // inside HeadToHead can pin to the viewport.
      overflowY: isMobile ? 'visible' : 'auto',
      minHeight: 'calc(100vh - 60px)', background: theme.bgPage,
    }}>
      <div id="no-print">
        <h2 style={{ marginTop: 0, marginBottom: 24, color: theme.textPrimary }}>NFL Matchup Preview</h2>

        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 28 }}>
          <div>
            <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>Select Matchup</label>
            {fetchingMatchups ? (
              <div style={{ fontSize: 13, color: theme.textSecondary, padding: '8px 0' }}>Loading matchups...</div>
            ) : matchups.length === 0 ? (
              <div style={{ fontSize: 13, color: theme.textSecondary, padding: '8px 0' }}>
                No upcoming matchups yet -- the current week's games haven't been played.
              </div>
            ) : (
              <select
                style={{ padding: '8px 12px', border: `1px solid ${theme.border}`, borderRadius: 4, fontSize: 14, minWidth: 240, background: theme.bgCard, color: theme.textPrimary }}
                value={selectedMatchup}
                onChange={(e) => setSelectedMatchup(e.target.value)}
              >
                <option value="">-- Select Matchup --</option>
                {matchups.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            )}
          </div>
          <button
            onClick={analyze}
            disabled={!selectedMatchup || loading}
            style={{
              padding: '9px 24px', background: theme.accent, color: 'white', border: 'none',
              borderRadius: 4, fontWeight: 700, fontSize: 14,
              cursor: selectedMatchup && !loading ? 'pointer' : 'not-allowed',
              opacity: selectedMatchup && !loading ? 1 : 0.6,
            }}
          >
            Analyze
          </button>
          {/* The PDF renders the 1300px desktop layout, which is a download you
              can't read on a phone without pinching -- so it's a desktop action. */}
          {matchupData && !isMobile && (
            <button
              onClick={downloadPdf}
              disabled={downloadingPdf}
              style={{
                padding: '9px 24px', background: 'transparent', color: theme.accent,
                border: `1px solid ${theme.accent}`, borderRadius: 4, fontWeight: 700, fontSize: 14,
                cursor: downloadingPdf ? 'not-allowed' : 'pointer',
                opacity: downloadingPdf ? 0.6 : 1,
              }}
            >
              {downloadingPdf ? 'Generating PDF...' : 'Download PDF'}
            </button>
          )}
        </div>

        {loading && <LoadingSpinner />}
        {error && (
          <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
            {error}
          </div>
        )}
        {!loading && !error && !matchupData && !fetchingMatchups && (
          <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 60 }}>
            Select a matchup and click "Analyze" to preview both teams.
          </div>
        )}
      </div>

      {!loading && matchupData && (
        <div id="pdf-page-1" style={{ maxWidth: 1300, margin: '0 auto' }}>
          {matchupData.is_fallback && (
            <div style={{
              background: 'rgba(232,163,61,0.12)', border: `1px solid ${theme.warningText}`, color: theme.warningText,
              borderRadius: 4, padding: '10px 16px', marginBottom: 16, textAlign: 'center', fontSize: 13,
            }}>
              The {matchupData.stats_season! + 1} season hasn't started yet -- these stats are from the{' '}
              {matchupData.stats_season} regular season (through week {matchupData.stats_through_week}).
            </div>
          )}
          {isMobile ? (
            <HeadToHead data={matchupData} gameScript={gameScript} />
          ) : (
            <>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 20 }}>
                <div style={{ background: theme.bgCard, borderRadius: 8, padding: '18px 32px', textAlign: 'center', minWidth: 220 }}>
                  <div style={{ fontSize: 22, fontWeight: 700, color: theme.textPrimary, marginBottom: 6 }}>
                    {matchupData.away_team} @ {matchupData.home_team}
                  </div>
                  {gameScript?.total_line != null && (
                    <div style={{ fontSize: 26, fontWeight: 700, color: theme.textPrimary }}>O/U {gameScript.total_line}</div>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                <TeamCard
                  teamAbbr={matchupData.away_team}
                  stats={matchupData.away_stats}
                  impliedTotal={gameScript?.away?.implied_total}
                  weeklyRank={gameScript?.away?.weekly_scoring_rank}
                  weeklyFavorable={gameScript?.away?.weekly_scoring_favorable}
                />
                <TeamCard
                  teamAbbr={matchupData.home_team}
                  stats={matchupData.home_stats}
                  impliedTotal={gameScript?.home?.implied_total}
                  weeklyRank={gameScript?.home?.weekly_scoring_rank}
                  weeklyFavorable={gameScript?.home?.weekly_scoring_favorable}
                />
              </div>
            </>
          )}

          {gameScript && !gameScript.error && (
            <div style={{ marginTop: 32 }}>
              <h3 style={{ textAlign: 'center', color: theme.textPrimary, marginBottom: 4 }}>Projected Game Script</h3>
              <div style={{ textAlign: 'center', fontSize: 13, color: theme.textSecondary, marginBottom: 16 }}>
                {gameScript.away_team} @ {gameScript.home_team} &middot; spread {gameScript.spread_line > 0 ? '+' : ''}{gameScript.spread_line} (home)
                {gameScript.total_line != null && <> &middot; O/U {gameScript.total_line}</>}
              </div>
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                <GameScriptTeamPanel data={gameScript.away} />
                <GameScriptTeamPanel data={gameScript.home} />
              </div>
              <div style={{ fontSize: 11, color: theme.textMuted, textAlign: 'center', marginTop: 16 }}>
                Projection blends each team's season-long tendency toward its historical rate in the situation
                the spread implies, weighted more heavily in later quarters -- not a guarantee of how the game plays out.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
