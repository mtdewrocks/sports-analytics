/**
 * Shared theme constants -- "Sportsbook Dark" (Direction A), the theme
 * approved for the site. Import from here rather than hardcoding hex
 * values, so future page conversions stay consistent and a future palette
 * tweak only has to happen in one place.
 *
 * This file covers CHROME/branding colors only (backgrounds, text, borders,
 * the brand accent). It does NOT cover data-visualization colors (the
 * blue/red tough-vs-favorable scale used on Matchup/Mismatches pages) --
 * those are a separate, colorblind-safe system that needs its own careful
 * per-page contrast tuning against a dark background, not a blanket swap.
 * DARK_DATA_BLUE / DARK_DATA_RED below are the two data colors already
 * verified (in the theme comparison mockup) to have enough contrast against
 * this theme's dark backgrounds -- lighter than the light-mode versions,
 * since the same hex reads as muddy on a near-black background.
 */

export const theme = {
  // Backgrounds
  bgPage: '#0d1117',
  bgCard: '#161b22',
  bgCardHover: '#1c2129',

  // Borders
  border: '#21262d',
  borderStrong: '#30363d',

  // Text
  textPrimary: '#e6e6e6',
  textSecondary: '#8b949e',
  textMuted: '#6e7681',

  // Brand accent -- teal-green, replacing the previous pink/red (#e94560)
  // as the site's primary accent, per the approved dark theme mockup.
  accent: '#1d9e75',
  accentHover: '#17805f',

  // Data-viz colors verified for dark backgrounds (see file header) --
  // NOT the same hex as the light-mode versions (#3d7fd1 / #d1483d).
  dataBlue: '#6ba8f0',
  dataRed: '#f4573f',

  // Warning/fallback banner text (e.g. "season hasn't started, showing
  // last year's data"). Verified via contrast check against bgCard: 8.02:1.
  warningText: '#e8a33d',
} as const;
