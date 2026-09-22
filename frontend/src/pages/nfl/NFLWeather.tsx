import React, { useState, useEffect } from 'react';
import { getNFLWeather } from '../../api/nfl';
import LoadingSpinner from '../../components/LoadingSpinner';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

interface WeatherGame {
  week: number;
  home_team: string;
  away_team: string;
  stadium: string | null;
  roof: string;
  wind: number;
  temp: number | null;
  total_line: number;
  total: number;
  diff: number;
}
interface WeatherSummary {
  wind_bucket_mph: number;
  high_wind_unders: number;
  high_wind_games: number;
  low_wind_unders: number;
  low_wind_games: number;
}
interface WeatherData {
  season: number;
  games: WeatherGame[];
  summary: WeatherSummary | null;
  featured_game: WeatherGame | null;
}

function StatTile({ n, l, color }: { n: React.ReactNode; l: string; color?: string }) {
  return (
    <div style={{
      background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8,
      padding: '12px 16px', flex: 1, minWidth: 160,
    }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: color ?? theme.textPrimary }}>{n}</div>
      <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 2 }}>{l}</div>
    </div>
  );
}

// One row of the diverging bar chart -- how far the actual combined score
// landed from the closing total, blue for over the line, red for under.
function DivBarRow({ g, maxAbs, isMobile }: { g: WeatherGame; maxAbs: number; isMobile: boolean }) {
  const isOver = g.diff >= 0;
  const pct = maxAbs > 0 ? Math.min((Math.abs(g.diff) / maxAbs) * 50, 50) : 0;
  const color = isOver ? theme.dataBlue : theme.dataRed;
  return (
    <div
      title={`Line ${g.total_line}, actual ${g.total}`}
      style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : '190px 1fr 64px',
        alignItems: 'center', gap: isMobile ? 4 : 10, padding: '6px 0', fontSize: 12.5,
      }}
    >
      <div style={{ color: theme.textSecondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        <b style={{ color: theme.textPrimary }}>{g.away_team} @ {g.home_team}</b> · W{g.week} · {g.wind} mph
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ position: 'relative', height: 16, background: theme.border, borderRadius: 2, flex: 1 }}>
          <div style={{ position: 'absolute', left: '50%', top: -3, bottom: -3, width: 1, background: theme.borderStrong }} />
          <div style={{
            position: 'absolute', top: 2, bottom: 2, borderRadius: 3, background: color,
            width: `${pct}%`, ...(isOver ? { left: '50%' } : { right: '50%' }),
          }} />
        </div>
        {isMobile && (
          <div style={{ textAlign: 'right', fontWeight: 700, fontSize: 12.5, color, minWidth: 50 }}>
            {isOver ? '+' : ''}{g.diff.toFixed(1)}
          </div>
        )}
      </div>
      {!isMobile && (
        <div style={{ textAlign: 'right', fontWeight: 700, fontSize: 12.5, color }}>
          {isOver ? '+' : ''}{g.diff.toFixed(1)}
        </div>
      )}
    </div>
  );
}

