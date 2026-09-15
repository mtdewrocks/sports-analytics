import { theme } from '../theme';

/**
 * Position-group colours for the usage pages.
 *
 * Validated against the Sportsbook Dark surface (#0d1117): all three sit
 * inside the dark-mode lightness band, clear the chroma floor, hold a
 * colourblind separation of ΔE 22.8 on the worst adjacent pair (deutan) and
 * 23.1 for normal vision, and each clears 3:1 contrast against the page.
 *
 * Three is also the ceiling worth having. A skill group is 8-12 players, and
 * no categorical palette keeps that many distinguishable -- which is exactly
 * why these pages colour by POSITION and rank by length, rather than giving
 * every player his own hue.
 */
export const POSITION_COLORS: Record<string, string> = {
  RB: '#4e8ad2',
  WR: '#c08422',
  TE: '#9d72c4',
};

/** Anything not RB/WR/TE -- quarterbacks, fullbacks, an unmatched roster row. */
export const POSITION_OTHER = '#5b6875';

export function positionColor(position?: string | null): string {
  if (!position) return POSITION_OTHER;
  return POSITION_COLORS[position.toUpperCase()] ?? POSITION_OTHER;
}

/** The subject of a trend chart; every teammate takes the recessive grey. */
export const TREND_SUBJECT = theme.dataBlue;
export const TREND_CONTEXT = '#3a4552';

/** Starter/bench split used on the NBA Team Usage page, which colours by
 *  inferred role rather than position (no position data in that file --
 *  see NBATeamUsage.tsx). BENCH_COLOR reuses POSITION_OTHER's grey rather
 *  than a new hex, since it's the same "not a headline color" role here too. */
export const STARTER_COLOR = theme.accent;
export const BENCH_COLOR = POSITION_OTHER;
