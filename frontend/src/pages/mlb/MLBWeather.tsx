import { useState, useEffect } from 'react';
import { getMLBWeather } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

interface WindEffect {
  favors: 'hitters' | 'pitchers' | 'lhb' | 'rhb' | 'neutral';
  label: string;
}

interface WeatherGame {
  home_team: string;
  away_team: string;
  stadium: string;
  roof: 'outdoor' | 'retractable' | 'dome';
  game_time_utc: string;
  temp_f: number | null;
  wind_mph: number | null;
  wind_gust_mph: number | null;
  wind_dir: string | null;
  precip_pct: number | null;
  note: string | null;
  wind_effect: WindEffect | null;
}

// Same blue/red tough-vs-favorable scale as the Matchup pages: blue reads as
// good for hitters, red as tough for hitters (favors pitchers). A crosswind
// call (lhb/rhb) still favors somebody's fly balls over a calm day, so it
// gets blue too -- it just isn't evenly split between both sides the way a
// straight-out wind is.
function windEffectColor(favors: WindEffect['favors']): string {
  if (favors === 'pitchers') return theme.dataRed;
  if (favors === 'neutral') return theme.textSecondary;
  return theme.dataBlue;
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      weekday: 'short', hour: 'numeric', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function windColor(mph: number | null): string {
  if (mph == null) return theme.textSecondary;
  if (mph >= 15) return theme.dataRed;
  if (mph >= 10) return theme.warningText;
  return theme.textPrimary;
}

export default function MLBWeather() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [games, setGames] = useState<WeatherGame[]>([]);
  const isMobile = useIsMobile();

  useEffect(() => {
    getMLBWeather()
      .then((res) => setGames(res.data.games ?? []))
      .catch(() => setError('Failed to load weather forecast.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: isMobile ? 16 : 24, maxWidth: 1000, margin: '0 auto', minHeight: 'calc(100vh - 60px)', background: theme.bgPage }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>Weather</h2>
      <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: isMobile ? 20 : 28 }}>
        Live forecast for today's not-yet-started games -- wind, temperature and rain chance at each
        ballpark, refreshed every couple of hours as game time approaches. Not a forecast for games
        that have already started or finished.
        <div style={{ marginTop: 6 }}>
          Wind effect (out/in/favors a side) assumes a park facing the standard east-northeast MLB
          orientation, since real per-park layouts aren't published anywhere we could verify --
          treat it as a reasonable approximation, not an exact reading for every park.
        </div>
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {!loading && !error && (
        games.length === 0 ? (
          <div style={{ color: theme.textSecondary, textAlign: 'center', margin: '40px 0' }}>
            No upcoming games on today's slate right now -- check back once the day's schedule is set,
            or once earlier games have started (a game already underway no longer shows here).
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {games.map((g, i) => (
              <div key={i} style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '14px 16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
                  <div style={{ fontWeight: 700, color: theme.textPrimary }}>
                    {g.away_team} @ {g.home_team}
                  </div>
                  <div style={{ fontSize: 12, color: theme.textMuted }}>
                    {fmtTime(g.game_time_utc)} · {g.stadium}
                  </div>
                </div>

                {g.roof === 'dome' ? (
                  <div style={{ marginTop: 8, fontSize: 13, color: theme.textMuted }}>
                    Indoors -- no weather impact.
                  </div>
                ) : (
                  <div style={{ marginTop: 10, display: 'flex', gap: 20, flexWrap: 'wrap' }}>
                    <div>
                      <div style={{ fontSize: 11, color: theme.textMuted }}>Temp</div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: theme.textPrimary }}>
                        {g.temp_f != null ? `${g.temp_f}°F` : '--'}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: theme.textMuted }}>Wind</div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: windColor(g.wind_mph) }}>
                        {g.wind_mph != null ? `${g.wind_mph} mph ${g.wind_dir ?? ''}` : '--'}
                      </div>
                      {g.wind_gust_mph != null && g.wind_gust_mph > (g.wind_mph ?? 0) + 5 && (
                        <div style={{ fontSize: 11, color: theme.textMuted }}>gusts to {g.wind_gust_mph}</div>
                      )}
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: theme.textMuted }}>Rain chance</div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: theme.textPrimary }}>
                        {g.precip_pct != null ? `${g.precip_pct}%` : '--'}
                      </div>
                    </div>
                    {g.roof === 'retractable' && (
                      <div style={{ fontSize: 11, color: theme.textMuted, alignSelf: 'center' }}>
                        Retractable roof -- may end up played closed
                      </div>
                    )}
                  </div>
                )}

                {g.wind_effect && (
                  <div style={{ marginTop: 10, fontSize: 13, fontWeight: 600, color: windEffectColor(g.wind_effect.favors) }}>
                    {g.wind_effect.label}
                  </div>
                )}

                {g.note && (
                  <div style={{ marginTop: 10, fontSize: 12, color: theme.textSecondary, lineHeight: 1.5, borderTop: `1px solid ${theme.border}`, paddingTop: 8 }}>
                    {g.note}
                  </div>
                )}
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
