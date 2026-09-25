import MiddlesExplorer from '../../components/MiddlesExplorer';
import BettingSportToggle from '../../components/BettingSportToggle';
import useBettingSport from '../../hooks/useBettingSport';
import { getMLBMiddles } from '../../api/mlb';
import { getNFLMiddles } from '../../api/nfl';

const FETCHERS = { mlb: getMLBMiddles, nfl: getNFLMiddles };

export default function BettingMiddles() {
  const [sport, setSport, options] = useBettingSport();
  return (
    <MiddlesExplorer
      // Keyed by sport so switching remounts and refetches -- the explorer
      // loads once on mount, same as the old per-sport pages did.
      key={sport}
      fetcher={FETCHERS[sport]}
      title="Middles & Arbs"
      toolbar={<BettingSportToggle sport={sport} options={options} onChange={setSport} />}
    />
  );
}
