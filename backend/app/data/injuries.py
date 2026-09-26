"""Injury cards: what changed, who benefits, and whether the lines have moved.

Reads get_injuries.py's change log. For each recent, meaningful change it adds:

  NFL   Who absorbs the volume. The injured player's season target share and
        carry share are "vacated", and each teammate's share is scaled up in
        proportion (share / (1 - vacated)) -- a transparent estimate, not a
        projection: it assumes the work is spread the way it's already
        spread. Then, for the top beneficiaries, whether their main prop
        line has moved since the injury was first seen (from the odds
        snapshots). "Line hasn't moved" is the actionable part.
  NBA   The teammate whose minutes rose most when this player sat before
        (app/data/nba.py's get_biggest_beneficiary), when there's history.
  MLB   Status only -- lineups, not usage shares, decide who plays.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.loader import (
    get_injury_changes_data, get_nfl_player_week_usage, get_nfl_rosters,
    get_odds_snapshots_data, get_props_data, ttl_cache, MLB_TTL,
)

SERIOUS = {"Out", "IR", "PUP", "Suspended", "Doubtful", "IL-7", "IL-10", "IL-15", "IL-60"}
WATCH = {"Questionable", "Day-To-Day"}
SKILL_POSITIONS = {"QB", "RB", "WR", "TE", "FB"}

# Minimum share of team volume for a player's absence to be worth a card.
MIN_TARGET_SHARE = 0.08
MIN_CARRY_SHARE = 0.15
TOP_BENEFICIARIES = 3

# Which prop markets to check for each kind of vacated volume.
NFL_MARKETS = {"targets": ["receptions", "reception_yds"], "carries": ["rush_attempts", "rush_yds"]}


def _key(name: Any) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace(".", "").replace("'", "")
    return " ".join(p for p in s.split() if p not in {"jr", "sr", "ii", "iii", "iv", "v"})


def _txt(v) -> Optional[str]:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def is_meaningful(old: Optional[str], new: Optional[str]) -> bool:
    """A downgrade into a serious/watch status, or a return from a serious one."""
    if new in SERIOUS or new in WATCH:
        return old != new
    return new == "Active" and old in SERIOUS


# ── NFL volume ───────────────────────────────────────────────────────────

@ttl_cache(MLB_TTL)
def _nfl_shares() -> Dict[str, Any]:
    """Season target/carry share per player_id, with team and full name."""
    u = get_nfl_player_week_usage()
    if u.empty:
        return {"players": {}, "by_team": {}}
    season = u["season"].max()
    u = u[u["season"] == season]
    team_tot = u.groupby("posteam")[["targets", "carries"]].sum()
    per = u.groupby(["player_id", "posteam"])[["targets", "carries"]].sum().reset_index()
    per = per.join(team_tot, on="posteam", rsuffix="_team")
    per["target_share"] = per["targets"] / per["targets_team"].where(per["targets_team"] > 0)
    per["carry_share"] = per["carries"] / per["carries_team"].where(per["carries_team"] > 0)

    rosters = get_nfl_rosters()
    names = dict(zip(rosters["player_id"], rosters["full_name"])) if not rosters.empty else {}
    positions = dict(zip(rosters["player_id"], rosters["position"])) if not rosters.empty else {}
    abbr_names = dict(zip(u["player_id"], u["player"]))
    per["name"] = per["player_id"].map(lambda p: names.get(p) or abbr_names.get(p))
    per["position"] = per["player_id"].map(positions.get)
    players = {r["player_id"]: r for r in per.to_dict(orient="records")}
    by_team: Dict[str, List[dict]] = {}
    for r in players.values():
        by_team.setdefault(r["posteam"], []).append(r)
    return {"players": players, "by_team": by_team, "name_to_id": {_key(v): k for k, v in names.items()}}


def redistribute(injured: Dict[str, Any], teammates: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    """Scale each teammate's share up by the injured player's vacated share.
    Pure, so it's tested directly."""
    col = "target_share" if kind == "targets" else "carry_share"
    vacated = injured.get(col) or 0.0
    if vacated <= 0 or vacated >= 1:
        return []
    out = []
    for t in teammates:
        share = t.get(col)
        if t.get("player_id") == injured.get("player_id") or not share or share != share:
            continue
        # A QB's scrambles aren't designed carries; they don't absorb an RB's work.
        if kind == "carries" and t.get("position") == "QB":
            continue
        est = share / (1 - vacated)
        out.append({"player": t.get("name"), "share": round(share * 100, 1),
                    "est_share": round(est * 100, 1), "gain": round((est - share) * 100, 1)})
    out.sort(key=lambda x: x["gain"], reverse=True)
    return out[:TOP_BENEFICIARIES]


