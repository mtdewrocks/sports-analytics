import PropsExplorer from '../../components/PropsExplorer';
import { getNBAProps } from '../../api/nba';

// Was a one-off search form over the old Basketball_Props.xlsx. NBA props now
// come from the same get_props.py pipeline as MLB and NFL, so the page is the
// same shared line-shopping grid.
export default function NBAProps() {
  return <PropsExplorer fetcher={getNBAProps} title="NBA Props" sport="nba" />;
}
