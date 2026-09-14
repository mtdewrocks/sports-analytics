import PropsExplorer from '../../components/PropsExplorer';
import { getMLBProps } from '../../api/mlb';

/** The grid itself lives in PropsExplorer -- MLB and NFL produce the same
 *  long-format schema from get_props.py, so they share one implementation and
 *  differ only in which endpoint they call. */
export default function MLBProps() {
  return <PropsExplorer fetcher={getMLBProps} />;
}
