import { useState, useEffect } from 'react';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import { getNFLMatchups, getNFLMatchup } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';

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

// Fixed size everywhere a logo appears -- same dimensions on screen and in
// the printed/PDF version, since the printed version is this same markup
// via the browser's print engine, not a separately rendered document.
const LOGO_SIZE = 56;

function TeamLogo({ teamAbbr }: { teamAbbr: string }) {
  return (
    <img
      src={`/nfl-logos/${teamAbbr}.jpg`}
      alt={`${teamAbbr} logo`}
      width={LOGO_SIZE}
      height={LOGO_SIZE}
      style={{ width: LOGO_SIZE, height: LOGO_SIZE, objectFit: 'contain' }}
      onError={(e) => { (e.target as HTMLImageElement).style.visibility = 'hidden'; }}
    />
  );
}

export default function NFLMatchup() {
  const [matchups, setMatchups] = useState<string[]>([]);
  const [selectedMatchup, setSelectedMatchup] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetchingMatchups, setFetchingMatchups] = useState(true);
  const [error, setError] = useState('');
  const [matchupData, setMatchupData] = useState<MatchupData | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);

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
    try {
      const res = await getNFLMatchup(selectedMatchup);
      setMatchupData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch matchup data.');
    } finally {
      setLoading(false);
    }
  };

  const downloadPdf = async () => {
    const el = document.getElementById('matchup-report');
    if (!el || !matchupData) return;

    setDownloadingPdf(true);
    try {
      // scale: 2 for a crisp image at print resolution -- the element is
      // rendered at normal screen size, so a 1:1 canvas would look soft
      // once placed on a full page.
      const canvas = await html2canvas(el, { scale: 2, backgroundColor: '#ffffff' });
      const imgData = canvas.toDataURL('image/png');

      const pdf = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'letter' });
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const margin = 24;
      const maxWidth = pageWidth - margin * 2;
      const maxHeight = pageHeight - margin * 2;

      // Fit the image to the page while preserving its aspect ratio --
      // whichever dimension would overflow first is the constraint.
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

  // Pair away/home rows by stat name (they're built from the same ordered
  // list server-side, so a simple zip is safe) -- one unified table with
  // the stat name down the middle reads much more like a classic matchup
  // comparison than two separate side-by-side tables, and naturally fits
  // one printed page instead of two independently-wrapping blocks.
  const rows = matchupData
    ? matchupData.away_stats.map((away, i) => ({ away, home: matchupData.home_stats[i] }))
    : [];

  return (
    <div style={{ padding: 24, overflowY: 'auto', minHeight: 'calc(100vh - 60px)' }}>
      <div id="no-print">
        <h2 style={{ marginTop: 0, marginBottom: 24, color: '#1a1a2e' }}>NFL Matchup Preview</h2>

        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 28 }}>
          <div>
            <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Select Matchup</label>
            {fetchingMatchups ? (
              <div style={{ fontSize: 13, color: '#999', padding: '8px 0' }}>Loading matchups...</div>
            ) : matchups.length === 0 ? (
              <div style={{ fontSize: 13, color: '#999', padding: '8px 0' }}>
                No upcoming matchups yet -- the current week's games haven't been played.
              </div>
            ) : (
              <select
                style={{ padding: '8px 12px', border: '1px solid #ddd', borderRadius: 4, fontSize: 14, minWidth: 240 }}
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
              padding: '9px 24px', background: '#1a1a2e', color: 'white', border: 'none',
              borderRadius: 4, fontWeight: 700, fontSize: 14,
              cursor: selectedMatchup && !loading ? 'pointer' : 'not-allowed',
              opacity: selectedMatchup && !loading ? 1 : 0.6,
            }}
          >
            Analyze
          </button>
          {matchupData && (
            <button
              onClick={downloadPdf}
              disabled={downloadingPdf}
              style={{
                padding: '9px 24px', background: 'white', color: '#1a1a2e',
                border: '1px solid #1a1a2e', borderRadius: 4, fontWeight: 700, fontSize: 14,
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
          <div style={{ background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 4, padding: 16, color: '#c0392b', marginBottom: 16 }}>
            {error}
          </div>
        )}
        {!loading && !error && !matchupData && !fetchingMatchups && (
          <div style={{ color: '#999', textAlign: 'center', fontSize: 16, marginTop: 60 }}>
            Select a matchup and click "Analyze" to preview both teams.
          </div>
        )}
      </div>

      {!loading && matchupData && (
        <div id="matchup-report" style={{ maxWidth: 900, margin: '0 auto' }}>
          {matchupData.is_fallback && (
            <div style={{
              background: '#fff3cd', border: '1px solid #ffe08a', color: '#7a5c00',
              borderRadius: 4, padding: '10px 16px', marginBottom: 16, textAlign: 'center', fontSize: 13,
            }}>
              The {matchupData.stats_season! + 1} season hasn't started yet -- these stats are from the{' '}
              {matchupData.stats_season} regular season (through week {matchupData.stats_through_week}).
            </div>
          )}

          <div style={{
            background: 'white', borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.08)', overflow: 'hidden',
          }}>
            {/* Header: logo -- team -- @ -- team -- logo, mirrored across center */}
            <div style={{
              background: '#1a1a2e', padding: '20px 24px',
              display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', gap: 16,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, justifyContent: 'flex-end' }}>
                <span style={{ color: 'white', fontWeight: 700, fontSize: 22 }}>{matchupData.away_team}</span>
                <TeamLogo teamAbbr={matchupData.away_team} />
              </div>
              <span style={{ color: '#8890a8', fontWeight: 700, fontSize: 16 }}>@</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, justifyContent: 'flex-start' }}>
                <TeamLogo teamAbbr={matchupData.home_team} />
                <span style={{ color: 'white', fontWeight: 700, fontSize: 22 }}>{matchupData.home_team}</span>
              </div>
            </div>

            {/* Column sub-headers */}
            <div style={{
              display: 'grid', gridTemplateColumns: '1fr 1.4fr 1fr', background: '#f0f0f0',
              padding: '8px 16px', fontSize: 11, color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.4,
            }}>
              <div style={{ textAlign: 'center' }}>{matchupData.away_team}</div>
              <div style={{ textAlign: 'center' }}>Stat</div>
              <div style={{ textAlign: 'center' }}>{matchupData.home_team}</div>
            </div>

            {rows.map((row, i) => {
              // Highlight whichever side ranks better for this stat -- a
              // quick visual "who has the edge here" read, since that's
              // the whole point of a matchup comparison for a bettor.
              const awayBetter = row.away.rank != null && row.home.rank != null && row.away.rank < row.home.rank;
              const homeBetter = row.away.rank != null && row.home.rank != null && row.home.rank < row.away.rank;
              const edgeColor = '#1a7a3a';

              return (
                <div
                  key={row.away.stat}
                  style={{
                    display: 'grid', gridTemplateColumns: '1fr 1.4fr 1fr', alignItems: 'center',
                    padding: '9px 16px', background: i % 2 === 0 ? '#fff' : '#fafafa',
                    borderBottom: '1px solid #f0f0f0',
                  }}
                >
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontWeight: 700, fontSize: 15, color: awayBetter ? edgeColor : '#1a1a2e' }}>
                      {row.away.value ?? '—'}
                    </div>
                    <div style={{ fontSize: 12, color: '#555' }}>
                      {row.away.rank != null ? ordinal(row.away.rank) : '—'}
                    </div>
                  </div>
                  <div style={{ textAlign: 'center', fontSize: 13, color: '#555', fontWeight: 600 }}>
                    {row.away.stat}
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontWeight: 700, fontSize: 15, color: homeBetter ? edgeColor : '#1a1a2e' }}>
                      {row.home.value ?? '—'}
                    </div>
                    <div style={{ fontSize: 12, color: '#555' }}>
                      {row.home.rank != null ? ordinal(row.home.rank) : '—'}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
