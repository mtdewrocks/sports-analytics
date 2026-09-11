import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine,
  ResponsiveContainer, Cell, CartesianGrid,
} from 'recharts';
import { theme } from '../theme';

interface Game {
  game_date?: string; week?: number; stat_value: number; opponent?: string;
  result?: 'W' | 'L' | 'T' | null;
  tooltip?: Record<string, number | string | null>;
}
interface StatChartProps { games: Game[]; threshold: number; stat: string; }

function CustomTooltip({ active, payload, label, stat }: any) {
  if (!active || !payload || payload.length === 0) return null;
  const game: Game = payload[0].payload;
  const score = game.tooltip?.score;
  return (
    <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 4, padding: '8px 12px', fontSize: 12 }}>
      <div style={{ color: theme.textPrimary, fontWeight: 700, marginBottom: 4 }}>{label}{game.opponent ? ` vs ${game.opponent}` : ''}</div>
      <div style={{ color: theme.textPrimary }}>{stat.toUpperCase()}: {payload[0].value}</div>
      {score != null && (
        <div style={{ color: theme.textSecondary, marginTop: 2 }}>
          {game.result === 'W' ? 'Won' : game.result === 'L' ? 'Lost' : 'Tied'} {score}
        </div>
      )}
    </div>
  );
}

export default function StatChart({ games, threshold, stat }: StatChartProps) {
  return (
    <ResponsiveContainer width="100%" height={380}>
      <BarChart data={games} margin={{ top: 10, right: 20, left: 10, bottom: 60 }}>
        {/* Explicitly no gridlines */}
        <CartesianGrid strokeOpacity={0} />
        <XAxis
          dataKey="game_date"
          angle={-45}
          textAnchor="end"
          interval={0}
          tick={{ fontSize: 10, fill: theme.textSecondary }}
          axisLine={{ stroke: theme.border }}
          tickLine={false}
        />
        <YAxis
          axisLine={{ stroke: theme.border }}
          tickLine={false}
          tick={{ fontSize: 11, fill: theme.textSecondary }}
          width={36}
        />
        <Tooltip content={<CustomTooltip stat={stat} />} />
        <ReferenceLine
          y={threshold}
          stroke={theme.dataRed}
          strokeDasharray="5 5"
          label={{ value: `Line: ${threshold}`, fill: theme.dataRed, fontSize: 12, position: 'insideTopRight' }}
        />
        <Bar dataKey="stat_value" name={stat} radius={[3, 3, 0, 0]}>
          {games.map((g, i) => (
            <Cell key={i} fill={g.stat_value >= threshold ? theme.dataBlue : theme.dataRed} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
