import AltLineExplorer from '../../components/AltLineExplorer';
import BettingSportToggle from '../../components/BettingSportToggle';
import useBettingSport from '../../hooks/useBettingSport';
import { getMLBAltValue } from '../../api/mlb';
import { getNFLAltValue } from '../../api/nfl';

const FETCHERS = { mlb: getMLBAltValue, nfl: getNFLAltValue };

export default function BettingAltLineValue() {
  const [sport, setSport, options] = useBettingSport();
  return (
    <AltLineExplorer
      // Keyed by sport so switching remounts and refetches -- the explorer
      // loads once on mount, same as the old per-sport pages did.
      key={sport}
      fetcher={FETCHERS[sport]}
      title="Alt-Line Value"
      toolbar={<BettingSportToggle sport={sport} options={options} onChange={setSport} />}
    />
  );
}
