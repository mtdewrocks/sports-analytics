import { theme } from '../theme';
import StatCard from './StatCard';

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

/**
 * The game-log row as a card. Now a thin wrapper over StatCard -- the layout
 * that started here is used by ten other pages, so it lives there, and this
 * keeps only the game-log-specific bits: the W/L colouring and the
 * over/under-the-line colouring of the stat itself.
 */
export default function GameCard({
  week, gameDate, result, opponent, statLabel, statValue, threshold, extraStats, defRank,
}: GameCardProps) {
  const resultColor = result === 'W' ? theme.dataBlue : result === 'L' ? theme.dataRed : theme.textSecondary;

  const meta = [
    ...extraStats.map((s) => <>{s.value ?? '—'} {s.label}</>),
    ...(defRank ? [
      <span style={{ color: defRank.color, fontWeight: 600 }}>
        {defRank.label} {defRank.value}
        {defRank.isFallback && <span style={{ color: theme.textMuted, fontWeight: 400 }}> (prior yr)</span>}
      </span>,
    ] : []),
  ];

  return (
    <StatCard
      title={
        <>
          {week != null ? `Week ${week}` : (gameDate ?? '—')}{' '}
          <span style={{ color: resultColor, fontWeight: 700 }}>{result ?? '—'}</span>
          {opponent && <> vs {opponent}</>}
        </>
      }
      value={statValue}
      valueColor={statValue > threshold ? theme.dataBlue : theme.dataRed}
      meta={meta}
      footer={statLabel}
    />
  );
}
