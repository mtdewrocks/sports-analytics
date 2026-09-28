import client from './client';

// Cross-sport betting endpoints -- backend/app/routers/betting.py.
// (Bet logging, live quotes and the Edge Board were removed; see
// docs/removed-features.md.)

export const getReportCard = () => client.get('/api/betting/report-card');
export const getBriefing = () => client.get('/api/betting/briefing');
