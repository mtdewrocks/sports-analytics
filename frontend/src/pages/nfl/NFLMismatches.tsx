import { useState, useEffect } from 'react';
import { getNFLMismatchCategories, getNFLMismatches } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import StatCard from '../../components/StatCard';
import ChipRow from '../../components/ChipRow';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

interface Category {
  key: string;
  label: string;
}

interface MismatchGame {
  matchup: string;
  offense_team: string;
  defense_team: string;
  offense_rank: number;
  defense_rank: number;
  offense_value: number | null;
  defense_value: number | null;
  score: number;
}

interface MismatchData {
  category: string;
  label: string;
  offense_label: string;
  defense_label: string;
  week: number;
  games: MismatchGame[];
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

// Same absolute-tier convention used on the Matchup and Game Log pages:
// top 10 of 32 teams, bottom 10, middle 12.
function rankColor(rank: number): string {
  if (rank <= 10) return theme.dataBlue;
  if (rank >= 23) return theme.dataRed;
  return theme.textPrimary;
}

export default function NFLMismatches() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<MismatchData | null>(null);
  const isMobile = useIsMobile();

  useEffect(() => {
    getNFLMismatchCategories()
      .then((res) => {
        setCategories(res.data);
        if (res.data.length > 0) setSelectedCategory(res.data[0].key);
      })
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (!selectedCategory) return;
    setLoading(true);
    setError('');
    getNFLMismatches(selectedCategory)
      .then((res) => setData(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to fetch mismatches.'))
      .finally(() => setLoading(false));
  }, [selectedCategory]);

  return (
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 1100, margin: '0 auto', background: theme.bgPage, minHeight: 'calc(100vh - 60px)' }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>NFL Weekly Mismatches</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 20 }}>
        Every game on this week's slate, ranked by how lopsided the matchup is for the stat you pick.
      </div>

      {/* One row that scrolls sideways rather than three rows that wrap --
          this stays one row high however many categories get added later. */}
      <ChipRow
        chips={categories.map((c) => ({ key: c.key, label: c.label }))}
        value={selectedCategory}
        onChange={setSelectedCategory}
        scroll={isMobile}
        bleed={isMobile ? 16 : 0}
        style={{ marginBottom: 24 }}
      />

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {!loading && !error && data && data.error && (
        <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40 }}>{data.error}</div>
      )}

      {!loading && !error && data && !data.error && (
        <>
          <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 12 }}>Week {data.week}</div>

          {data.games.length === 0 ? (
            <div style={{ color: theme.textSecondary, textAlign: 'center', marginTop: 40 }}>
              No games with enough data for this category yet -- check back once more of the season has been played.
            </div>
          ) : isMobile ? (
            /* The score is what the list is sorted by, so it's the hero; the
               two rank cells collapse into one sentence line with colour doing
               the work the separate columns used to. The ordinal marker is
               real information here -- this list genuinely is ranked. */
            <div>
              {(() => {
                const maxScore = Math.max(...data.games.map((g) => Math.abs(g.score)), 1);
                return data.games.map((g, i) => (
                  <StatCard
                    key={i}
                    rank={i + 1}
                    title={<span style={{ fontWeight: 700 }}>{g.matchup}</span>}
                    value={g.score}
                    valueColor={i === 0 ? theme.dataBlue : theme.textPrimary}
                  >
                    {/* Both teams in a game appear on this list, once for each
                        side, so "TEAM rank vs TEAM rank" on one line left you
                        working out which half was the offense. Each side now
                        gets its own row, named. */}
                    <div style={{ marginTop: 7, display: 'flex', flexDirection: 'column', gap: 3 }}>
                      {([
                        { team: g.offense_team, label: data.offense_label, rank: g.offense_rank, value: g.offense_value },
                        { team: g.defense_team, label: data.defense_label, rank: g.defense_rank, value: g.defense_value },
                      ]).map((side) => (
                        <div key={side.label} style={{ display: 'flex', alignItems: 'baseline', gap: 6, fontSize: 12 }}>
                          <span style={{
                            color: theme.textPrimary, fontWeight: 700,
                            flex: '0 0 38px', width: 38,
                          }}>
                            {side.team}
                          </span>
                          <span style={{ color: theme.textSecondary, flex: 1, minWidth: 0 }}>{side.label}</span>
                          <span style={{
                            color: rankColor(side.rank), fontWeight: 700,
                            fontVariantNumeric: 'tabular-nums', flexShrink: 0,
                          }}>
                            {ordinal(side.rank)}
                          </span>
                          {side.value != null && (
                            <span style={{
                              color: theme.textMuted, fontVariantNumeric: 'tabular-nums',
                              flex: '0 0 52px', width: 52, textAlign: 'right',
                            }}>
                              {side.value}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                    <div style={{ height: 4, borderRadius: 2, background: theme.border, marginTop: 8, overflow: 'hidden' }}>
                      <div style={{
                        height: '100%', borderRadius: 2,
                        width: `${Math.round((Math.abs(g.score) / maxScore) * 100)}%`,
                        background: i === 0 ? theme.dataBlue : theme.textSecondary,
                      }} />
                    </div>
                  </StatCard>
                ));
              })()}
            </div>
          ) : (
            <div style={{ background: theme.bgCard, borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.4)', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Matchup</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>{data.offense_label}</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>{data.defense_label}</th>
                    <th style={{ padding: '10px 14px', textAlign: 'right' }}>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {data.games.map((g, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: i % 2 === 0 ? theme.bgCard : theme.bgPage }}>
                      <td style={{ padding: '9px 14px', color: theme.textSecondary, fontSize: 12 }}>{g.matchup}</td>
                      <td style={{ padding: '9px 14px' }}>
                        <span style={{ fontWeight: 700, color: theme.textPrimary }}>{g.offense_team}</span>{' '}
                        <span style={{ color: rankColor(g.offense_rank), fontWeight: 600 }}>
                          {ordinal(g.offense_rank)}
                        </span>
                        {g.offense_value != null && <span style={{ color: theme.textMuted }}> ({g.offense_value})</span>}
                      </td>
                      <td style={{ padding: '9px 14px' }}>
                        <span style={{ fontWeight: 700, color: theme.textPrimary }}>{g.defense_team}</span>{' '}
                        <span style={{ color: rankColor(g.defense_rank), fontWeight: 600 }}>
                          {ordinal(g.defense_rank)}
                        </span>
                        {g.defense_value != null && <span style={{ color: theme.textMuted }}> ({g.defense_value})</span>}
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', fontWeight: 700, color: theme.textPrimary }}>{g.score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 16, textAlign: 'center' }}>
            Ranks are out of 32 teams (1 = best). Early in the season these are based on a small number of
            games and can move quickly -- treat them as more reliable once a few weeks have been played.
          </div>
        </>
      )}
    </div>
  );
}
