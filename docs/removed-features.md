# Removed features: how they worked and how to rebuild them

Removed in September 2026 to cut memory use on the web server and the risk of
live-odds calls burning Odds API credits once real users arrive. Everything
below existed and worked. **The last commit that still has all of it is
`df14766`** ("Setting up beta database access and pushing weather items") on
`main`. The fastest rebuild is restoring the files from that commit:

```bash
git show df14766:backend/app/odds_live.py > backend/app/odds_live.py
# or restore several at once
git checkout df14766 -- backend/app/data/alt_value.py backend/app/data/today.py \
  backend/app/bets backend/app/odds_live.py backend/app/data/mlb_context.py \
  backend/tests/test_alt_value.py backend/tests/test_bets.py backend/tests/test_mlb_context.py frontend/src/components/BetSheet.tsx \
  frontend/src/components/AltLineExplorer.tsx frontend/src/pages/betting/MyBets.tsx \
  frontend/src/pages/betting/Today.tsx frontend/src/pages/betting/AltLineValue.tsx
```

Then re-add the routes, nav entries, API wrappers and Bet buttons listed under
each feature (those edits were in files that stayed, so they aren't restored
by the checkout above).

What was **kept**: the EV Finder, its report card (moved from My Bets to the
EV Finder page), the closing-line snapshots (`build_odds_snapshots.py`), the
flagged-plays log (`build_flagged_plays.py`), `market_core.closing_for` and
the `bets` database table (left in place, no longer written to).

---

## 1. My Bets, the "Bet this" sheet and live quotes

### What the user saw
- A **Bet** button on the Props page (per row, plus clickable odds cells on
  the desktop grid), the Hit Rate Sheet, the EV Finder, the Daily Briefing's
  game cards, the Edge Board and Alt-Line Value.
- Tapping it opened the **Bet this** bottom sheet:
  1. The price **up right now** at the chosen book, refreshed live, and the
     best price across books ("better price at X" hint).
  2. An **Over/Under switch** (Props and Hit Rate open on the Over).
  3. **"Choose a book"** chips for every book hanging that side/line.
  4. The book's **bet-slip deep link** when the book provides one, with the
     user's state filled in.
  5. Price and optional stake fields, then **Log bet**. Result: "Verified"
     (price matches what we saw) or "Self-reported".
- **My Bets** page (`/betting/my-bets`):
  - Tiles: Average CLV (with count graded), Beat the close %, ROI (units),
    Record (W-L-P). A note when CLV is positive but results are down
    ("likely short-term variance, not a bad process").
  - Bet list, newest first: player, side, line, market, book, price, stake,
    result badge, CLV, verified/self-reported. Buttons: **Mark win/loss/push/
    void** (only after the game started, if it couldn't auto-grade) and
    **Delete** (only before the game starts).
  - **EV Finder report card** table (see "Kept" above).

### Backend
- **`app/odds_live.py` — live quote.** `get_quote(sport, player, market,
  line, side, book, event_id, state)`:
  - Resolves the game from the props file (`resolve_event`); refuses once
    the game has started (`reason: "started"`).
  - Fetches that ONE market for that ONE event from The Odds API
    (`/v4/sports/{sport}/events/{event_id}/odds`, markets = the market and
    its `_alternate`, `includeLinks=true`, the 10 named books). **1 credit per
    call.**
  - Cached `CACHE_SECONDS = 180` per (event, market), shared by all users.
  - Stops calling live when the account has under `MIN_REMAINING = 5000`
    credits (read from the `x-requests-remaining` header) and falls back to
    the scheduled props file's price, saying so (`source: "scheduled"`).
  - Returns `at_book`, `best`, all `offers` (book, price, link), the event's
    teams and start time. Pick'em apps are excluded (`NO_SINGLE_BET_BOOKS`,
    `UNBETTABLE_BOOKS` in `props_config.py`).
