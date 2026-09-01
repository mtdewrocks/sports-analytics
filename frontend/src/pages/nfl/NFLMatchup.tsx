import { useState, useEffect } from 'react';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import { getNFLMatchups, getNFLMatchup, getNFLGameScript } from '../../api/nfl';
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

interface PlayerVolume {
  player: string;
  season_volume: number | null;
  season_share: number | null;
  bucket_volume: number | null;
  bucket_share: number | null;
}

interface TeamGameScript {
  team: string;
  implied_situation: string;
  baseline_pass_pct: number | null;
  projected_pass_pct: number | null;
  top_rushers: PlayerVolume[];
  top_receivers: PlayerVolume[];
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
  if (rank == null) return '#1a1a2e';
  if (rank <= 10) return '#1565c0';
  if (rank >= 23) return '#c62828';
  return '#1a1a2e';
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

function TeamCard({ teamAbbr, stats }: { teamAbbr: string; stats: StatRow[] }) {
  return (
    <div style={{ flex: 1, minWidth: 320, background: 'white', borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.08)', overflow: 'hidden' }}>
      <div style={{ background: '#1a1a2e', color: 'white', padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <TeamLogo teamAbbr={teamAbbr} />
        <span style={{ fontWeight: 700, fontSize: 20 }}>{teamAbbr}</span>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 18 }}>
        <thead>
          <tr style={{ background: '#f0f0f0' }}>
            <th style={{ padding: '11px 16px', textAlign: 'left', fontSize: 14, color: '#666' }}>Stat</th>
            <th style={{ padding: '11px 16px', textAlign: 'right', fontSize: 14, color: '#666' }}>Value</th>
            <th style={{ padding: '11px 16px', textAlign: 'right', fontSize: 14, color: '#666' }}>Rank</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((row, i) => {
            const color = rankColor(row.rank);
            return (
              <tr key={row.stat} style={{ borderBottom: '1px solid #f0f0f0', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                <td style={{ padding: '10px 16px', fontWeight: 600, color: '#555' }}>{row.stat}</td>
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

function PlayerVolumeTable({ title, players }: { title: string; players: PlayerVolume[] }) {
  if (players.length === 0) return null;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: '#666', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.3 }}>{title}</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #ddd' }}>
            <th style={{ textAlign: 'left', padding: '5px 6px', color: '#888', fontWeight: 600 }}>Player</th>
            <th style={{ textAlign: 'right', padding: '5px 6px', color: '#888', fontWeight: 600 }}>Season</th>
            <th style={{ textAlign: 'right', padding: '5px 6px', color: '#888', fontWeight: 600 }}>In script</th>
          </tr>
        </thead>
        <tbody>
          {players.map((p) => (
            <tr key={p.player} style={{ borderBottom: '1px solid #f0f0f0' }}>
              <td style={{ padding: '6px', fontWeight: 600 }}>{p.player}</td>
              <td style={{ padding: '6px', textAlign: 'right' }}>
                {p.season_volume ?? '—'} <span style={{ color: '#999' }}>({p.season_share ?? '—'}%)</span>
              </td>
              <td style={{ padding: '6px', textAlign: 'right' }}>
                {p.bucket_volume ?? '—'} <span style={{ color: '#999' }}>({p.bucket_share ?? '—'}%)</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GameScriptTeamPanel({ data }: { data: TeamGameScript }) {
  if (data.error) {
    return <div style={{ flex: 1, minWidth: 280, color: '#999', fontSize: 13 }}>{data.error}</div>;
  }
  const delta = data.projected_pass_pct != null && data.baseline_pass_pct != null
    ? data.projected_pass_pct - data.baseline_pass_pct : null;
  return (
    <div style={{ flex: 1, minWidth: 280, background: 'white', borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.08)', padding: 16 }}>
      <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>{data.team}</div>
      <div style={{ fontSize: 12, color: '#888', marginBottom: 10 }}>Implied script: {situationLabel(data.implied_situation)}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 26, fontWeight: 700 }}>{data.projected_pass_pct ?? '—'}%</span>
        <span style={{ fontSize: 12, color: '#999' }}>projected pass rate</span>
      </div>
      <div style={{ fontSize: 12, color: '#999', marginBottom: 14 }}>
        close-game rate {data.baseline_pass_pct ?? '—'}%
        {delta != null && (
          <span style={{ color: delta < 0 ? '#1565c0' : '#c62828', fontWeight: 600 }}> ({delta > 0 ? '+' : ''}{delta.toFixed(1)})</span>
        )}
      </div>
      <PlayerVolumeTable title="Rushers" players={data.top_rushers} />
      <PlayerVolumeTable title="Receivers" players={data.top_receivers} />
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
    const page1 = document.getElementById('pdf-page-1');
    const page2 = document.getElementById('pdf-page-2');
    if (!page1 || !matchupData) return;

    setDownloadingPdf(true);
    try {
      const pdf = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'letter' });
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const margin = 24;

      const addCanvasPage = async (el: HTMLElement, isFirst: boolean) => {
        const canvas = await html2canvas(el, { scale: 2, backgroundColor: '#ffffff' });
        const imgData = canvas.toDataURL('image/png');
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
        if (!isFirst) pdf.addPage();
        pdf.addImage(imgData, 'PNG', x, y, renderWidth, renderHeight);
      };

      await addCanvasPage(page1, true);
      if (page2 && gameScript && !gameScript.error) {
        await addCanvasPage(page2, false);
      }

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
        <>
          {/* Page 1 of the PDF: the standard team stat comparison */}
          <div id="pdf-page-1" style={{ maxWidth: 900, margin: '0 auto' }}>
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

          {/* Page 2 of the PDF: projected game script */}
          {gameScript && !gameScript.error && (
            <div id="pdf-page-2" style={{ maxWidth: 900, margin: '32px auto 0' }}>
              <h3 style={{ textAlign: 'center', color: '#1a1a2e', marginBottom: 4 }}>Projected Game Script</h3>
              <div style={{ textAlign: 'center', fontSize: 13, color: '#888', marginBottom: 16 }}>
                {gameScript.away_team} @ {gameScript.home_team} &middot; spread {gameScript.spread_line > 0 ? '+' : ''}{gameScript.spread_line} (home)
                {gameScript.total_line != null && <> &middot; O/U {gameScript.total_line}</>}
              </div>
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                <GameScriptTeamPanel data={gameScript.away} />
                <GameScriptTeamPanel data={gameScript.home} />
              </div>
              <div style={{ fontSize: 11, color: '#aaa', textAlign: 'center', marginTop: 16 }}>
                Projection blends each team's season-long tendency toward its historical rate in the situation
                the spread implies, weighted more heavily in later quarters -- not a guarantee of how the game plays out.
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
