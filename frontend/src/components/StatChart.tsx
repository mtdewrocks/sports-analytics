import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Cell } from 'recharts';

interface Game { game_date?: string; week?: number; stat_value: number; opponent?: string; }
interface StatChartProps { games: Game[]; threshold: number; stat: string; }

export default function StatChart({ games, threshold, stat }: StatChartProps) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={games} margin={{ top: 10, right: 20, left: 0, bottom: 40 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="game_date" angle={-45} textAnchor="end" interval={0} tick={{ fontSize: 10 }} />
        <YAxis />
        <Tooltip formatter={(v: number) => [v, stat]} />
        <ReferenceLine y={threshold} stroke="red" strokeDasharray="5 5" label={{ value: `Line: ${threshold}`, fill: 'red', fontSize: 12 }} />
        <Bar dataKey="stat_value" name={stat}>
          {games.map((g, i) => (
            <Cell key={i} fill={g.stat_value > threshold ? '#2ecc71' : '#e74c3c'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
