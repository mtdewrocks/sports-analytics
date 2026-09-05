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

// FastAPI expects repeated params for List[str]: players=A&players=B --
// axios { params: { players: [...] } } sends players[]=A which FastAPI ignores.
export const getNFLFantasyMatchupCurrentWeek = (players: string[]) => {
  const qs = new URLSearchParams();
  players.forEach((p) => qs.append('players', p));
  return client.get(`/api/nfl/fantasy-matchup/current-week?${qs.toString()}`);
};
export const getNFLFantasyMatchupSeason = (players: string[]) => {
  const qs = new URLSearchParams();
  players.forEach((p) => qs.append('players', p));
  return client.get(`/api/nfl/fantasy-matchup/season?${qs.toString()}`);
};

export const getNFLTeammates = (player: string) => client.get('/api/nfl/teammates', { params: { player } });

export const getNFLInOut = (player: string, exclude: string[]) => {
  const qs = new URLSearchParams();
  qs.append('player', player);
  exclude.forEach((e) => qs.append('exclude', e));
  return client.get(`/api/nfl/in-out?${qs.toString()}`);
};
