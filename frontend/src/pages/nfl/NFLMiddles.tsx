import MiddlesExplorer from '../../components/MiddlesExplorer';
import { getNFLMiddles } from '../../api/nfl';

export default function NFLMiddles() {
  return <MiddlesExplorer fetcher={getNFLMiddles} title="NFL Middles & Arbs" />;
}
