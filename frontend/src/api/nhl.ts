import client from './client';

// NHL endpoints -- backend/app/routers/nhl.py.
export const getNHLPlayers = () => client.get('/api/nhl/players');
export const getNHLSlate = (date?: string) => client.get('/api/nhl/slate', { params: date ? { date } : {} });
export const getNHLGameLog = (params: Record<string, any>) => client.get('/api/nhl/game-log', { params });
export const getNHLMatchup = (gameId: number) => client.get('/api/nhl/matchup', { params: { game_id: gameId } });
export const getNHLGoalieReport = (date?: string) =>
  client.get('/api/nhl/goalie-report', { params: date ? { date } : {} });
export const getNHLScheduleSpots = (date?: string) =>
  client.get('/api/nhl/schedule-spots', { params: date ? { date } : {} });
export const getNHLLines = (gameId: number, mode: 'last' | 'common' = 'last') =>
  client.get('/api/nhl/lines', { params: { game_id: gameId, mode } });
export const getNHLDeepDive = (gameId: number, attacking: 'away' | 'home', strength: '5v5' | 'pp' | 'all') =>
  client.get('/api/nhl/deep-dive', { params: { game_id: gameId, attacking, strength } });
