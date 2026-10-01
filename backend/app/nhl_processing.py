"""Turn one NHL game's raw documents into the rows the NHL pages read.

    process_game(game, box, pbp, shifts) -> {
        "skaters": [...], "goalies": [...], "teams": [...],
        "units": [...], "unit_matchups": [...], "zones": [...], "shots": [...],
    }

Inputs are the parsed shapes from nhl_api.py (parse_boxscore, parse_pbp,
parse_shifts) plus the schedule row. Pure: no network, no files -- which is
what lets tests/test_nhl_processing.py drive it with a synthetic game.

HOW THE HARD PARTS WORK
-----------------------
Strength state. Every play-by-play event carries a 4-digit situationCode:
away goalie in net (1/0), away skaters, home skaters, home goalie. The code
is carried forward second by second until the next event. That slightly
overstates a power play that expires between whistles (the next event shows
5-on-5), which is a few seconds per penalty -- fine for time-on-ice splits.

Who played together. Shift charts give each skater's on-ice seconds. A
player x second matrix, masked to 5-on-5 seconds, gives shared ice time for
every pair; lines are built greedily (top-TOI forward + the two forwards he
shared the most time with, then repeat) and pairs the same way for
defensemen. Power-play units are the top five / next five skaters by
power-play time. This is what actually happened on the ice, not a projected
lineup.

Shot coordinates are flipped so every team attacks toward +x (net at
x = +89), using the home team's defending side per event.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

SHOT_TYPES = {"shot-on-goal", "missed-shot", "blocked-shot", "goal"}
UNBLOCKED = {"shot-on-goal", "missed-shot", "goal"}
ON_GOAL = {"shot-on-goal", "goal"}
FORWARD_POS = {"C", "L", "R", "F", "LW", "RW"}
ZONES = ["net_front", "slot", "high_slot", "left_circle", "right_circle",
         "left_point", "right_point", "wide"]
HIGH_DANGER = {"net_front", "slot"}
NET_X = 89.0


# ── small helpers ──────────────────────────────────────────────────────────

def parse_situation(code: Optional[str]) -> Optional[Tuple[int, int, int, int]]:
    """'1451' -> (away goalie, away skaters, home skaters, home goalie)."""
    if not code or len(code) != 4 or not code.isdigit():
        return None
    a_g, a_s, h_s, h_g = (int(c) for c in code)
    if not (0 <= a_s <= 6 and 0 <= h_s <= 6):
        return None
    return a_g, a_s, h_s, h_g


def zone_for(x: float, y: float) -> str:
    """Shot location bucket, in attacking-toward-+x coordinates. 'Left' is
    the shooter's left when facing the net (+y)."""
    dist = math.hypot(NET_X - x, y)
    if x > NET_X:
        return "wide"
    if dist <= 12:
        return "net_front"
    if x >= 69 and abs(y) <= 9:
        return "slot"
    if x >= 54 and abs(y) <= 9:
        return "high_slot"
    if x >= 54 and abs(y) <= 30:
        return "left_circle" if y > 0 else "right_circle"
    if x < 54:
        return "left_point" if y >= 0 else "right_point"
    return "wide"


def shot_geometry(x: float, y: float) -> Tuple[float, float]:
    dx = NET_X - x
    dist = math.hypot(dx, y)
    angle = math.degrees(math.atan2(abs(y), dx))  # >90 means from behind the goal line
    return round(dist, 1), round(angle, 1)


def team_result(gf: int, ga: int, last_period: Optional[str]) -> str:
    if gf > ga:
        return "W"
    return "OTL" if last_period in ("OT", "SO") else "L"


# ── main entry point ───────────────────────────────────────────────────────

