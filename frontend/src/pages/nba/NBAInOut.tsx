import { useState, useEffect } from 'react';
import { getNBAPlayers, getNBATeammates, getNBAInOut, getNBABeneficiary, getNBASeasons } from '../../api/nba';
import { Link } from 'react-router-dom';
import LoadingSpinner from '../../components/LoadingSpinner';
import SearchDropdown from '../../components/SearchDropdown';
import { theme } from '../../theme';

interface InOutData {
  player: string;
  exclude: string[];
  games_with: number;
  games_without: number;
  with: Record<string, number | null>;
  without: Record<string, number | null>;
}

interface BeneficiaryRow {
  player: string;
  with: number;
  without: number;
  delta: number;
  games_with: number;
  games_without: number;
}
interface BeneficiaryData {
  excluded_player: string;
  stat: string;
  results: BeneficiaryRow[];
}

const DISPLAY_STATS: { key: string; label: string }[] = [
  { key: 'min',     label: 'MIN' },
  { key: 'pts',     label: 'PTS' },
  { key: 'reb',     label: 'REB' },
  { key: 'ast',     label: 'AST' },
  { key: 'pts_ast', label: 'PTS+AST' },
  { key: 'pts_reb', label: 'PTS+REB' },
  { key: 'pra',     label: 'PTS+REB+AST' },
];

function DiffCell({ value }: { value: number }) {
  const color = value > 0.5 ? theme.dataBlue : value < -0.5 ? theme.dataRed : theme.textPrimary;
  return (
    <td style={{ padding: '8px 14px', textAlign: 'center', fontWeight: 700, color }}>
      {value > 0 ? '+' : ''}{value.toFixed(1)}
    </td>
  );
}

