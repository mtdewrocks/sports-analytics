import SegmentedToggle from './SegmentedToggle';
import type { BettingSport } from '../siteMap';

const LABEL: Record<BettingSport, string> = { mlb: 'MLB', nfl: 'NFL' };

/** Sport switch at the top of every cross-sport Betting page. */
export default function BettingSportToggle({
  sport, options, onChange,
}: { sport: BettingSport; options: BettingSport[]; onChange: (s: BettingSport) => void }) {
  return (
    <SegmentedToggle
      value={sport}
      onChange={onChange}
      options={options.map((s) => ({ value: s, label: LABEL[s] }))}
      style={{ marginBottom: 12, width: 'fit-content' }}
    />
  );
}
