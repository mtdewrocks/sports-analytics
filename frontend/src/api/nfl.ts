import client from './client';

export const getNFLPlayers = () => client.get('/api/nfl/players');
export const getNFLStats = () => client.get('/api/nfl/stats');
// Game Log's own player list -- a different backend source than
// getNFLPlayers() above (which Fantasy Matchup and In/Out still use), so its
// season toggle only had to touch this page. Usage Trend has since gotten
// the same treatment -- see getNFLUsagePlayers() below.
export const getNFLGameLogPlayers = () => client.get('/api/nfl/game-log/players');
export const getNFLGameLog = (params: Record<string, any>) => client.get('/api/nfl/game-log', { params });
// "Position vs. Defense" -- how other players at the selected player's own
// position have fared against their next opponent this season. position
// must be RB/WR/TE/QB (the backend 422s on anything else); exclude_player
// drops the selected player themselves out of the results, for the rare
// divisional-rematch case where they'd otherwise show up against their own
// upcoming opponent from an earlier meeting this season.
export const getNFLPositionVsDefense = (opponent: string, position: string, excludePlayer?: string) =>
  client.get('/api/nfl/position-vs-defense', {
    params: excludePlayer ? { opponent, position, exclude_player: excludePlayer } : { opponent, position },
  });
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

// Was '/api/nfl/teams', which the router never defines (the endpoint is
// "/usage/teams") -- every call 404'd, NFLTeamUsage.tsx swallowed the error
// via .catch(() => setTeams([])), and the team dropdown just stayed empty
// with no visible error. Not a cache issue; the request never had anywhere
// to land.
export const getNFLUsageTeams = () => client.get('/api/nfl/usage/teams');
export const getNFLTeamUsage = (team: string, week?: number) =>
  client.get('/api/nfl/usage', { params: week != null ? { team, week } : { team } });
// Usage Trend's OWN player list -- deliberately not getNFLPlayers() (see the
// comment on that export above). get_player_usage_trend() looks the player
// up inside player_week_usage.parquet, whose names are abbreviated
// ("T.McBride"); getNFLPlayers() lists the legacy Player_Stats_Weekly file's
// full names ("Trey McBride"). No amount of normalizing punctuation/case
// makes those two strings equal, so every trend lookup came back empty no
// matter who was picked. Same fix Game Log already got via
// getNFLGameLogPlayers() for the identical reason.
export const getNFLUsagePlayers = () => client.get('/api/nfl/usage/players');
export const getNFLUsageTrend = (player: string, stat: string) =>
  client.get('/api/nfl/usage/trend', { params: { player, stat } });

export const getNFLProps = (params: Record<string, any>) => client.get('/api/nfl/props', { params });
export const getNFLMiddles = (params: Record<string, any>) => client.get('/api/nfl/middles', { params });

// Wind/temp backtest for this season's outdoor games -- real recorded
// post-game conditions only, no live forecast (see get_nfl_weather()'s
// docstring in backend/app/data/nfl.py).
export const getNFLWeather = () => client.get('/api/nfl/weather');

// EV Finder and Alt-Line Value -- see backend/app/data/ev.py and alt_value.py.
export const getNFLEV = (params: Record<string, any>) => client.get('/api/nfl/ev', { params });
export const getNFLAltValue = (params: Record<string, any>) => client.get('/api/nfl/alt-value', { params });
