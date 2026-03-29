import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine,
  ResponsiveContainer, Cell, CartesianGrid,
} from 'recharts';

interface Game { game_date?: string; week?: number; stat_value: number; opponent?: string; }
interface StatChartProps { games: Game[]; threshold: number; stat: string; }

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
          tick={{ fontSize: 10 }}
          axisLine={{ stroke: '#ddd' }}
          tickLine={false}
        />
        <YAxis
          axisLine={{ stroke: '#ddd' }}
          tickLine={false}
          tick={{ fontSize: 11 }}
          width={36}
        />
        <Tooltip formatter={(v) => [v ?? '', stat.toUpperCase()]} />
        <ReferenceLine
          y={threshold}
          stroke="#e74c3c"
          strokeDasharray="5 5"
          label={{ value: `Line: ${threshold}`, fill: '#e74c3c', fontSize: 12, position: 'insideTopRight' }}
        />
        <Bar dataKey="stat_value" name={stat} radius={[3, 3, 0, 0]}>
          {games.map((g, i) => (
            <Cell key={i} fill={g.stat_value > threshold ? '#2ecc71' : '#e74c3c'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
