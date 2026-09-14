import PropsExplorer from '../../components/PropsExplorer';
import { getNFLProps } from '../../api/nfl';

export default function NFLProps() {
  return <PropsExplorer fetcher={getNFLProps} />;
}
