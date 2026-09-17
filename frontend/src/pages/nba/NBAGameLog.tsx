import { useState, useEffect } from 'react';
import { getNBAPlayers, getNBATeammates, getNBAGameLog } from '../../api/nba';
import StatChart from '../../components/StatChart';
import OverCountsTable from '../../components/OverCountsTable';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import StatCard from '../../components/StatCard';
import FilterPanel from '../../components/FilterPanel';
import { fieldLabelStyle, fieldStyle, usePanelLayout } from '../../components/filterStyles';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

// Was a hand-rolled two-column layout (fixed 240px sidebar + flex-1 content)
// with no mobile handling at all -- fine on desktop, but on a phone the
// sidebar alone ate the width and the 7-column table ran off the edge. Now
// built on the same FilterPanel / usePanelLayout / StatCard pieces the NFL
// Game Log page already uses, so it collapses the same way that one does:
// filters stack full-width on top, secondary ones move behind a disclosure,
// and the table becomes a card per game.

const STAT_OPTIONS = ['pts', 'reb', 'ast', 'stl', 'blk', 'tov', '3pm', 'pra', 'blk_stl', 'reb_ast', 'pts_ast', 'pts_reb'];

interface Game {
  game_date: string;
  opponent: string;
  stat_value: number;
  min?: number | string;
  fgm?: number | null;
  fga?: number | null;
}

interface OverCount {
  over: number;
  total: number;
  pct: number;
}

interface GameData {
  games: Game[];
  over_counts: {
    last5: OverCount;
    last10: OverCount;
    season: OverCount;
  };
}

// Shared with the other pages that have a filter sidebar -- see
// components/FilterPanel.
const labelStyle = fieldLabelStyle;
const inputStyle = fieldStyle;

