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
export const getNBABeneficiary = (excludedPlayer: string, stat: string = 'min') =>
  client.get('/api/nba/in-out/beneficiary', { params: { excluded_player: excludedPlayer, stat } });
export const getNBAProps = (params: Record<string, any>) => client.get('/api/nba/props', { params });
export const getNBATeams = () => client.get('/api/nba/teams');
export const getNBATeamUsage = (team: string, metric: string = 'fga', scope: string = 'season') =>
  client.get('/api/nba/team-usage', { params: { team, metric, scope } });
export const getNBATeamMatchup = (teamA: string, teamB: string) =>
  client.get('/api/nba/team-matchup', { params: { team_a: teamA, team_b: teamB } });
export const getNBASeasons = () => client.get('/api/nba/seasons');
export const getNBASchedule = (date?: string) =>
  client.get('/api/nba/schedule', { params: date ? { date } : {} });
export const getNBAMiddles = (params: Record<string, any>) => client.get('/api/nba/middles', { params });
export const getNBAEV = (params: Record<string, any>) => client.get('/api/nba/ev', { params });
export const getNBAGapBets = (params: Record<string, any> = {}) => client.get('/api/nba/gap-bets', { params });
export const getNBAGapRecord = () => client.get('/api/nba/gap-bets/record');
export const getNBAInjuryImpact = (params: Record<string, any> = {}) => client.get('/api/nba/injury-impact', { params });
