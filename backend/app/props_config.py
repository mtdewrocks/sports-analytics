"""Per-sport settings for the props puller.

TWO MARKET TIERS, AND WHY
-------------------------
The alternate ladders (`*_alternate`) are where middles live -- the main market
is one line per book, so an Over and an Under on different numbers almost
always means one leg came off a ladder. But they are also half the markets,
and on NFL they are 26 of 60, which makes them half the bill.

They also move far more slowly than the main line. A book repricing Mahomes
over 249.5 does not necessarily redraw its whole 150-to-350 ladder.

So each tier gets its own refresh cadence: the core markets track the game,
the ladders get refreshed a few times per slate. Because the API charges
(unique markets RETURNED) x regions, asking for core+alt together in ONE call
costs exactly the same as two separate calls -- so when both are due they are
merged rather than issued twice.

BUDGET, AT ONE REGION
---------------------
    MLB  52,650/month  (13 fast markets x ~7 pulls/day, 13 slow x ~2)
    NFL  32,198/month  (24 fast x ~18 pulls/week, 18 slow x ~2)
    ---
         84,848 of 100,000 -- about 15% spare.

Both seasons overlap in Sept/Oct, so that margin is the real one. If you want
more slack, in order of least pain:

  1. Widen the MLB mid-tier from 3h to 4h (-6k). Costs little: a line eight
     hours from first pitch is not moving much.
  2. Drop the four MLB alternate ladders added for middles (-5k), accepting
     that middle discovery on home runs / RBIs / total bases goes with them.

Do NOT reach for a second region to "get more books" without recosting --
regions MULTIPLY, so "us,us2" takes this straight from 88k to 177k.

MARKET KEYS are checked against The Odds API's published market list. What is
deliberately LEFT OUT, so the gaps are choices rather than oversights:

  MLB   batter_triples, batter_fantasy_score(+_alternate) -- triples are too
        thin to price across books; fantasy score is DFS-only and does not
        share the Over/Under shape the Props page pivots on.
  NFL   player_defensive_interceptions -- the one market left out, and only
        because nothing has turned up there yet. If tackles are any guide,
        that reasoning is worth re-testing rather than trusted.
        player_tds_over and player_pass_rush_reception_tds -- near-duplicates
        of markets already covered.
        (pass_yds_q1, pats, solo_tackles and assists are kept, on the slow
        tier: wanted, but not worth game-day cadence.)

Only markets that RETURN data are charged, so a key that no book offers is
free -- but the fetch log names empty markets on every call, and pruning them
keeps requests short.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SportConfig:
    key: str                      # The Odds API sport key
    slug: str                     # short name, used in filenames and logs
    output: str
    core_markets: tuple      # fast tier: repriced through the day
    alt_markets: tuple       # slow tier: ladders, and anything rarely moved
    # (hours until start, minimum hours between refreshes). First match wins.
    core_tiers: tuple
    alt_tiers: tuple
    strip_prefixes: tuple = field(default=())

    @property
    def all_markets(self) -> tuple:
        return self.core_markets + self.alt_markets


MLB = SportConfig(
    key="baseball_mlb",
    slug="mlb",
    output="Daily_Props.parquet",
    core_markets=(
        "batter_hits", "batter_strikeouts",
        "batter_total_bases", "batter_hits_runs_rbis",
        # Added: the three most-bet MLB batter props were all missing from the
        # original list, which is a strange gap for a line-shopping page.
        "batter_home_runs", "batter_rbis", "batter_runs_scored",
        "pitcher_earned_runs", "pitcher_strikeouts", "pitcher_hits_allowed",
        "pitcher_walks", "pitcher_record_a_win", "pitcher_outs",
    ),
    alt_markets=(
        # The slow tier is "rarely repriced", not "alternate ladder only".
        # Singles, steals and first-home-run are thin, slow-moving markets --
        # paying core cadence for them was what pushed the bill to 95k.
        "batter_doubles", "batter_walks",
        "batter_singles", "batter_stolen_bases",
        "batter_first_home_run",          # Yes/No -- see to_over_under()
        "batter_hits_alternate", "batter_strikeouts_alternate",
        "batter_home_runs_alternate", "batter_rbis_alternate",
        "batter_total_bases_alternate", "batter_runs_scored_alternate",
        "pitcher_hits_allowed_alternate", "pitcher_strikeouts_alternate",
    ),
    # A baseball slate is visible for about a day, so the tiers are in hours.
    core_tiers=((3.0, 1.0), (8.0, 3.0), (float("inf"), 6.0)),
    alt_tiers=((3.0, 4.0), (float("inf"), 12.0)),
    strip_prefixes=("batter_",),
)

NFL = SportConfig(
    key="americanfootball_nfl",
    slug="nfl",
    output="NFL_Props.parquet",
    core_markets=(
        "player_pass_yds", "player_pass_tds", "player_pass_attempts",
        "player_pass_completions", "player_pass_interceptions",
        "player_pass_longest_completion",
        "player_rush_yds", "player_rush_attempts", "player_rush_longest",
        "player_receptions", "player_reception_yds", "player_reception_longest",
        "player_pass_rush_reception_yds",
        # Added: the TD markets and the two flex-yardage markets. Rush and
        # reception TDs price very differently from anytime-TD, and
        # rush+reception yards is the market RBs are actually bet in.
        "player_rush_tds", "player_reception_tds",
        "player_rush_reception_yds", "player_pass_rush_yds",
        "player_anytime_td", "player_1st_td", "player_last_td",   # Yes/No
        "player_tackles_assists", "player_sacks",
        "player_kicking_points", "player_field_goals",
    ),
    alt_markets=(
        "player_pass_yds_alternate", "player_pass_tds_alternate",
        "player_rush_yds_alternate", "player_rush_attempts_alternate",
        "player_reception_yds_alternate", "player_receptions_alternate",
        "player_pass_completions_alternate",
        "player_pass_rush_reception_yds_alternate",
        "player_rush_reception_yds_alternate",
        "player_rush_tds_alternate", "player_reception_tds_alternate",
        # Kept, on the slow tier. All four are thin and rarely repriced before
        # kickoff, so fast-tier cadence would be paying game-day prices for
        # numbers that sit still.
        "player_pass_yds_q1", "player_pats",
        "player_solo_tackles", "player_assists",
        # The tackle ladders, which is where middles actually turn up.
        #
        # I originally left these out reasoning that thin markets make poor
        # middle candidates. That is backwards. Liquidity decides whether you
        # can get size down; it does not decide whether a GAP EXISTS. Tackle
        # props are among the least-modelled numbers on the board, so books
        # disagree with each other far more than they do on passing yards --
        # and disagreement between books is precisely what a middle is.
        #
        # Being slow-moving helps twice over: a gap here does not evaporate in
        # minutes the way a main-line arb does, so the slow tier's cadence is
        # enough to catch it.
        "player_tackles_assists_alternate",
        "player_solo_tackles_alternate",
        "player_assists_alternate",
    ),
    # An NFL line is live for six days, so these run in days, not hours:
    # twice a day until three days out, four times a day inside that.
    #
    # Costed at ~26k/month, which with MLB's ~41k leaves a third of the 100k
    # quota spare -- no upgrade needed.
    #
    # NOT compressing near kickoff is a deliberate trade. Adding a
    # `(2.0, 0.5)` tier -- every 30 minutes inside two hours -- costs about
    # 4k/month more and is the ONLY thing that catches a short-lived arb,
    # since those live for minutes and a 6-hourly scan simply never sees one.
    # Worth adding if the middles screen becomes a headline feature; not worth
    # it while it is one page among several. (GitHub's scheduler can't reliably
    # fire every 30 minutes anyway -- that tier needs the Render-cron dispatch
    # to mean anything.)
    core_tiers=(
        (72.0, 6.0),           # inside 3 days -- 4x a day
        (float("inf"), 12.0),  # further out -- 2x a day
    ),
    alt_tiers=((6.0, 3.0), (48.0, 24.0), (float("inf"), 72.0)),
    strip_prefixes=("player_",),
)

SPORTS = {"mlb": MLB, "nfl": NFL}
