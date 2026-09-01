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

// Absolute tiers out of 32 teams -- top 10 / bottom 10 / the 12 in between --
// rather than comparing the two teams in the matchup against each other.
// A team can be "blue" here even if its opponent is also blue.
function rankColor(rank: number | null): string {
  if (rank == null) return '#1a1a2e';
  if (rank <= 10) return '#1565c0';   // blue: top 10
  if (rank >= 23) return '#c62828';   // red: bottom 10
  return '#1a1a2e';                    // black: middle of the pack
}

// Fixed size everywhere a logo appears -- same dimensions on screen and in
// the downloaded PDF, since the PDF is a snapshot of this same markup.
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

function TeamCard({ teamAbbr, stats }: { teamAbbr: string; stats: StatRow[] }) {
  return (
    <div style={{
      flex: 1,
      minWidth: 320,
      background: 'white',
      borderRadius: 8,
      boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
      overflow: 'hidden',
    }}>
      <div style={{
        background: '#1a1a2e', color: 'white', padding: '14px 20px',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <TeamLogo teamAbbr={teamAbbr} />
        <span style={{ fontWeight: 700, fontSize: 20 }}>{teamAbbr}</span>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ background: '#f0f0f0' }}>
            <th style={{ padding: '8px 16px', textAlign: 'left', fontSize: 12, color: '#666' }}>Stat</th>
            <th style={{ padding: '8px 16px', textAlign: 'right', fontSize: 12, color: '#666' }}>Value</th>
            <th style={{ padding: '8px 16px', textAlign: 'right', fontSize: 12, color: '#666' }}>Rank</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((row, i) => {
            const color = rankColor(row.rank);
            return (
              <tr key={row.stat} style={{ borderBottom: '1px solid #f0f0f0', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                <td style={{ padding: '7px 16px', fontWeight: 600, color: '#555' }}>{row.stat}</td>
                <td style={{ padding: '7px 16px', textAlign: 'right', fontWeight: 700, color }}>
                  {row.value ?? '—'}
                </td>
                <td style={{ padding: '7px 16px', textAlign: 'right', fontWeight: 600, color }}>
                  {row.rank != null ? ordinal(row.rank) : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
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
      const canvas = await html2canvas(el, { scale: 2, backgroundColor: '#ffffff' });
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
        <div id="matchup-report">
          {matchupData.is_fallback && (
            <div style={{
              background: '#fff3cd', border: '1px solid #ffe08a', color: '#7a5c00',
              borderRadius: 4, padding: '10px 16px', marginBottom: 16, textAlign: 'center', fontSize: 13,
            }}>
              The {matchupData.stats_season! + 1} season hasn't started yet -- these stats are from the{' '}
              {matchupData.stats_season} regular season (through week {matchupData.stats_through_week}).
            </div>
          )}
          <h2 style={{ textAlign: 'center', color: '#1a1a2e', marginBottom: 20 }}>
            {matchupData.away_team} @ {matchupData.home_team}
          </h2>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <TeamCard teamAbbr={matchupData.away_team} stats={matchupData.away_stats} />
            <TeamCard teamAbbr={matchupData.home_team} stats={matchupData.home_stats} />
          </div>
        </div>
      )}
    </div>
  );
}
