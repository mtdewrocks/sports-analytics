import MiddlesExplorer from '../../components/MiddlesExplorer';
import { getMLBMiddles } from '../../api/mlb';

export default function MLBMiddles() {
  return <MiddlesExplorer fetcher={getMLBMiddles} title="MLB Middles & Arbs" />;
}
