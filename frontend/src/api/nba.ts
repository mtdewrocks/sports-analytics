import client from './client';

export const getNBAPlayers = () => client.get('/api/nba/players');
export const getNBATeammates = (player: string) => client.get('/api/nba/teammates', { params: { player } });
export const getNBAGameLog = (params: Record<string, any>) => client.get('/api/nba/game-log', { params });
export const getNBAInOut = (player: string, exclude: string[]) => {
  // FastAPI expects repeated params for List[str]: exclude=X&exclude=Y
  // axios { params: { exclude: [...] } } sends exclude[]=X which FastAPI ignores
  const qs = new URLSearchParams();
  qs.append('player', player);
  exclude.forEach((e) => qs.append('exclude', e));
  return client.get(`/api/nba/in-out?${qs.toString()}`);
};
export const getNBAProps = (params: Record<string, any>) => client.get('/api/nba/props', { params });
