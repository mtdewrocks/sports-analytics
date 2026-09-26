import EVExplorer from '../../components/EVExplorer';
import BettingSportToggle from '../../components/BettingSportToggle';
import useBettingSport from '../../hooks/useBettingSport';
import { getMLBEV } from '../../api/mlb';
import { getNFLEV } from '../../api/nfl';

const FETCHERS = { mlb: getMLBEV, nfl: getNFLEV };

export default function BettingEVFinder() {
  const [sport, setSport, options] = useBettingSport();
  return (
    <EVExplorer
      // Keyed by sport so switching remounts and refetches -- the explorer
      // loads once on mount, same as the old per-sport pages did.
      key={sport}
      fetcher={FETCHERS[sport]}
      sport={sport}
      title="EV Finder"
      toolbar={<BettingSportToggle sport={sport} options={options} onChange={setSport} />}
    />
  );
}
