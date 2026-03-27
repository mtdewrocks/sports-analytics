import client from './client';

export const getMLBPitchers = () => client.get('/api/mlb/pitchers');
export const getMLBMatchup = (pitcher: string) => client.get('/api/mlb/matchup', { params: { pitcher } });
export const getMLBHotHitters = () => client.get('/api/mlb/hot-hitters');
export const getMLBProps = (params: Record<string, any>) => client.get('/api/mlb/props', { params });
