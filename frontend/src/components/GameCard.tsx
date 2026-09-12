import { theme } from '../theme';

interface GameCardProps {
  week?: number;
  gameDate?: string;
  result?: 'W' | 'L' | 'T' | null;
  opponent?: string;
  statLabel: string;
  statValue: number;
  threshold: number;
  extraStats: { label: string; value: number | string | null }[];
  defRank?: { label: string; value: string; color: string; isFallback?: boolean } | null;
}

export default function GameCard({
  week, gameDate, result, opponent, statLabel, statValue, threshold, extraStats, defRank,
}: GameCardProps) {
  const resultColor = result === 'W' ? theme.dataBlue : result === 'L' ? theme.dataRed : theme.textSecondary;
  const statColor = statValue > threshold ? theme.dataBlue : theme.dataRed;

  return (
    <div style={{ background: theme.bgCard, borderRadius: 8, padding: '12px 14px', marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <div style={{ fontSize: 13, color: theme.textPrimary }}>
          {week != null ? `Week ${week}` : (gameDate ?? '—')}{' '}
          <span style={{ color: resultColor, fontWeight: 700 }}>{result ?? '—'}</span>
          {opponent && <> vs {opponent}</>}
        </div>
        <div style={{ fontSize: 20, fontWeight: 700, color: statColor }}>{statValue}</div>
      </div>
      {(extraStats.length > 0 || defRank) && (
        <div style={{ fontSize: 12, color: theme.textSecondary }}>
          {extraStats.map((s, i) => (
            <span key={s.label}>
              {i > 0 && ' · '}
              {s.value ?? '—'} {s.label}
            </span>
          ))}
          {defRank && (
            <>
              {extraStats.length > 0 && ' · '}
              <span style={{ color: defRank.color, fontWeight: 600 }}>
                {defRank.label} {defRank.value}
              </span>
              {defRank.isFallback && <span style={{ color: theme.textMuted }}> (prior yr)</span>}
            </>
          )}
        </div>
      )}
      <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 2 }}>{statLabel}</div>
    </div>
  );
}