export default function NFLWeather() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [data, setData] = useState<WeatherData | null>(null);
  const isMobile = useIsMobile();

  useEffect(() => {
    getNFLWeather()
      .then((res) => setData(res.data))
      .catch(() => setError('Failed to load weather data.'))
      .finally(() => setLoading(false));
  }, []);

  const games = data?.games ?? [];
  const maxAbs = games.length > 0 ? Math.max(...games.map((g) => Math.abs(g.diff))) : 0;
  const fg = data?.featured_game;

  return (
    <div style={{ padding: isMobile ? 16 : 24, minHeight: 'calc(100vh - 60px)', background: theme.bgPage }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>Weather Impact</h2>
      <div style={{ fontSize: 14, color: theme.textSecondary, marginBottom: isMobile ? 20 : 28 }}>
        How wind and temperature have moved totals in this season's outdoor games, from real recorded post-game conditions.
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {!loading && !error && data && (
        <>
          {data.summary && (
            <>
              <h3 style={{ fontSize: 16, margin: '0 0 6px', color: theme.textPrimary }}>
                {data.season} Outdoor-Game Backtest
              </h3>
              <div style={{ fontSize: 13, color: theme.textMuted, marginBottom: 14, lineHeight: 1.5 }}>
                Every outdoor game played so far this season, real recorded wind/temp from the game itself — not a forecast. Small early-season sample; a directional read, not a model.
              </div>
              <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                <StatTile
                  n={`${data.summary.high_wind_unders} / ${data.summary.high_wind_games}`}
                  l={`Went under when wind ≥ ${data.summary.wind_bucket_mph} mph`}
                />
                <StatTile
                  n={`${data.summary.low_wind_unders} / ${data.summary.low_wind_games}`}
                  l={`Went under when wind < ${data.summary.wind_bucket_mph} mph`}
                />
              </div>
            </>
          )}

          {fg && (
            <div style={{
              marginBottom: 24, borderRadius: 8, border: `1px solid ${theme.border}`,
              background: theme.bgCard, padding: '16px 18px 18px',
            }}>
              <h4 style={{ fontSize: 14, margin: '0 0 10px', color: theme.textPrimary }}>
                This Season's Biggest Weather-Adjacent Miss — {fg.away_team} at {fg.home_team}, Week {fg.week}
              </h4>
              <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
                <StatTile n={fg.total_line} l="Closing total line" />
                <StatTile n={fg.total} l={`Actual combined points`} color={theme.dataRed} />
                <StatTile n={`${fg.diff >= 0 ? '+' : ''}${fg.diff.toFixed(1)}`} l="Total missed by" color={theme.dataRed} />
                <StatTile n={`${fg.wind} mph${fg.temp != null ? ` / ${fg.temp}°F` : ''}`} l={fg.stadium ?? 'Recorded conditions'} />
              </div>
              <div style={{
                borderLeft: `3px solid ${theme.warningText}`, background: 'rgba(232,163,61,0.06)',
                padding: '10px 14px', borderRadius: '0 6px 6px 0', fontSize: 12.5, color: theme.textSecondary, lineHeight: 1.6,
              }}>
                The schedule's own wind field is a single game-day reading, not a peak-gust figure, and there's no precipitation field yet — enough to flag "this game ran well under its total in real elevated wind," not enough on its own to say wind was the whole story. Highlighted automatically each week as the largest total miss among games with wind ≥ {data.summary?.wind_bucket_mph ?? 7} mph.
              </div>
            </div>
          )}

          {games.length > 0 && (
            <>
              <h3 style={{ fontSize: 16, margin: '28px 0 6px', color: theme.textPrimary }}>
                Every Outdoor Game, Sorted by Wind
              </h3>
              <div style={{ fontSize: 13, color: theme.textMuted, marginBottom: 14, lineHeight: 1.5 }}>
                Bar shows how far the actual combined score landed from the closing total line — blue means the game went over, red means under.
              </div>
              <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '14px 16px' }}>
                {games.map((g, i) => (
                  <div key={i} style={{ borderBottom: i < games.length - 1 ? `1px solid ${theme.border}` : 'none' }}>
                    <DivBarRow g={g} maxAbs={maxAbs} isMobile={isMobile} />
                  </div>
                ))}
              </div>
            </>
          )}

          {games.length === 0 && (
            <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 15, margin: '40px 0' }}>
              No outdoor games with recorded wind/temp data yet this season.
            </div>
          )}

          <h3 style={{ fontSize: 16, margin: '32px 0 6px', color: theme.textPrimary }}>This Week's Forecast</h3>
          <div style={{
            fontSize: 13, color: theme.textMuted, lineHeight: 1.7, background: theme.bgCard,
            border: `1px solid ${theme.border}`, borderRadius: 8, padding: '14px 16px',
          }}>
            No live forecast source is wired in yet, so this section can't show upcoming-game wind/precip risk the way the backtest above shows already-played games. <b style={{ color: theme.textSecondary }}>What it would take:</b> the National Weather Service API (api.weather.gov) is free, needs no API key, and resolves by exact stadium coordinates with roughly a 7-day horizon — it would need a one-time table of stadium lat/long and independent confirmation that it reports wind <i>gust</i> as its own field, since that's the number that actually matters for kicks and deep balls.
          </div>
        </>
      )}
    </div>
  );
}
