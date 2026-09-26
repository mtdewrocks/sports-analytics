import client from './client';

// Cross-sport betting endpoints -- backend/app/routers/betting.py.

export interface BetDraft {
  sport: 'mlb' | 'nfl' | 'nba';
  player: string;
  market: string;
  line: number | null;
  side: 'over' | 'under';
  book: string;
  price: number;
  tool?: string;
  event_id?: string | null;
}

export interface Offer { book: string; price: number; link: string | null }

export interface Quote {
  ok: boolean;
  reason: 'started' | 'not_found' | 'no_price' | null;
  event_id?: string;
  commence_time?: string;
  home_team?: string;
  away_team?: string;
  source?: 'live' | 'scheduled';
  fetched_at?: string | null;
  at_book?: Offer | null;
  best?: Offer | null;
  offers?: Offer[];
}

export const getToday = () => client.get('/api/betting/today');
export const getQuote = (b: BetDraft) =>
  client.get<Quote>('/api/betting/quote', {
    params: {
      sport: b.sport, player: b.player, market: b.market, side: b.side,
      line: b.line ?? undefined, book: b.book, event_id: b.event_id ?? undefined,
    },
  });
export const logBet = (b: BetDraft & { stake?: number | null }) => client.post('/api/betting/bets', b);
export const getMyBets = () => client.get('/api/betting/bets');
export const setBetResult = (id: string, result: 'win' | 'loss' | 'push' | 'void') =>
  client.patch(`/api/betting/bets/${id}`, { result });
export const deleteBet = (id: string) => client.delete(`/api/betting/bets/${id}`);
export const getReportCard = () => client.get('/api/betting/report-card');
export const getBriefing = () => client.get('/api/betting/briefing');
