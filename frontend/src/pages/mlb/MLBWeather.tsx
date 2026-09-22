import { useState, useEffect } from 'react';
import { getMLBWeather } from '../../api/mlb';
import LoadingSpinner from '../../components/LoadingSpinner';
import useIsMobile from '../../hooks/useIsMobile';
import { theme } from '../../theme';

interface Ballpark {
  park: string;
  team: string;
  effect: string;
}

export default function MLBWeather() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [ballparks, setBallparks] = useState<Ballpark[]>([]);
  const isMobile = useIsMobile();

  useEffect(() => {
    getMLBWeather()
      .then((res) => setBallparks(res.data.ballparks ?? []))
      .catch(() => setError('Failed to load weather data.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: isMobile ? 16 : 24, minHeight: 'calc(100vh - 60px)', background: theme.bgPage }}>
      <h2 style={{ marginTop: 0, marginBottom: 6, color: theme.textPrimary }}>Weather Impact</h2>
      <div style={{ fontSize: 14, color: theme.textSecondary, marginBottom: isMobile ? 20 : 28 }}>
        How ballpark wind and elevation shape scoring and home runs — known park tendencies, not a live per-game forecast.
      </div>

      {loading && <LoadingSpinner />}
      {error && (
        <div style={{ background: 'rgba(244,87,63,0.12)', border: `1px solid ${theme.dataRed}`, borderRadius: 4, padding: 16, color: theme.dataRed }}>
          {error}
        </div>
      )}

      {!loading && !error && (
        <>
          <h3 style={{ fontSize: 16, margin: '0 0 6px', color: theme.textPrimary }}>Ballpark Wind &amp; Elevation Profiles</h3>
          <div style={{ fontSize: 13, color: theme.textMuted, marginBottom: 14, lineHeight: 1.5 }}>
            No live per-game wind feed exists for MLB in the data pipeline yet, so this is well-documented, season-independent park knowledge — it doesn't know which way the wind is blowing at any specific ballpark today.
          </div>

          {ballparks.length > 0 ? (
            <div style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 12, marginBottom: 8,
            }}>
              {ballparks.map((bp) => (
                <div key={bp.park} style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '14px 16px' }}>
                  <div style={{ fontWeight: 700, color: theme.textPrimary, marginBottom: 4 }}>
                    {bp.park} <span style={{ fontWeight: 400, fontSize: 12, color: theme.textSecondary }}>{bp.team}</span>
                  </div>
                  <div style={{ fontSize: 12.5, color: theme.textSecondary, lineHeight: 1.5 }}>{bp.effect}</div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: theme.textSecondary, textAlign: 'center', fontSize: 15, margin: '40px 0' }}>
              No ballpark profile data available.
            </div>
          )}

          <h3 style={{ fontSize: 16, margin: '32px 0 6px', color: theme.textPrimary }}>Where Live Data Would Come From</h3>
          <div style={{
            fontSize: 13, color: theme.textMuted, lineHeight: 1.7, background: theme.bgCard,
            border: `1px solid ${theme.border}`, borderRadius: 8, padding: '14px 16px',
          }}>
            Phase 2 for MLB: add a live per-game wind-speed/direction feed, keyed to game time at each home ballpark — the same National Weather Service source (api.weather.gov, free, no API key, resolves by exact stadium coordinates) that a live NFL forecast would use. That would turn this page from "known park tendencies" into "today's actual wind at this specific ballpark," the same way the <a href="/nfl/weather" style={{ color: theme.accent }}>NFL Weather page</a>'s backtest already uses the NFL schedule's real recorded wind/temp fields — MLB's schedule data has no equivalent fields at all right now.
          </div>
        </>
      )}
    </div>
  );
}
