import client from './client';

export const getNBAPlayers = () => client.get('/api/nba/players');
export const getNBATeammates = (player: string) => client.get('/api/nba/teammates', { params: { player } });
export const getNBAGameLog = (params: Record<string, any>) => client.get('/api/nba/game-log', { params });
export const getNBAInOut = (player: string, exclude: string[]) =>
  client.get('/api/nba/in-out', { params: { player, exclude } });
export const getNBAProps = (params: Record<string, any>) => client.get('/api/nba/props', { params });