# ── line movement ────────────────────────────────────────────────────────

def _median_line(rows: pd.DataFrame) -> Optional[float]:
    lines = pd.to_numeric(rows["Line"], errors="coerce").dropna()
    return float(lines.median()) if not lines.empty else None


def line_move(sport: str, player: str, market: str, since_iso: str) -> Optional[Dict[str, Any]]:
    """Main-market line for `player` now vs. just before `since_iso`, as the
    median across books. None if there's no current line; `before` is None
    until the snapshot history reaches back that far."""
    props = get_props_data(sport)
    if props.empty:
        return None
    pk = _key(player)
    cur = props[(props["market"] == market) & (props["Player"].map(_key) == pk)]
    now_line = _median_line(cur) if not cur.empty else None
    if now_line is None:
        return None

    before = None
    snaps = get_odds_snapshots_data(sport)
    if not snaps.empty:
        s = snaps[(snaps["market"] == market) & (snaps["Player"].map(_key) == pk)]
        t = pd.to_datetime(s["observed_at"], utc=True, errors="coerce", format="mixed")
        s = s[t <= pd.to_datetime(since_iso, utc=True)]
        if not s.empty:
            s = s.sort_values("observed_at").drop_duplicates(subset=["bookmakers"], keep="last")
            before = _median_line(s)
    return {"market": market, "before": before, "now": now_line,
            "moved": None if before is None else round(now_line - before, 1)}


# ── NBA ──────────────────────────────────────────────────────────────────

def _nba_impact(player: str) -> Optional[Dict[str, Any]]:
    try:
        from app.data.nba import get_biggest_beneficiary
        res = get_biggest_beneficiary(player, "min")
    except Exception as e:
        print(f"Warning: NBA beneficiary for {player} failed: {e}")
        return None
    rows = res.get("results") or res.get("beneficiaries") or []
    if not rows:
        return None
    top = sorted(rows, key=lambda r: r.get("delta", 0), reverse=True)[:TOP_BENEFICIARIES]
    return {"kind": "minutes", "beneficiaries": [
        {"player": r["player"], "with": r.get("with"), "without": r.get("without"),
         "delta": r.get("delta"), "games_without": r.get("games_without")} for r in top]}


# ── feed ─────────────────────────────────────────────────────────────────

def _nfl_impact(change: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if change.get("position") not in SKILL_POSITIONS or change.get("new_status") not in SERIOUS:
        return None
    t = _nfl_shares()
    pid = _txt(change.get("gsis_id")) or t.get("name_to_id", {}).get(_key(change.get("player")))
    inj = t["players"].get(pid) if pid else None
    if not inj:
        return None
    kinds = []
    if (inj.get("target_share") or 0) >= MIN_TARGET_SHARE:
        kinds.append("targets")
    if (inj.get("carry_share") or 0) >= MIN_CARRY_SHARE:
        kinds.append("carries")
    if not kinds:
        return None
    out = []
    for kind in kinds:
        bens = redistribute(inj, t["by_team"].get(inj["posteam"], []), kind)
        for b in bens:
            b["lines"] = [m for m in (line_move("nfl", b["player"], mk, change["detected_at"])
                                      for mk in NFL_MARKETS[kind]) if m]
        col = "target_share" if kind == "targets" else "carry_share"
        out.append({"kind": kind, "player_share": round((inj.get(col) or 0) * 100, 1),
                    "beneficiaries": bens})
    return {"volume": out}


@ttl_cache(300)
def get_injury_feed(sport: str, hours: float = 36.0) -> List[Dict[str, Any]]:
    """Meaningful status changes in the last `hours`, newest first, with
    impact where we can estimate it."""
    log = get_injury_changes_data(sport)
    if log.empty:
        return []
    t = pd.to_datetime(log["detected_at"], utc=True, errors="coerce")
    log = log[t >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=hours)]
    out = []
    for c in log.sort_values("detected_at", ascending=False).to_dict(orient="records"):
        old, new = _txt(c.get("old_status")), _txt(c.get("new_status"))
        if not is_meaningful(old, new):
            continue
        card = {"sport": sport, "player": c.get("player"), "team": _txt(c.get("team")),
                "position": _txt(c.get("position")), "old_status": old, "new_status": new,
                "detail": _txt(c.get("detail")), "detected_at": _txt(c.get("detected_at")),
                "impact": None}
        if sport == "nfl":
            card["impact"] = _nfl_impact({**c, "detected_at": card["detected_at"]})
        elif sport == "nba" and new in SERIOUS:
            card["impact"] = _nba_impact(c.get("player"))
        out.append(card)
    return out
