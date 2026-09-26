"""Today's lineup vs. the team's usual lineup -- against the same pitcher hand.

A pitcher's history was built against lineups at full strength. When two
regulars sit, today's lineup can be much weaker (or, when a team stacks
platoon bats, stronger) than the one his numbers came from. This measures
that gap.

USUAL LINEUP, BY HAND
---------------------
Teams run different lineups against lefties and righties -- platoon bats sit
against same-side starters as a matter of routine -- so "usual" is always the
usual lineup AGAINST TODAY'S STARTER'S HAND: the 9 players who started most
in the team's last USUAL_WINDOW games against that hand. With fewer than
MIN_HAND_GAMES such games (early season, or a team that rarely sees lefties)
it falls back to the last USUAL_WINDOW games of either hand, and says so.

Rebuilt from data already pulled -- no new source:
  batter_logs       who played each game, and their counting stats
  pitcher_logs      each game's starters (games_started == 1)
  season_pitching_stats / starters   each starter's throwing hand
  schedule_results  which team was home, to know whose starter a hitter faced
  mlb_rosters       only players still on the team count toward "usual"

A hitter "started" a game if he had STARTER_MIN_PA+ plate appearances --
bench bats who pinch-hit once don't count.

THE STATS, APPLES TO APPLES
---------------------------
Every hitter -- today's and the usual nine -- is measured the same way: his
season line in games against that starter hand (overall if he has fewer than
MIN_SPLIT_PA there), from the game logs:

  wOBA  (0.69 BB + 0.89 1B + 1.27 2B + 1.62 3B + 2.10 HR) / PA
        (standard weights; the logs have no HBP, so it runs a hair low --
        identically on both sides, which is what matters for the gap)
  K%    SO / PA
  BB%   BB / PA

Straight averages across the nine, same convention as the rest of the page.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.loader import MLB_TTL, get_mlb_data, ttl_cache

USUAL_WINDOW = 20
MIN_HAND_GAMES = 8
STARTER_MIN_PA = 3
MIN_SPLIT_PA = 40
LINEUP_SIZE = 9
NOTABLE_WOBA = 0.015     # gap (15 points) worth mentioning
BIG_WOBA = 0.025         # gap (25 points) that counts as a real edge
NOTABLE_RATE = 2.0       # K% / BB% points worth mentioning

W = {"bb": 0.69, "1b": 0.89, "2b": 1.27, "3b": 1.62, "hr": 2.10}


@ttl_cache(MLB_TTL)
def _games() -> pd.DataFrame:
    """One row per (hitter, game) with the hitter's team, whether he
    started, and the hand of the starter he faced."""
    d = get_mlb_data()
    b = d.get("batter_logs", pd.DataFrame())
    p = d.get("pitcher_logs", pd.DataFrame())
    sched = d.get("schedule_results", pd.DataFrame())
    if b.empty or p.empty or sched.empty:
        return pd.DataFrame()

    throws: Dict[Any, str] = {}
    for key in ("season_pitching_stats", "starters"):
        t = d.get(key, pd.DataFrame())
        if not t.empty and {"pitcher_id", "throws"} <= set(t.columns):
            throws.update(dict(zip(t["pitcher_id"], t["throws"])))

    st = p[p["games_started"] == 1][["game_pk", "pitcher_id", "is_home"]].copy()
    st["hand"] = st["pitcher_id"].map(throws)
    # The starter a hitter faced is the one on the OTHER side of the field.
    faced = {(g, bool(h)): hand for g, h, hand in zip(st["game_pk"], st["is_home"], st["hand"])}

    teams = {g: (h, a) for g, h, a in zip(sched["game_pk"], sched["home_team"], sched["away_team"])}
    g = b.copy()
    g["team"] = [teams.get(pk, (None, None))[0 if home else 1] for pk, home in zip(g["game_pk"], g["is_home"])]
    g["hand"] = [faced.get((pk, not bool(home))) for pk, home in zip(g["game_pk"], g["is_home"])]
    g["started"] = pd.to_numeric(g["plate_appearances"], errors="coerce").fillna(0) >= STARTER_MIN_PA
    g["date"] = pd.to_datetime(g["date"], errors="coerce")
    return g[g["team"].notna()]


def _line(rows: pd.DataFrame) -> Optional[Dict[str, float]]:
    pa = float(pd.to_numeric(rows["plate_appearances"], errors="coerce").sum())
    if pa <= 0:
        return None
    n = lambda c: float(pd.to_numeric(rows[c], errors="coerce").fillna(0).sum())  # noqa: E731
    h, d2, d3, hr, bb, so = n("hits"), n("doubles"), n("triples"), n("home_runs"), n("walks"), n("strikeouts")
    singles = h - d2 - d3 - hr
    woba = (W["bb"] * bb + W["1b"] * singles + W["2b"] * d2 + W["3b"] * d3 + W["hr"] * hr) / pa
    return {"woba": woba, "k": so / pa * 100, "bb": bb / pa * 100, "pa": pa}


@ttl_cache(MLB_TTL)
def _hitter_lines() -> Dict[tuple, Dict[str, float]]:
    """(player_id, hand) -> season line vs that hand; (player_id, None) -> overall."""
    g = _games()
    out: Dict[tuple, Dict[str, float]] = {}
    if g.empty:
        return out
    for pid, rows in g.groupby("player_id"):
        overall = _line(rows)
        if overall:
            out[(pid, None)] = overall
        for hand, hr in rows.groupby("hand"):
            ln = _line(hr)
            if ln:
                out[(pid, hand)] = ln
    return out


def hitter_line(pid: Any, hand: Optional[str]) -> Optional[Dict[str, float]]:
    lines = _hitter_lines()
    split = lines.get((pid, hand))
    if split and split["pa"] >= MIN_SPLIT_PA:
        return split
    return lines.get((pid, None))


def usual_lineup(team: str, hand: Optional[str], before: pd.Timestamp) -> Dict[str, Any]:
    """The usual nine for `team` against `hand`, from games before `before`."""
    g = _games()
    empty = {"player_ids": [], "names": {}, "games": 0, "basis": None}
    if g.empty:
        return empty
    tg = g[(g["team"] == team) & (g["date"] < before)]
    rosters = get_mlb_data().get("mlb_rosters", pd.DataFrame())
    on_team = set(rosters.loc[rosters["team"] == team, "player_id"]) if not rosters.empty else None

    def pick(frame: pd.DataFrame, basis: str) -> Dict[str, Any]:
        recent = frame.drop_duplicates("game_pk").sort_values("date").tail(USUAL_WINDOW)["game_pk"]
        starts = frame[frame["game_pk"].isin(set(recent)) & frame["started"]]
        if on_team:
            starts = starts[starts["player_id"].isin(on_team)]
        counts = starts.groupby("player_id").size().sort_values(ascending=False).head(LINEUP_SIZE)
        names = dict(zip(starts["player_id"], starts["player"]))
        return {"player_ids": list(counts.index), "names": {k: names[k] for k in counts.index},
                "games": int(len(recent)), "basis": basis}

    by_hand = tg[tg["hand"] == hand] if hand else tg.iloc[0:0]
    if by_hand["game_pk"].nunique() >= MIN_HAND_GAMES:
        return pick(by_hand, "vs_hand")
    return pick(tg, "overall")


def _avg(pids: List[Any], hand: Optional[str]) -> Optional[Dict[str, float]]:
    lines = [ln for ln in (hitter_line(p, hand) for p in pids) if ln]
    if not lines:
        return None
    return {k: sum(ln[k] for ln in lines) / len(lines) for k in ("woba", "k", "bb")}


def lineup_vs_usual(team: str, hand: Optional[str], today_ids: List[Any],
                    today_names: Dict[Any, str], game_time: Any) -> Optional[Dict[str, Any]]:
    """Today's posted lineup vs. the usual one against this hand. None when
    there isn't enough history to say."""
    before = pd.to_datetime(game_time, utc=True, errors="coerce")
    before = (pd.Timestamp.now() if pd.isna(before) else before.tz_convert(None)).normalize()
    usual = usual_lineup(team, hand, before)
    if len(usual["player_ids"]) < LINEUP_SIZE - 1:
        return None
    t, u = _avg(today_ids, hand), _avg(usual["player_ids"], hand)
    if not t or not u:
        return None
    today_set = set(today_ids)
    missing = [{"player": usual["names"][p],
                "woba": round((hitter_line(p, hand) or {}).get("woba", 0), 3)}
               for p in usual["player_ids"] if p not in today_set]
    missing.sort(key=lambda m: m["woba"], reverse=True)
    extra = [today_names.get(p) for p in today_ids if p not in set(usual["player_ids"])]
    diff = {"woba": round(t["woba"] - u["woba"], 3), "k": round(t["k"] - u["k"], 1),
            "bb": round(t["bb"] - u["bb"], 1)}
    return {
        "hand": hand, "basis": usual["basis"], "games": usual["games"],
        "today": {"woba": round(t["woba"], 3), "k": round(t["k"], 1), "bb": round(t["bb"], 1)},
        "usual": {"woba": round(u["woba"], 3), "k": round(u["k"], 1), "bb": round(u["bb"], 1)},
        "diff": diff,
        "missing": missing, "replacements": [x for x in extra if x],
        "notable": (abs(diff["woba"]) >= NOTABLE_WOBA or abs(diff["k"]) >= NOTABLE_RATE
                    or abs(diff["bb"]) >= NOTABLE_RATE),
        "big": abs(diff["woba"]) >= BIG_WOBA,
    }


def for_opposing_lineup(rows: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Convenience: `rows` = one team's posted lineup from daily_matchups
    (all facing the same starter)."""
    if rows is None or rows.empty or "batter_id" not in rows.columns:
        return None
    r0 = rows.iloc[0]
    try:
        ids = list(rows["batter_id"])
        names = dict(zip(rows["batter_id"], rows["player"]))
        return lineup_vs_usual(r0.get("team"), r0.get("throws"), ids, names, r0.get("game_time_utc"))
    except Exception as e:
        print(f"Warning: lineup vs usual for {r0.get('team')} failed: {e}")
        return None
