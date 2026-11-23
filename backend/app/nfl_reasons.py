"""Plain-English reasons behind an NFL pick, for the pick emails.

Written from numbers the pipeline saves on each player ("why", see
get_nfl_projections._why), all things the projection actually uses:

  script     the simulation's game script -- how much more or less this team
             throws than it normally does, given the spread and total
  defense    what tonight's defense allows to his position vs the league
  volume     the sim's targets / carries for him vs his recent average
  teammates  targets or carries freed up by teammates who are out
  vegas      the team's implied points
  wind       15+ mph outdoors (passing and receiving only)

Only reasons pointing the same way as the pick are shown, strongest first
(strength = how far past its "worth mentioning" bar the factor is). These
explain why OUR MODEL likes a side -- the books know these things too.
"""
from __future__ import annotations

from typing import List, Optional

RECEIVING = {"receptions", "reception_yds"}
RUSHING = {"rush_attempts", "rush_yds"}
PASSING = {"pass_yds", "pass_attempts", "pass_completions", "pass_tds"}
DEF_STAT = {"receptions": "rec", "reception_yds": "rec_yds", "rush_yds": "rush_yds", "rush_attempts": "rush_yds",
            "pass_yds": "pass_yds", "pass_attempts": "pass_yds", "pass_completions": "pass_yds", "pass_tds": "pass_yds"}
DEF_WORD = {"rec": "catches", "rec_yds": "receiving yards", "rush_yds": "rushing yards", "pass_yds": "passing yards"}
LEAGUE_IMPLIED = 22.5

# the bar each factor must clear to be worth a sentence
BAR = {"script": 0.02, "defense": 0.08, "targets": 0.7, "carries": 2.0, "tm_tgt": 0.08, "tm_car": 4.0,
       "vegas": 3.0, "wind": 15.0, "qb": 0.4}


def _spread_text(team: str, sp: Optional[float]) -> str:
    if sp is None:
        return team
    if abs(sp) < 0.5:
        return f"{team} (pick'em)"
    return f"{team} favored by {abs(sp):g}" if sp < 0 else f"{team} a {sp:g}-pt underdog"


def reasons_for(player: dict, market: str, side: str, n: int = 2) -> List[str]:
    w = player.get("why") or {}
    if not w or side not in ("over", "under") or market == "anytime_td":
        return []
    sign = 1 if side == "over" else -1
    team, opp, pos = player.get("team"), player.get("opponent"), player.get("position")
    cands = []

    def add(strength_dir: float, bar: float, text: str):
        if strength_dir * sign >= bar:
            cands.append((abs(strength_dir) / bar, text))

    # game script
    s = w.get("script_shift")
    if s is not None and market != "rush_reception_yds":
        d = -s if market in RUSHING else s
        verb = "throw" if s > 0 else "run"
        add(d, BAR["script"], f"{_spread_text(team, w.get('team_spread'))} -- the sim has {team} {verb}ing on "
                              f"{abs(s) * 100:.0f}% more of its plays than usual")

    # defense
    stat = DEF_STAT.get(market)
    if market == "rush_reception_yds":
        stat = "rush_yds" if pos == "RB" else "rec_yds"
    if market in PASSING and pos != "QB":
        stat = None
    rel = (w.get("opp_rel") or {}).get(stat) if stat else None
    if rel:
        more = "more" if rel > 1 else "fewer"
        add(rel - 1, BAR["defense"], f"{opp} allows {abs(rel - 1) * 100:.0f}% {more} {DEF_WORD[stat]} to {pos}s than average")

    # volume
    if market in RECEIVING and w.get("sim_targets") is not None and w.get("ew_targets"):
        d = w["sim_targets"] - w["ew_targets"]
        if abs(d) >= 0.12 * w["ew_targets"]:
            add(d, BAR["targets"], f"sim gives him {w['sim_targets']:.1f} targets vs {w['ew_targets']:.1f} a game lately")
    if market in RUSHING | {"rush_reception_yds"} and w.get("sim_carries") is not None and w.get("ew_carries"):
        d = w["sim_carries"] - w["ew_carries"]
        if abs(d) >= 0.12 * w["ew_carries"]:
            add(d, BAR["carries"], f"sim gives him {w['sim_carries']:.1f} carries vs {w['ew_carries']:.1f} a game lately")

    # teammates out (only ever pushes up)
    if market in RECEIVING and (w.get("tm_out_tgt_share") or 0) > 0:
        add(w["tm_out_tgt_share"], BAR["tm_tgt"], f"teammates out free up {w['tm_out_tgt_share'] * 100:.0f}% of the targets")
    if market in RUSHING and (w.get("tm_out_carries") or 0) > 0:
        add(w["tm_out_carries"], BAR["tm_car"], f"teammates out free up {w['tm_out_carries']:.0f} carries a game")

    # a different QB than the one he's been catching passes from
    q = w.get("qb_change")
    if q and pos != "QB" and market in RECEIVING | {"rush_reception_yds"}:
        out = f" ({q['usual_status'].lower()})" if q.get("usual_status") else ""
        txt = f"{q['now']} starting for {q['usual']}{out}"
        if q.get("now_ypa") and q.get("usual_ypa"):
            d = q["now_ypa"] - q["usual_ypa"]
            add(d, BAR["qb"], f"{txt}: {q['now_ypa']:.1f} yds per attempt this season vs {q['usual_ypa']:.1f}")
            if abs(d) < BAR["qb"]:                      # a change worth knowing even when it's a wash
                cands.append((1.0, txt))
        else:
            cands.append((1.0, txt))

    # Vegas
    imp = w.get("implied_pts")
    if imp is not None and market not in ("rush_attempts", "pass_attempts"):
        add(imp - LEAGUE_IMPLIED, BAR["vegas"], f"{team} expected to score {imp:.1f}")

    # wind
    if (w.get("wind") or 0) >= BAR["wind"] and not w.get("dome") and market in RECEIVING | PASSING:
        add(-w["wind"], BAR["wind"], f"{w['wind']:.0f} mph wind")

    cands.sort(key=lambda c: -c[0])
    return [c[1] for c in cands[:n]]
