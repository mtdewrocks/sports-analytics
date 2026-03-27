import client from './client';

export const getNFLPlayers = () => client.get('/api/nfl/players');
export const getNFLStats = () => client.get('/api/nfl/stats');
export const getNFLGameLog = (params: Record<string, any>) => client.get('/api/nfl/game-log', { params });
export const getNFLMatchups = () => client.get('/api/nfl/matchups');
export const getNFLMatchup = (matchup: string) => client.get('/api/nfl/matchup', { params: { matchup } });
