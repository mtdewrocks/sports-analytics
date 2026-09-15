import client from './client';

export const getNFLPlayers = () => client.get('/api/nfl/players');
export const getNFLStats = () => client.get('/api/nfl/stats');
// Game Log's own player list -- a different backend source than
// getNFLPlayers() above (which Fantasy Matchup, In/Out, and the usage
// trend page still use), so its season toggle only had to touch this page.
export const getNFLGameLogPlayers = () => client.get('/api/nfl/game-log/players');
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

// `position` was dropped from the screener -- the stat filters already imply
// the position (nobody with 1000 rushing yards is a cornerback), so it only
// ever added a control that could silently exclude a matching player. The
// backend parameter is optional and stays in place, simply never sent.
export const getNFLSeasonScreener = (season: number, filters: string[]) => {
  const qs = new URLSearchParams();
  qs.append('season', String(season));
  filters.forEach((f) => qs.append('filters', f));
  return client.get(`/api/nfl/season-screener?${qs.toString()}`);
};

export const getNFLUsageTeams = () => client.get('/api/nfl/teams');
export const getNFLTeamUsage = (team: string, week?: number) =>
  client.get('/api/nfl/usage', { params: week != null ? { team, week } : { team } });
export const getNFLUsageTrend = (player: string, stat: string) =>
  client.get('/api/nfl/usage/trend', { params: { player, stat } });

export const getNFLProps = (params: Record<string, any>) => client.get('/api/nfl/props', { params });
export const getNFLMiddles = (params: Record<string, any>) => client.get('/api/nfl/middles', { params });