- **Routes** (`app/routers/betting.py`, all behind `require_access`):
  - `GET /api/betting/quote` — the quote above.
  - `POST /api/betting/bets` — log a bet. Validates American odds (≥100 or
    ≤-100), re-quotes server-side, refuses started games (409) and unknown
    props (404), stamps the time server-side, sets `verification =
    "verified"` only if `price <= quoted price at that book`.
  - `GET /api/betting/bets` — the user's bets + summary; grades anything
    newly gradeable first (lazy grading, no scheduled job).
  - `PATCH /api/betting/bets/{id}` — manual result, only after start.
  - `DELETE /api/betting/bets/{id}` — only before start (no cleaning up a
    record after the fact).
  - `GET /api/betting/report-card` — kept (now used by the EV Finder page).
- **`app/models.py` `Bet`** — table `bets`: id, user_id, sport, event_id,
  player, market (props-file key), line (None for Yes/No), side, book, price,
  quoted_price, stake, tool (ev|alt|today|briefing|manual|props|hitrate),
  verification, commence_time, home_team, away_team, placed_at; after the
  game: close_price, close_fair_pct, clv_pct, result (pending|win|loss|push|
  void), result_source (auto|user), graded_at. Created by `create_all`.
- **`app/bets/grading.py`**:
  - **CLV**: `market_core.closing_for(bet, closing_lines)` → fair closing
    chance of the side (Pinnacle's two-way no-vig price at that line if it
    closed there, else the median of each book's de-vigged price; one-sided
    markets use the book's own close) and `clv_pct = decimal(price) ×
    fair_close − 1`. No close at exactly that line → CLV stays empty.
  - **Result**: 5 hours after start (`RESULT_DELAY_HOURS`), from the same game
    logs and market→stat maps as the Hit Rate Sheet (`MLB_MARKET_STAT_MAP`,
    `NFL_MARKET_STAT`); `settle(value, line, side)`; Yes/No treats 1+ as Yes.
    Doubleheaders / missing box scores stay pending for the user to mark.
  - **Summary**: bets, settled, record, units (per 1 unit staked), ROI %,
    average CLV, beat-close %, CLV count, verified share.
- **Tests**: `backend/tests/test_bets.py` (settle, closing_for, summary,
  Edge Board tiers). The closing_for, flagged-plays and line-move tests now
  live in `backend/tests/test_closing_lines.py`.
- **Config**: `ODDS_API_KEY` on the web service (Render) was only for live
  quotes; removed from `config.py` and `render.yaml`. The props workflow's
  GitHub secret of the same name is unrelated and still needed.

### Frontend
- `components/BetSheet.tsx` (keyed by the bet so each opens fresh — no
  setState in effects), `pages/betting/MyBets.tsx`, API in
  `api/betting.ts` (`getQuote`, `logBet`, `getMyBets`, `setBetResult`,
  `deleteBet`, `BetDraft`, `Quote`).
- Bet buttons lived in `PropsExplorer.tsx` (`draftFor`, clickable odds cells,
  Bet column), `HitRateSheet.tsx` (`betDraft`), `EVExplorer.tsx`,
  `DailyBriefing.tsx` (plays on game cards), `pages/betting/Today.tsx`.
- Nav: "My Bets" in the Betting group of `siteMap.ts`; route in `App.tsx`.

### Why it was removed / what to change if it comes back
- Every tap cost up to 2 credits (market + alternate) when not cached; with
  many users on different props that adds up fast. If rebuilt: **no live
  call on open** — show the scheduled price and its age, with a "Refresh
  price" button limited per user per day; or skip live prices entirely and
  just deep-link to the book.
- Consider a separate process or scheduled job for grading so the web
  server doesn't load game logs on page views (memory).

---

## 2. Edge Board (`/betting/edge-board`, formerly "Today")

### What it was
One ranked feed of the strongest signals across the site; each card linked
to its source page and bettable cards had a **Bet this** button. Filters:
All / NFL / MLB / NBA / Injuries / Edges / Long shots.

### Backend — `app/data/today.py`, `GET /api/betting/today`
Every item: `{id, type, sport, title, subtitle, notes[], badge, score, time,
link, bet, risk}`. Sections built independently (one failing drops only that
section), sorted by `score`:

| Type | Source | Rule | Score |
|---|---|---|---|
| injury | `data/injuries.get_injury_feed` (last 36h) | meaningful status changes, with volume beneficiaries | leads the page |
| ev | EV Finder (`data/ev.get_ev`) | top `EV_PER_SPORT = 6` per sport | `500 + min(ev, 12)×10`, −40 for long shots |
| alt | Alt-Line Value best rung per ladder | `ALT_PER_SPORT = 4` | `350 + min(ev, 12)×4` (+ matchup bonus) |
| middle | Middles & Arbs | `MIDDLES_PER_SPORT = 3` | `300 + one-side-wins %` |
| weather | weather forecasts | wind ≥ `WINDY_MPH = 12`, top `WEATHER_ITEMS = 4` | `200 + wind + rain/5` |
| hot | MLB hot hitters | top `HOT_HITTERS = 3` | `150 + wOBA×100` |

**Long-shot rules** (the part worth keeping if any of this returns):
- Price tiers: standard −250…+250; long shot +251…+600; anything else not shown.
- EV long shots need EV ≥ 6% and a fair price from Pinnacle or ≥ 3 books.
- Alt long shots need ≥ 20 games and BOTH season and last-10 hit rates above
  the implied chance by 5 points.
- At most 2 long shots per sport, labeled "LONG SHOT".
- **Suggested stake**: quarter-Kelly as % of bankroll, capped at 2%
  (0.5% for long shots). `stake_pct(p, price, kind)`.

### Frontend
`pages/betting/Today.tsx` (title "Edge Board"), `getToday` in
`api/betting.ts`; `/betting/today` redirected to `/betting/edge-board`.

### Why removed
It overlapped the Daily Briefing (injuries, weather, plays per game).
`tier`, `stake_pct`, `ev_longshot_ok` were also used by the briefing's
per-game plays; the briefing now keeps EV plays in the −250…+250 band plus
the EV long-shot rule inline (`briefing._play_ok`).

---

## 3. Alt-Line Value (`/betting/alt-lines`)

### What it was
For each player's alternate ladder (e.g. strikeouts 3.5 / 4.5 / 5.5 / 6.5),
the rung with the most value, from hit rates vs. the best price.

### Backend — `app/data/alt_value.py`
Built on the Hit Rate Sheet rows (`get_mlb_hit_rate_sheet`,
`get_nfl_hit_rate_sheet`), grouped into one ladder per (player, market).
Per rung:
1. **Best price**: highest Over price across real books (pick'em apps out).
2. **Hit rate**: season rate blended with the recent window
   (`RECENT_WEIGHT = 0.2`); sample size = season games only.
3. **Shrinkage** toward the market's median implied probability, prior worth
   `max(PRIOR_GAMES = 15, PRIOR_EXPECTED_HITS / p = 3/p)` games — so rare
   outcomes need far more evidence.
4. **EV** = p × payout − (1 − p).

Flagging: ≥ `MIN_GAMES` (MLB 10, NFL 4) games; never above
`MAX_FLAG_PRICE = +600`; EV > `SUSPICIOUS_EV = 50%` shown with "check
price", never picked; above `LONGSHOT_PRICE = +300` needs ≥ 10 games and
2× the EV bar (default 3%). Rungs shown from `MIN_SHOWN_PRICE = −400`.
Optional MLB matchup context per ladder (`app/data/mlb_context.py`, tests in
`backend/tests/test_mlb_context.py`:
opposing pitcher / lineup vs usual) with a favorable-only filter.

Routes: `GET /api/mlb/alt-value`, `GET /api/nfl/alt-value` (params: market,
player, min_ev, flagged_only, range, favorable). Tests:
`backend/tests/test_alt_value.py`.

### Frontend
`components/AltLineExplorer.tsx` (ladder cards, "our chance" explainer,
best rung highlighted), `pages/betting/AltLineValue.tsx`, fetchers
`getMLBAltValue` / `getNFLAltValue`, nav entry in `siteMap.ts`, route in
`App.tsx`. The Daily Briefing also added up to one Alt rung per game
(`briefing._alt_by_start`); removed with it.

### Why removed
In practice it mostly surfaced long shots.

---

## Things that did NOT go away
- **EV Finder** page and `data/ev.py` (still flags plays and still logs them
  for the report card).
- **Props page** alt lines shown inline with an "Alt line" tag.
- `build_odds_snapshots.py` / closing lines — the report card needs them.