def process_game(game: Dict[str, Any], box: Dict[str, Any], pbp: Dict[str, Any],
                 shifts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    gid = int(game["game_id"])
    season = int(game.get("season") or 0)
    gdate = str(game.get("date"))
    gtype = int(game.get("game_type") or 2)
    home = pbp.get("home") or box.get("home") or game.get("home")
    away = pbp.get("away") or box.get("away") or game.get("away")
    other = {home: away, away: home}
    roster: Dict[int, Dict[str, Any]] = dict(pbp.get("roster") or {})
    events = pbp.get("events") or []

    # Box-score players the play-by-play roster somehow missed still need a team.
    for p in box.get("skaters", []) + box.get("goalies", []):
        roster.setdefault(p["player_id"], {"name": p.get("name_short") or "", "team": p["team"],
                                           "pos": "G" if p in box.get("goalies", []) else p.get("pos")})

    def team_of(pid: Any) -> Optional[str]:
        if pid is None:
            return None
        r = roster.get(int(pid))
        return r["team"] if r else None

    # ── timeline ──
    last_evt = max([e["sec"] for e in events], default=3600)
    last_shift = max([s["end"] for s in shifts], default=0)
    L = int(max(last_evt, last_shift, 1)) + 1

    a_g = np.ones(L, np.int8); a_s = np.full(L, 5, np.int8)
    h_s = np.full(L, 5, np.int8); h_g = np.ones(L, np.int8)
    coded = [(e["sec"], parse_situation(e["situation"])) for e in events if parse_situation(e["situation"])]
    for i, (t, c) in enumerate(coded):
        t_end = coded[i + 1][0] if i + 1 < len(coded) else L
        t0, t1 = min(int(t), L), min(int(t_end), L)
        if t1 <= t0:
            continue
        a_g[t0:t1], a_s[t0:t1], h_s[t0:t1], h_g[t0:t1] = c
    # Shift charts, when present, give a better strength timeline than the
    # event codes: count each team's skaters on the ice every second (a
    # 5-second rolling median irons out the overlap during line changes) and
    # check whether a goalie is in net. This catches the exact second a power
    # play starts and ends instead of waiting for the next whistle.
    def on_ice_counts(team: str, want_goalie: bool) -> Optional[np.ndarray]:
        arr = np.zeros(L, np.int16)
        any_shift = False
        for sh in shifts:
            pos = (roster.get(sh["player_id"]) or {}).get("pos")
            if (roster.get(sh["player_id"]) or {}).get("team", sh.get("team")) != team:
                continue
            if (pos == "G") != want_goalie:
                continue
            any_shift = True
            arr[max(0, sh["start"]):min(L, sh["end"])] += 1
        return arr if any_shift else None

    def median5(a: np.ndarray) -> np.ndarray:
        pad = np.pad(a, 2, mode="edge")
        win = np.lib.stride_tricks.sliding_window_view(pad, 5)
        return np.median(win, axis=1).astype(np.int8)

    h_cnt, a_cnt = on_ice_counts(home, False), on_ice_counts(away, False)
    if h_cnt is not None and a_cnt is not None:
        h_s = np.clip(median5(h_cnt), 0, 6).astype(np.int8)
        a_s = np.clip(median5(a_cnt), 0, 6).astype(np.int8)
        hg_cnt, ag_cnt = on_ice_counts(home, True), on_ice_counts(away, True)
        if hg_cnt is not None:
            h_g = (median5(hg_cnt) > 0).astype(np.int8)
        if ag_cnt is not None:
            a_g = (median5(ag_cnt) > 0).astype(np.int8)
        # a stoppage between periods shows nobody on the ice; call it 5v5
        empty = (h_s == 0) & (a_s == 0)
        h_s[empty] = 5; a_s[empty] = 5; h_g[empty] = 1; a_g[empty] = 1

    goalies_in = (a_g == 1) & (h_g == 1)
    ev5 = (a_s == 5) & (h_s == 5) & goalies_in
    pp_mask = {home: (h_s > a_s) & goalies_in, away: (a_s > h_s) & goalies_in}

    def pp_opportunities(mask: np.ndarray) -> int:
        n, run = 0, 0
        for v in mask:
            if v:
                run += 1
                if run == 5:          # a stretch has to last 5s to count
                    n += 1
            else:
                run = 0
        return n

    # ── on-ice matrix from shifts ──
    skater_ids = sorted({s["player_id"] for s in shifts
                         if (roster.get(s["player_id"]) or {}).get("pos") != "G"})
    idx = {pid: i for i, pid in enumerate(skater_ids)}
    M = np.zeros((len(skater_ids), L), dtype=bool)
    for s in shifts:
        i = idx.get(s["player_id"])
        if i is not None:
            M[i, max(0, s["start"]):min(L, s["end"])] = True
    have_shifts = len(skater_ids) > 0

    # ── event pass ──
    T = {t: {"cf": 0, "ca": 0, "cf5": 0, "ca5": 0, "sog": 0, "sog_against": 0, "gf": 0, "ga": 0,
             "pp_goals": 0, "fo_w": 0, "fo_total": 0, "ub": 0, "dist_sum": 0.0, "hd": 0,
             "rebounds": 0, "rush": 0, "sog_lead": 0, "sog_tied": 0, "sog_trail": 0,
             "pgf": [0, 0, 0, 0], "pga": [0, 0, 0, 0], "first10": 0}
         for t in (home, away)}
    cf_sec = {t: np.zeros(L, np.int16) for t in (home, away)}
    gf_sec = {t: np.zeros(L, np.int16) for t in (home, away)}
    player_att: Dict[int, int] = {}
    player_fo: Dict[int, List[int]] = {}
    pp_points: Dict[int, int] = {}
    shots: List[Dict[str, Any]] = []
    zone_counts = {(t, st): {z: 0 for z in ZONES} for t in (home, away) for st in ("all", "5v5", "pp")}
    score = {home: 0, away: 0}
    home_diff = np.zeros(L, np.int8)
    last_goal_t = 0
    prev_coord_events: List[Tuple[int, Optional[str], float, float]] = []   # (sec, team, x, y) raw
    last_attempt_t: Dict[str, int] = {home: -99, away: -99}

    def direction(team: str, e: Dict[str, Any], x: float) -> int:
        side = e.get("defending_side")
        if side in ("left", "right"):
            d_home = 1 if side == "left" else -1
            return d_home if team == home else -d_home
        zc = (e.get("details") or {}).get("zoneCode")
        sgn = 1 if x >= 0 else -1
        return sgn if zc != "D" else -sgn

    for e in events:
        typ, d, s = e["type"], e["details"], min(int(e["sec"]), L - 1)
        x, y = d.get("xCoord"), d.get("yCoord")

        if typ in SHOT_TYPES:
            shooter = d.get("scoringPlayerId") if typ == "goal" else d.get("shootingPlayerId")
            team = team_of(shooter) or (e["owner"] if typ != "blocked-shot" else None)
            if team not in T:
                continue
            opp = other[team]
            sit = parse_situation(e["situation"])
            if sit:
                ag, as_, hs, hg = sit
                t_sk, o_sk = (hs, as_) if team == home else (as_, hs)
                o_goalie_in = (ag if team == home else hg) == 1
                t_goalie_in = (hg if team == home else ag) == 1
            else:
                t_sk = o_sk = 5
                o_goalie_in = t_goalie_in = True
            empty_net = not o_goalie_in
            strength = "pp" if (t_sk > o_sk and o_goalie_in and t_goalie_in) else \
                       "sh" if (t_sk < o_sk and o_goalie_in and t_goalie_in) else "ev"
            is5 = t_sk == 5 and o_sk == 5 and o_goalie_in and t_goalie_in

            T[team]["cf"] += 1; T[opp]["ca"] += 1
            if is5:
                T[team]["cf5"] += 1; T[opp]["ca5"] += 1
            cf_sec[team][s] += 1
            if shooter is not None:
                player_att[int(shooter)] = player_att.get(int(shooter), 0) + 1

            if typ in ON_GOAL:
                T[team]["sog"] += 1; T[opp]["sog_against"] += 1
                diff = score[team] - score[opp]
                T[team]["sog_lead" if diff > 0 else "sog_trail" if diff < 0 else "sog_tied"] += 1

            if typ in UNBLOCKED and x is not None and y is not None:
                dirn = direction(team, e, float(x))
                xn, yn = float(x) * dirn, float(y) * dirn
                dist, ang = shot_geometry(xn, yn)
                zone = zone_for(xn, yn)
                rebound = s - last_attempt_t[team] <= 3
                rush = False
                for (ps, pteam, px, py) in reversed(prev_coord_events):
                    if s - ps > 4:
                        break
                    if px * dirn < 25:        # previous event in neutral/defensive zone
                        rush = True
                        break
                if not empty_net:
                    T[team]["ub"] += 1
                    T[team]["dist_sum"] += dist
                    T[team]["hd"] += int(zone in HIGH_DANGER)
                    T[team]["rebounds"] += int(rebound)
                    T[team]["rush"] += int(rush)
                    zone_counts[(team, "all")][zone] += 1
                    if is5:
                        zone_counts[(team, "5v5")][zone] += 1
                    if strength == "pp":
                        zone_counts[(team, "pp")][zone] += 1
                shots.append({
                    "game_id": gid, "season": season, "date": gdate, "team": team, "opp": opp,
                    "shooter_id": int(shooter) if shooter is not None else None,
                    "goalie_id": int(d["goalieInNetId"]) if d.get("goalieInNetId") is not None else None,
                    "event": typ, "is_goal": typ == "goal", "shot_type": (d.get("shotType") or "unknown"),
                    "x": round(xn, 1), "y": round(yn, 1), "distance": dist, "angle": ang,
                    "rebound": bool(rebound), "rush": bool(rush), "strength": strength, "is5": bool(is5),
                    "empty_net": bool(empty_net), "zone": zone, "period": e["period"], "sec": s,
                })
            if typ in ("shot-on-goal", "missed-shot", "blocked-shot", "goal"):
                last_attempt_t[team] = s

            if typ == "goal":
                T[team]["gf"] += 1; T[opp]["ga"] += 1
                gf_sec[team][s] += 1
                per = min(e["period"], 4) - 1
                T[team]["pgf"][per] += 1; T[opp]["pga"][per] += 1
                if s < 600:
                    T[home]["first10"] = T[away]["first10"] = 1
                if strength == "pp":
                    T[team]["pp_goals"] += 1
                    for k in ("scoringPlayerId", "assist1PlayerId", "assist2PlayerId"):
                        if d.get(k) is not None:
                            pp_points[int(d[k])] = pp_points.get(int(d[k]), 0) + 1
                # score timeline (home minus away), from this second on
                home_diff[last_goal_t:s] = score[home] - score[away]
                score[team] += 1
                last_goal_t = s

        elif typ == "faceoff":
            w, l_ = d.get("winningPlayerId"), d.get("losingPlayerId")
            wt = team_of(w) or e["owner"]
            if wt in T:
                T[wt]["fo_w"] += 1
                T[wt]["fo_total"] += 1
                T[other[wt]]["fo_total"] += 1
            for pid, won in ((w, 1), (l_, 0)):
                if pid is not None:
                    rec = player_fo.setdefault(int(pid), [0, 0])
                    rec[0] += won; rec[1] += 1

        if x is not None and y is not None:
            prev_coord_events.append((s, e.get("owner"), float(x), float(y)))
            if len(prev_coord_events) > 20:
                prev_coord_events.pop(0)

    home_diff[last_goal_t:] = score[home] - score[away]
    sec_state = {
        home: {"lead": int((home_diff > 0).sum()), "tied": int((home_diff == 0).sum()), "trail": int((home_diff < 0).sum())},
        away: {"lead": int((home_diff < 0).sum()), "tied": int((home_diff == 0).sum()), "trail": int((home_diff > 0).sum())},
    }

    # ── scores / results (box score is authoritative when present) ──
    final = {home: game.get("home_score"), away: game.get("away_score")}
    for t in (home, away):
        if final[t] is None:
            final[t] = T[t]["gf"]
    last_period = game.get("last_period")

    # ── units ──
    pos_of = {pid: (roster.get(pid) or {}).get("pos") for pid in skater_ids}
    team_ids = {t: [pid for pid in skater_ids if (roster.get(pid) or {}).get("team") == t] for t in (home, away)}
    ev_toi = {pid: int((M[idx[pid]] & ev5).sum()) for pid in skater_ids}
    pp_toi = {pid: int((M[idx[pid]] & pp_mask[(roster.get(pid) or {}).get("team")]).sum())
              if (roster.get(pid) or {}).get("team") in pp_mask else 0 for pid in skater_ids}

    def build_groups(ids: List[int], size: int, n_groups: int) -> List[List[int]]:
        if not ids:
            return []
        sub = M[[idx[p] for p in ids]] & ev5
        shared = sub.astype(np.int32) @ sub.T.astype(np.int32)
        remaining = sorted(ids, key=lambda p: -ev_toi[p])
        loc = {p: i for i, p in enumerate(ids)}
        groups = []
        while remaining and len(groups) < n_groups:
            a = remaining[0]
            cands = [p for p in remaining[1:] if ev_toi[p] > 0]
            best, best_score = None, -1
            for combo in combinations(cands, min(size - 1, len(cands))):
                members = (a,) + combo
                sc = sum(shared[loc[i], loc[j]] for i, j in combinations(members, 2))
                if sc > best_score:
                    best, best_score = list(members), sc
            if best is None:
                best = [a]
            groups.append(best)
            remaining = [p for p in remaining if p not in best]
        groups.sort(key=lambda g: -sum(ev_toi[p] for p in g))
        return groups

    def order_line(g: List[int]) -> List[int]:
        rank = {"L": 0, "LW": 0, "C": 1, "R": 2, "RW": 2}
        return sorted(g, key=lambda p: rank.get(pos_of.get(p) or "", 1))

    units: List[Dict[str, Any]] = []
    unit_masks: Dict[Tuple[str, str], np.ndarray] = {}
    player_line: Dict[int, str] = {}
    player_pp: Dict[int, str] = {}
    team_pp_sec = {t: int(pp_mask[t].sum()) for t in (home, away)}
    if have_shifts:
        for t in (home, away):
            fwd = [p for p in team_ids[t] if (pos_of.get(p) or "") in FORWARD_POS and ev_toi[p] > 0]
            dmen = [p for p in team_ids[t] if pos_of.get(p) == "D" and ev_toi[p] > 0]
            groups = [(f"L{i + 1}", order_line(g)) for i, g in enumerate(build_groups(fwd, 3, 4))]
            groups += [(f"D{i + 1}", g) for i, g in enumerate(build_groups(dmen, 2, 3))]
            if team_pp_sec[t] >= 30:
                by_pp = sorted([p for p in team_ids[t] if pp_toi[p] >= 10], key=lambda p: -pp_toi[p])
                if by_pp[:5]:
                    groups.append(("PP1", by_pp[:5]))
                if by_pp[5:10]:
                    groups.append(("PP2", by_pp[5:10]))
            for label, g in groups:
                mask = ev5 if not label.startswith("PP") else pp_mask[t]
                tog = np.all(M[[idx[p] for p in g]], axis=0) & mask
                unit_masks[(t, label)] = tog
                o = other[t]
                units.append({
                    "game_id": gid, "season": season, "date": gdate, "game_type": gtype,
                    "team": t, "opp": o, "unit": label,
                    "players_key": "-".join(str(p) for p in sorted(g)),
                    "player_ids": ",".join(str(p) for p in g),
                    "players": " · ".join((roster.get(p) or {}).get("name", str(p)) for p in g),
                    "toi_together": int(tog.sum()),
                    "cf": int(cf_sec[t][tog].sum()), "ca": int(cf_sec[o][tog].sum()),
                    "gf": int(gf_sec[t][tog].sum()), "ga": int(gf_sec[o][tog].sum()),
                })
                for p in g:
                    if label.startswith("PP"):
                        player_pp[p] = label
                    else:
                        player_line[p] = label

    # who faced whom (5v5): each line/pair's most-faced opposing line and pair
    unit_matchups: List[Dict[str, Any]] = []
    for (t, lab), tog in unit_masks.items():
        if lab.startswith("PP") or tog.sum() == 0:
            continue
        o = other[t]
        for kind in ("L", "D"):
            best, best_sec = None, 0
            for (t2, lab2), tog2 in unit_masks.items():
                if t2 != o or not lab2.startswith(kind) or lab2.startswith("PP"):
                    continue
                sec = int((tog & tog2).sum())
                if sec > best_sec:
                    best, best_sec = lab2, sec
            if best:
                unit_matchups.append({"game_id": gid, "season": season, "date": gdate, "team": t,
                                      "unit": lab, "opp": o, "opp_unit": best,
                                      "seconds": best_sec, "unit_toi": int(tog.sum())})

    # ── goalies ──
    goalie_rows = []
    # The starter is the goalie the box score flags; failing that, whoever
    # played the most minutes.
    starters: Dict[str, Optional[int]] = {home: None, away: None}
    for t in (home, away):
        played = [g for g in box.get("goalies", []) if g["team"] == t and g["toi"] > 0]
        flagged = [g for g in played if g["starter"]]
        pick = flagged[0] if flagged else (max(played, key=lambda g: g["toi"]) if played else None)
        starters[t] = pick["player_id"] if pick else None
    starter_names = {t: (roster.get(pid) or {}).get("name") if pid else None for t, pid in starters.items()}
    for g in box.get("goalies", []):
        if g["toi"] <= 0 or g["team"] not in T:
            continue
        t, o = g["team"], other[g["team"]]
        goalie_rows.append({
            "game_id": gid, "season": season, "date": gdate, "game_type": gtype,
            "team": t, "opp": o, "is_home": t == home,
            "player_id": g["player_id"], "player": (roster.get(g["player_id"]) or {}).get("name") or g["name_short"],
            "starter": bool(starters[t] == g["player_id"]), "decision": g.get("decision"),
            "toi": g["toi"], "shots_against": g["shots_against"], "saves": g["saves"],
            "goals_against": g["goals_against"],
            "save_pct": round(g["saves"] / g["shots_against"], 3) if g["shots_against"] else None,
            "team_result": team_result(final[t], final[o], last_period),
            "score": f"{final[t]}-{final[o]}",
        })

    # ── skaters ──
    skater_rows = []
    for p in box.get("skaters", []):
        pid, t = p["player_id"], p["team"]
        if t not in T:
            continue
        o = other[t]
        line = player_line.get(pid)
        mates = []
        if line:
            for u in units:
                if u["team"] == t and u["unit"] == line:
                    mates = [int(x) for x in u["player_ids"].split(",") if int(x) != pid]
        fo = player_fo.get(pid, [0, 0])
        skater_rows.append({
            "game_id": gid, "season": season, "date": gdate, "game_type": gtype,
            "team": t, "opp": o, "is_home": t == home,
            "player_id": pid, "player": (roster.get(pid) or {}).get("name") or p["name_short"],
            "pos": (roster.get(pid) or {}).get("pos") or p.get("pos"),
            "goals": p["goals"], "assists": p["assists"], "points": p["goals"] + p["assists"],
            "sog": p["sog"], "attempts": player_att.get(pid, p["sog"]), "hits": p["hits"],
            "blocks": p["blocks"], "pim": p["pim"], "pp_goals": p["pp_goals"],
            "pp_points": pp_points.get(pid, p["pp_goals"]),
            "toi": p["toi"], "pp_toi": pp_toi.get(pid) if have_shifts else None,
            "ev_toi": ev_toi.get(pid) if have_shifts else None, "shifts": p["shifts"],
            "fo_wins": fo[0], "fo_taken": fo[1],
            "line": line, "pp_unit": player_pp.get(pid),
            "linemates": " · ".join((roster.get(m) or {}).get("name", str(m)) for m in mates) or None,
            "opp_goalie_id": starters[o], "opp_goalie": starter_names[o],
            "team_result": team_result(final[t], final[o], last_period),
            "score": f"{final[t]}-{final[o]}",
        })

    # ── team rows ──
    box_team = {t: {"hits": 0, "blocks": 0, "pim": 0} for t in (home, away)}
    for p in box.get("skaters", []):
        if p["team"] in box_team:
            for k in ("hits", "blocks", "pim"):
                box_team[p["team"]][k] += p[k]
    team_rows = []
    for t in (home, away):
        o = other[t]
        x = T[t]
        team_rows.append({
            "game_id": gid, "season": season, "date": gdate, "game_type": gtype,
            "team": t, "opp": o, "is_home": t == home,
            "goals_for": int(final[t]), "goals_against": int(final[o]),
            "result": team_result(final[t], final[o], last_period), "last_period": last_period,
            "shots_for": x["sog"], "shots_against": x["sog_against"],
            "cf": x["cf"], "ca": x["ca"], "cf5": x["cf5"], "ca5": x["ca5"],
            "hd_for": x["hd"], "hd_against": T[o]["hd"],
            "ub_for": x["ub"], "dist_sum_for": round(x["dist_sum"], 1),
            "rebounds_for": x["rebounds"], "rush_for": x["rush"],
            "pp_opps": pp_opportunities(pp_mask[t]), "pp_goals": x["pp_goals"],
            "times_shorthanded": pp_opportunities(pp_mask[o]), "pk_goals_against": T[o]["pp_goals"],
            "p1_gf": x["pgf"][0], "p1_ga": x["pga"][0], "p2_gf": x["pgf"][1], "p2_ga": x["pga"][1],
            "p3_gf": x["pgf"][2], "p3_ga": x["pga"][2], "ot_gf": x["pgf"][3], "ot_ga": x["pga"][3],
            "goal_first10": bool(x["first10"]),
            "fo_wins": x["fo_w"], "fo_total": x["fo_total"],
            "hits": box_team[t]["hits"], "blocks": box_team[t]["blocks"], "pim": box_team[t]["pim"],
            "sec_5v5": int(ev5.sum()), "sec_pp": int(pp_mask[t].sum()), "sec_sh": int(pp_mask[o].sum()),
            "sec_lead": sec_state[t]["lead"], "sec_tied": sec_state[t]["tied"], "sec_trail": sec_state[t]["trail"],
            "sog_lead": x["sog_lead"], "sog_tied": x["sog_tied"], "sog_trail": x["sog_trail"],
            "starter_goalie_id": starters[t], "starter_goalie": starter_names[t],
            "has_shifts": have_shifts,
        })

    zones = [{"game_id": gid, "season": season, "date": gdate, "game_type": gtype, "team": t, "opp": other[t],
              "strength": st, **counts} for (t, st), counts in zone_counts.items()]

    return {"skaters": skater_rows, "goalies": goalie_rows, "teams": team_rows, "units": units,
            "unit_matchups": unit_matchups, "zones": zones, "shots": shots}
