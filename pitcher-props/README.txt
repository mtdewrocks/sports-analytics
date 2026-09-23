Pitcher Props card for the MLB Pitcher Matchup page.

Option A: copy the files in backend/ and frontend/ over the same paths in the repo.
Option B: from the repo root, run: git am 0001-MLB-Matchup-add-Pitcher-Props-card-best-line-price-p.patch

Changed files:
  backend/app/data/props.py                 - get_pitcher_props(): best line and price for each pitcher market
  backend/app/routers/mlb.py                - GET /api/mlb/pitcher-props?pitcher=
  frontend/src/api/mlb.ts                   - getMLBPitcherProps()
  frontend/src/components/PropsExplorer.tsx - makes formatOdds and prettyBook available to other files
  frontend/src/pages/mlb/MLBMatchup.tsx     - PitcherPropsCard and a shorter Matchup Summary