function formatStatLabel(stat: string): string {
  return stat
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

export default function NBAGameLog() {
  const [players, setPlayers] = useState<string[]>([]);
  const [teammates, setTeammates] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState('');
  const [selectedStat, setSelectedStat] = useState('pts');
  const [thresholdStr, setThresholdStr] = useState('');
  const [minMinutesStr, setMinMinutesStr] = useState('');
  const [withPlayer, setWithPlayer] = useState('');
  const [withoutPlayer, setWithoutPlayer] = useState('');
  const [b2b, setB2b] = useState(false);
  const [threeInFour, setThreeInFour] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [gameData, setGameData] = useState<GameData | null>(null);
  const isMobile = useIsMobile();
  const panelLayout = usePanelLayout();

  useEffect(() => {
    getNBAPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
  }, []);

  useEffect(() => {
    if (!selectedPlayer) {
      setTeammates([]);
      return;
    }
    getNBATeammates(selectedPlayer)
      .then((res) => setTeammates(res.data))
      .catch(() => setTeammates([]));
  }, [selectedPlayer]);

  const fetchStats = async () => {
    if (!selectedPlayer) return;
    setLoading(true);
    setError('');
    setGameData(null);
    try {
      const threshold = parseFloat(thresholdStr) || 0;
      const minMinutes = parseInt(minMinutesStr) || 0;
      const params: Record<string, any> = {
        player: selectedPlayer,
        stat: selectedStat,
        threshold,
        b2b,
        three_in_four: threeInFour,
      };
      if (minMinutes > 0) params.min_minutes = minMinutes;
      if (withPlayer) params.with_player = withPlayer;
      if (withoutPlayer) params.without_player = withoutPlayer;
      const res = await getNBAGameLog(params);
      setGameData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch game log.');
    } finally {
      setLoading(false);
    }
  };

  const recentGames = gameData ? [...gameData.games].slice(-10).reverse() : [];
  const threshold = parseFloat(thresholdStr) || 0;

  return (
    <div style={panelLayout}>
      <FilterPanel
        title="NBA Game Log"
        moreLabel="Min Minutes, Teammates, Streaks"
        action={{
          label: 'Get Stats',
          onClick: fetchStats,
          disabled: !selectedPlayer || loading,
        }}
        more={
          <>
            <label style={labelStyle}>Minimum Minutes Played</label>
            <input
              type="number"
              min={0}
              max={48}
              step={1}
              style={inputStyle}
              placeholder="e.g. 20"
              value={minMinutesStr}
              onFocus={(e) => e.target.select()}
              onChange={(e) => setMinMinutesStr(e.target.value)}
            />

            <label style={labelStyle}>With Player</label>
            <div style={{ marginBottom: 16 }}>
              <SearchDropdown
                players={teammates}
                value={withPlayer}
                onSelect={setWithPlayer}
                placeholder={selectedPlayer ? 'Search teammate...' : 'Select player first'}
                disabled={!selectedPlayer || teammates.length === 0}
                inputStyle={{ padding: 8 }}
              />
            </div>

            <label style={labelStyle}>Without Player</label>
            <div style={{ marginBottom: 16 }}>
              <SearchDropdown
                players={teammates}
                value={withoutPlayer}
                onSelect={setWithoutPlayer}
                placeholder={selectedPlayer ? 'Search teammate...' : 'Select player first'}
                disabled={!selectedPlayer || teammates.length === 0}
                inputStyle={{ padding: 8 }}
              />
            </div>

            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 13, cursor: 'pointer' }}>
                <input type="checkbox" checked={b2b} onChange={(e) => setB2b(e.target.checked)} />
                Back-to-Back Only
              </label>
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 13, cursor: 'pointer' }}>
                <input type="checkbox" checked={threeInFour} onChange={(e) => setThreeInFour(e.target.checked)} />
                3-in-4 Only
              </label>
            </div>
          </>
        }
      >
        <label style={labelStyle}>Player</label>
        <div style={{ marginBottom: 16 }}>
          <SearchDropdown
            players={players}
            value={selectedPlayer}
            onSelect={setSelectedPlayer}
            placeholder="Search by first or last name..."
            inputStyle={{ padding: 8 }}
          />
        </div>

        <label style={labelStyle}>Stat</label>
        <select style={inputStyle} value={selectedStat} onChange={(e) => setSelectedStat(e.target.value)}>
          {STAT_OPTIONS.map((s) => <option key={s} value={s}>{formatStatLabel(s)}</option>)}
        </select>

        <label style={labelStyle}>Threshold</label>
        <input
          type="number"
          min={0}
          max={100}
          step={1}
          style={inputStyle}
          placeholder="e.g. 20"
          value={thresholdStr}
          onFocus={(e) => e.target.select()}
          onChange={(e) => setThresholdStr(e.target.value)}
        />
      </FilterPanel>

      {/* Main Content */}
      <div style={{ flex: 1, padding: isMobile ? 16 : 24, overflowY: 'auto', background: theme.bgPage }}>
        {loading && <LoadingSpinner />}
        {error && (
          <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
            {error}
          </div>
        )}
        {!loading && !error && gameData && (
          <>
            <h2 style={{ marginTop: 0, color: theme.textPrimary }}>
              {selectedPlayer} — {formatStatLabel(selectedStat)} (Line: {threshold})
            </h2>
            <StatChart games={gameData.games} threshold={threshold} stat={selectedStat} />
            <OverCountsTable over_counts={gameData.over_counts} threshold={threshold} stat={selectedStat} />
            <h3 style={{ marginTop: 28, marginBottom: 12, color: theme.textPrimary }}>Recent Games (Last 10)</h3>

            {isMobile ? (
              <div>
                {recentGames.map((g, i) => (
                  <StatCard
                    key={i}
                    title={g.game_date}
                    titleAside={g.opponent}
                    value={g.stat_value}
                    valueColor={g.stat_value > threshold ? theme.dataBlue : theme.dataRed}
                    footer={formatStatLabel(selectedStat)}
                    meta={[
                      g.min != null ? `${g.min} MIN` : null,
                      g.fgm != null && g.fga != null ? `${g.fgm}-${g.fga} FG` : null,
                      g.fgm != null && g.fga != null && g.fga > 0
                        ? `${Math.round((g.fgm / g.fga) * 100)}% FG` : null,
                    ]}
                  />
                ))}
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Date</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Opponent</th>
                    <th style={{ padding: '10px 14px', textAlign: 'center' }}>MIN</th>
                    <th style={{ padding: '10px 14px', textAlign: 'center' }}>FGA</th>
                    <th style={{ padding: '10px 14px', textAlign: 'center' }}>FG</th>
                    <th style={{ padding: '10px 14px', textAlign: 'center' }}>FG%</th>
                    <th style={{ padding: '10px 14px', textAlign: 'center' }}>{formatStatLabel(selectedStat)}</th>
                  </tr>
                </thead>
                <tbody>
                  {recentGames.map((g, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgPage : theme.bgCard, color: theme.textPrimary }}>
                      <td style={{ padding: '8px 14px' }}>{g.game_date}</td>
                      <td style={{ padding: '8px 14px' }}>{g.opponent}</td>
                      <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                        {g.min ?? '—'}
                      </td>
                      <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                        {g.fga != null ? g.fga : '—'}
                      </td>
                      <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                        {g.fgm != null && g.fga != null ? `${g.fgm}-${g.fga}` : '—'}
                      </td>
                      <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textSecondary }}>
                        {g.fgm != null && g.fga != null && g.fga > 0
                          ? `${Math.round((g.fgm / g.fga) * 100)}%`
                          : '—'}
                      </td>
                      <td style={{
                        padding: '8px 14px',
                        textAlign: 'center',
                        fontWeight: 700,
                        color: g.stat_value > threshold ? theme.dataBlue : theme.dataRed,
                      }}>
                        {g.stat_value}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
        {!loading && !error && !gameData && (
          <div style={{ color: theme.textSecondary, marginTop: 60, textAlign: 'center', fontSize: 16, background: theme.bgPage, minHeight: '100%' }}>
            Select a player and click "Get Stats" to view game log.
          </div>
        )}
      </div>
    </div>
  );
}