export default function NBAInOut() {
  const [mode, setMode] = useState<'specific' | 'beneficiary'>('beneficiary');
  const [players, setPlayers] = useState<string[]>([]);
  const [teammates, setTeammates] = useState<string[]>([]);
  const [playerA, setPlayerA] = useState('');
  const [excluded, setExcluded] = useState<string[]>([]);
  const [tmFilter, setTmFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<InOutData | null>(null);

  // Beneficiary mode: just "who's out" + which stat, no anchor needed --
  // scans every teammate automatically instead of one at a time.
  const [outPlayer, setOutPlayer] = useState('');
  const [beneficiaryStat, setBeneficiaryStat] = useState('min');
  const [beneficiaryData, setBeneficiaryData] = useState<BeneficiaryData | null>(null);
  const [beneficiaryLoading, setBeneficiaryLoading] = useState(false);
  const [beneficiaryError, setBeneficiaryError] = useState('');
  const [seasonLabel, setSeasonLabel] = useState('');

  useEffect(() => {
    getNBASeasons()
      .then((res) => {
        const cur = res.data?.current;
        if (cur) setSeasonLabel(`${cur - 1}-${String(cur).slice(-2)}`);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!outPlayer) { setBeneficiaryData(null); return; }
    setBeneficiaryLoading(true);
    setBeneficiaryError('');
    getNBABeneficiary(outPlayer, beneficiaryStat)
      .then((res) => setBeneficiaryData(res.data))
      .catch((err) => setBeneficiaryError(err?.response?.data?.detail || 'Failed to fetch beneficiary data.'))
      .finally(() => setBeneficiaryLoading(false));
  }, [outPlayer, beneficiaryStat]);

  useEffect(() => {
    getNBAPlayers()
      .then((res) => setPlayers(res.data))
      .catch(() => setPlayers([]));
  }, []);

  useEffect(() => {
    if (!playerA) { setTeammates([]); setExcluded([]); setTmFilter(''); setData(null); return; }
    getNBATeammates(playerA)
      .then((res) => setTeammates(res.data))
      .catch(() => setTeammates([]));
    setExcluded([]);
    setTmFilter('');
    setData(null);
  }, [playerA]);

  const toggleExclude = (name: string) => {
    setExcluded((prev) =>
      prev.includes(name) ? prev.filter((p) => p !== name) : [...prev, name]
    );
  };

  const analyze = async () => {
    if (!playerA) return;
    setLoading(true);
    setError('');
    setData(null);
    try {
      const res = await getNBAInOut(playerA, excluded);
      setData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch in/out data.');
    } finally {
      setLoading(false);
    }
  };

  const excludeLabel = excluded.length > 0 ? excluded.join(' & ') : 'excluded players';

  const filteredTeammates = tmFilter
    ? teammates.filter((t) => t.toLowerCase().includes(tmFilter.toLowerCase()))
    : teammates;

  return (
    <div style={{ padding: 24, overflowY: 'auto', minHeight: 'calc(100vh - 60px)', background: theme.bgPage }}>
      <h2 style={{ marginTop: 0, marginBottom: 8, color: theme.textPrimary }}>NBA In/Out Analysis</h2>
      <p style={{ color: theme.textSecondary, fontSize: 13, marginBottom: 20, marginTop: 0 }}>
        See how a player being out shifts the rest of the roster's numbers.
      </p>
      <div style={{
        display: 'inline-block', fontSize: 12, color: theme.textPrimary, background: theme.bgCard,
        border: `1px solid ${theme.border}`, borderRadius: 4, padding: '4px 10px', marginBottom: 18,
      }}>
        {seasonLabel ? `${seasonLabel} season games only` : 'This season\'s games only'}
        <span style={{ color: theme.textSecondary }}>
          {' '}· early in the season the "without" side is often just a game or two, so check the game counts.
          For tonight's injury report, see <Link to="/nba/injury-impact" style={{ color: theme.dataBlue }}>Injury Impact</Link>.
        </span>
      </div>

      <div style={{ display: 'flex', gap: 4, background: theme.bgCard, borderRadius: 6, padding: 3, marginBottom: 24, width: 'fit-content' }}>
        <button
          onClick={() => setMode('beneficiary')}
          style={{
            padding: '7px 16px', fontSize: 13, fontWeight: 700, borderRadius: 4, border: 'none', cursor: 'pointer',
            background: mode === 'beneficiary' ? theme.bgCardHover : 'transparent',
            color: mode === 'beneficiary' ? theme.textPrimary : theme.textSecondary,
          }}
        >
          Who Benefits Most
        </button>
        <button
          onClick={() => setMode('specific')}
          style={{
            padding: '7px 16px', fontSize: 13, fontWeight: 700, borderRadius: 4, border: 'none', cursor: 'pointer',
            background: mode === 'specific' ? theme.bgCardHover : 'transparent',
            color: mode === 'specific' ? theme.textPrimary : theme.textSecondary,
          }}
        >
          Specific Matchup
        </button>
      </div>

      {mode === 'beneficiary' && (
        <>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 28 }}>
            <div>
              <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>
                Player Out
              </label>
              <SearchDropdown players={players} value={outPlayer} onSelect={setOutPlayer} placeholder="Search by first or last name..." />
            </div>
            <div>
              <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>
                Stat
              </label>
              <select
                value={beneficiaryStat}
                onChange={(e) => setBeneficiaryStat(e.target.value)}
                style={{ padding: '8px 12px', fontSize: 13, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bgCard, color: theme.textPrimary }}
              >
                {DISPLAY_STATS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </div>
          </div>

          {beneficiaryLoading && <LoadingSpinner />}
          {beneficiaryError && (
            <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
              {beneficiaryError}
            </div>
          )}

          {!beneficiaryLoading && beneficiaryData && (
            beneficiaryData.results.length === 0 ? (
              <div style={{ color: theme.textSecondary, fontSize: 14 }}>
                No games yet with {outPlayer} both in and out of the lineup this season.
              </div>
            ) : (
              <>
                <div style={{
                  background: 'rgba(107,168,240,0.12)', border: `1px solid ${theme.dataBlue}`, borderRadius: 8,
                  padding: '18px 22px', marginBottom: 20, maxWidth: 480,
                }}>
                  <div style={{ color: theme.textSecondary, fontSize: 11, textTransform: 'uppercase', marginBottom: 6 }}>Biggest Beneficiary</div>
                  <div style={{ color: theme.textPrimary, fontSize: 20, fontWeight: 700, marginBottom: 4 }}>
                    {beneficiaryData.results[0].player}
                  </div>
                  <div style={{ color: theme.dataBlue, fontSize: 15, fontWeight: 600 }}>
                    +{beneficiaryData.results[0].delta.toFixed(1)} {DISPLAY_STATS.find((s) => s.key === beneficiaryStat)?.label} when {outPlayer} is out
                  </div>
                  <div style={{ color: theme.textSecondary, fontSize: 12, marginTop: 4 }}>
                    {beneficiaryData.results[0].with.toFixed(1)} with &rarr; {beneficiaryData.results[0].without.toFixed(1)} without
                    {' '}({beneficiaryData.results[0].games_with} / {beneficiaryData.results[0].games_without} games)
                  </div>
                </div>

                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14, maxWidth: 640 }}>
                  <thead>
                    <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                      <th style={{ padding: '8px 14px', textAlign: 'left' }}>Player</th>
                      <th style={{ padding: '8px 14px', textAlign: 'center' }}>With</th>
                      <th style={{ padding: '8px 14px', textAlign: 'center' }}>Without</th>
                      <th style={{ padding: '8px 14px', textAlign: 'center' }}>Diff</th>
                      <th style={{ padding: '8px 14px', textAlign: 'center' }}>Games (with / without)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {beneficiaryData.results.map((r, i) => (
                      <tr key={r.player} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                        <td style={{ padding: '7px 14px', color: theme.textPrimary, fontWeight: i === 0 ? 700 : 400 }}>{r.player}</td>
                        <td style={{ padding: '7px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.with.toFixed(1)}</td>
                        <td style={{ padding: '7px 14px', textAlign: 'center', color: theme.textPrimary }}>{r.without.toFixed(1)}</td>
                        <DiffCell value={r.delta} />
                        <td style={{ padding: '7px 14px', textAlign: 'center', fontVariantNumeric: 'tabular-nums',
                          color: Math.min(r.games_with, r.games_without) < 3 ? theme.warningText : theme.textSecondary }}>
                          {r.games_with} / {r.games_without}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 10 }}>
                  Game counts in amber mean fewer than 3 games on one side -- a sample that thin can swing on one night, so treat it as a hint, not a trend.
                </div>
              </>
            )
          )}

          {!beneficiaryLoading && !beneficiaryError && !beneficiaryData && (
            <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 60 }}>
              Select a player to see who benefits most when they're out.
            </div>
          )}
        </>
      )}

      {mode === 'specific' && (
      <>
      <p style={{ color: theme.textSecondary, fontSize: 13, marginBottom: 24, marginTop: 0 }}>
        Compare an anchor player's stats when specific teammates are in vs. out of the lineup.
        "Without" shows games where <strong>all</strong> selected teammates were absent.
      </p>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start', marginBottom: 28 }}>

        {/* Anchor player */}
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>
            Anchor Player
          </label>
          <SearchDropdown
            players={players}
            value={playerA}
            onSelect={setPlayerA}
            placeholder="Search by first or last name..."
          />
        </div>

        {/* Teammate checkbox list — only shown once anchor player is selected */}
        {playerA && (
          <div style={{ minWidth: 220 }}>
            <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: theme.textPrimary }}>
              Exclude Teammates{excluded.length > 0 ? ` (${excluded.length} selected)` : ''}
            </label>
            <input
              type="text"
              placeholder="Filter teammates..."
              disabled={teammates.length === 0}
              value={tmFilter}
              onChange={(e) => setTmFilter(e.target.value)}
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '7px 10px', fontSize: 13,
                border: `1px solid ${theme.border}`, borderRadius: 4,
                marginBottom: 4,
                background: teammates.length === 0 ? theme.bgCardHover : theme.bgCard,
                color: theme.textPrimary,
              }}
            />
            <div style={{
              border: `1px solid ${theme.border}`, borderRadius: 4,
              maxHeight: 200, overflowY: 'auto',
              background: teammates.length === 0 ? theme.bgCardHover : theme.bgCard,
            }}>
              {teammates.length === 0 ? (
                <div style={{ padding: '8px 12px', color: theme.textSecondary, fontSize: 13 }}>No teammates found</div>
              ) : filteredTeammates.length === 0 ? (
                <div style={{ padding: '8px 12px', color: theme.textSecondary, fontSize: 13 }}>No matches</div>
              ) : (
                filteredTeammates.map((t) => (
                  <label
                    key={t}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '6px 12px', cursor: 'pointer', fontSize: 13,
                      background: excluded.includes(t) ? theme.bgCardHover : 'transparent',
                      borderBottom: `1px solid ${theme.border}`, color: theme.textPrimary,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={excluded.includes(t)}
                      onChange={() => toggleExclude(t)}
                      style={{ cursor: 'pointer' }}
                    />
                    {t}
                  </label>
                ))
              )}
            </div>
            {excluded.length > 0 && (
              <button
                onClick={() => setExcluded([])}
                style={{
                  marginTop: 4, fontSize: 12, color: theme.textSecondary, background: 'none',
                  border: 'none', cursor: 'pointer', padding: 0,
                }}
              >
                Clear all
              </button>
            )}
          </div>
        )}

        {playerA && (
        <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 2 }}>
          <button
            onClick={analyze}
            disabled={!playerA || excluded.length === 0 || loading}
            style={{
              padding: '9px 28px',
              background: theme.accent,
              color: 'white',
              border: 'none',
              borderRadius: 4,
              fontWeight: 700,
              fontSize: 14,
              cursor: playerA && excluded.length > 0 && !loading ? 'pointer' : 'not-allowed',
              opacity: playerA && excluded.length > 0 && !loading ? 1 : 0.6,
            }}
          >
            Analyze
          </button>
        </div>
        )}
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!loading && data && (
        <>
          <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <div style={{
              background: 'rgba(107,168,240,0.12)', border: `1px solid ${theme.dataBlue}`, borderRadius: 6,
              padding: '10px 20px', fontSize: 14,
            }}>
              <span style={{ fontWeight: 700, color: theme.dataBlue }}>With {excludeLabel}: </span>
              <span style={{ color: theme.textPrimary }}>{data.games_with} games</span>
            </div>
            <div style={{
              background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 6,
              padding: '10px 20px', fontSize: 14,
            }}>
              <span style={{ fontWeight: 700, color: theme.dataRed }}>Without {excludeLabel}: </span>
              <span style={{ color: theme.textPrimary }}>{data.games_without} games</span>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                  <th style={{ padding: '10px 14px', textAlign: 'left' }}>Stat</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>With</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>Without</th>
                  <th style={{ padding: '10px 14px', textAlign: 'center' }}>Diff</th>
                </tr>
              </thead>
              <tbody>
                {DISPLAY_STATS.map(({ key, label }, i) => {
                  const withVal = data.with?.[key] ?? null;
                  const withoutVal = data.without?.[key] ?? null;
                  if (withVal === null && withoutVal === null) return null;
                  const diff = (withoutVal ?? 0) - (withVal ?? 0);
                  return (
                    <tr key={key} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                      <td style={{ padding: '8px 14px', fontWeight: 700, color: theme.textPrimary }}>{label}</td>
                      <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>
                        {withVal !== null ? withVal.toFixed(1) : '—'}
                      </td>
                      <td style={{ padding: '8px 14px', textAlign: 'center', color: theme.textPrimary }}>
                        {withoutVal !== null ? withoutVal.toFixed(1) : '—'}
                      </td>
                      <DiffCell value={diff} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!loading && !error && !data && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 16, marginTop: 60 }}>
          Select an anchor player, check at least one teammate to exclude, then click "Analyze".
        </div>
      )}
      </>
      )}
    </div>
  );
}
