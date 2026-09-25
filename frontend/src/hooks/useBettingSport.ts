import { useSearchParams } from 'react-router-dom';
import { bettingSports } from '../siteMap';
import type { BettingSport } from '../siteMap';

/**
 * The sport a cross-sport Betting page is showing, kept in the URL
 * (?sport=nfl) so a link or a refresh lands on the same view. Defaults to
 * the first in-season sport.
 */
export default function useBettingSport(): [BettingSport, (s: BettingSport) => void, BettingSport[]] {
  const options = bettingSports();
  const [params, setParams] = useSearchParams();
  const raw = params.get('sport');
  const sport = (options as string[]).includes(raw ?? '') ? (raw as BettingSport) : options[0];
  const setSport = (s: BettingSport) => {
    const next = new URLSearchParams(params);
    next.set('sport', s);
    setParams(next, { replace: true });
  };
  return [sport, setSport, options];
}
