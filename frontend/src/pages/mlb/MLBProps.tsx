import PropsExplorer from '../../components/PropsExplorer';
import { getMLBProps, getMLBPitcherLineupContext } from '../../api/mlb';

/** The grid itself lives in PropsExplorer -- MLB and NFL produce the same
 *  long-format schema from get_props.py, so they share one implementation and
 *  differ only in which endpoint they call and what they are called. MLB also
 *  passes the opposing-lineup context, which groups pitcher props per
 *  pitcher/market and adds the "Opposing lineup" strip on phone cards. */
export default function MLBProps() {
  return (
    <PropsExplorer
      fetcher={getMLBProps}
      title="MLB Props"
      sport="mlb"
      pitcherContextFetcher={getMLBPitcherLineupContext}
    />
  );
}
