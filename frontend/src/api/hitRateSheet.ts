import client from './client';

// Both sports' hit-rate-sheet endpoints take the identical query shape
// (market/min_pct/min_odds/period/player/books) -- see
// backend/app/routers/mlb.py and backend/app/routers/nfl.py -- so one thin
// wrapper per sport is all this needs, same convention as getMLBProps()/
// getNFLProps() in the sibling api files.
export const getMLBHitRateSheet = (params: Record<string, any>) =>
  client.get('/api/mlb/hit-rate-sheet', { params });

export const getNFLHitRateSheet = (params: Record<string, any>) =>
  client.get('/api/nfl/hit-rate-sheet', { params });
