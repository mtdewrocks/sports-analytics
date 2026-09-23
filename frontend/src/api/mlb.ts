import client from './client';

export const getMLBPitchers = () => client.get('/api/mlb/pitchers');
export const getMLBMatchup = (pitcher: string) => client.get('/api/mlb/matchup', { params: { pitcher } });
export const getMLBPitcherProps = (pitcher: string) => client.get('/api/mlb/pitcher-props', { params: { pitcher } });
export const getMLBHotHitters = () => client.get('/api/mlb/hot-hitters');
export const getMLBProps = (params: Record<string, any>) => client.get('/api/mlb/props', { params });
export const getMLBBullpenTeams = () => client.get('/api/mlb/bullpen/teams');
export const getMLBBullpen = (team: string) => client.get('/api/mlb/bullpen', { params: { team } });
export const getMLBPitcherDailyReport = () => client.get('/api/mlb/pitcher-daily-report');
export const getMLBTodaysMatchups = () => client.get('/api/mlb/todays-matchups');
export const getMLBTeamMatchup = (teamA: string, teamB: string) =>
  client.get('/api/mlb/team-matchup', { params: { team_a: teamA, team_b: teamB } });

export const getMLBMiddles = (params: Record<string, any>) => client.get('/api/mlb/middles', { params });

export const getMLBGameLogPlayers = () => client.get('/api/mlb/game-log/players');
export const getMLBGameLog = (params: Record<string, any>) => client.get('/api/mlb/game-log', { params });

// Pitcher-side counterpart -- own props (Ks, earned runs, hits/walks
// allowed, outs, record-a-win) rather than a batter's, no opposing-hand
// filter (see get_mlb_pitcher_game_log()'s docstring for why).
export const getMLBPitcherGameLogPlayers = () => client.get('/api/mlb/pitcher-game-log/players');
export const getMLBPitcherGameLog = (params: Record<string, any>) => client.get('/api/mlb/pitcher-game-log', { params });

// Combined batter + pitcher list for the Game Log's single search box --
// lets the page infer Batter/Pitcher mode from who got picked instead of
// asking for a mode up front. See get_mlb_game_log_all_players()'s
// docstring in backend/app/data/mlb.py.
export const getMLBGameLogAllPlayers = () => client.get('/api/mlb/game-log/all-players');

// Static ballpark wind/elevation profiles -- see get_mlb_weather()'s
// docstring in backend/app/data/mlb.py for why this has no live per-game
// data the way the NFL version does.
export const getMLBWeather = () => client.get('/api/mlb/weather');

// Toughest/Best Matchups (hits), Platoon Edge Finder, and Strikeout
// Risk/Contact Matchups for today's slate -- see get_mlb_matchup_edge()'s
// docstring in backend/app/data/mlb.py.
export const getMLBMatchupEdge = () => client.get('/api/mlb/matchup-edge');
