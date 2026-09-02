import client from './client';

export const getNFLPlayers = () => client.get('/api/nfl/players');
export const getNFLStats = () => client.get('/api/nfl/stats');
export const getNFLGameLog = (params: Record<string, any>) => client.get('/api/nfl/game-log', { params });
export const getNFLMatchups = () => client.get('/api/nfl/matchups');
export const getNFLMatchup = (matchup: string) => client.get('/api/nfl/matchup', { params: { matchup } });
export const getNFLGameScript = (matchup: string) => client.get('/api/nfl/game-script', { params: { matchup } });
export const getNFLMismatchCategories = () => client.get('/api/nfl/mismatches/categories');
export const getNFLMismatches = (category: string, week?: number) =>
  client.get('/api/nfl/mismatches', { params: week ? { category, week } : { category } });
