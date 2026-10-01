"""Synthetic NHL games in the PARSED shapes nhl_api.py produces.

Deterministic (seeded) and small, but structured like a real game: four
forward lines and three defense pairs rotating on fixed shift lengths, power
plays with known units, shots with rink coordinates, goals, faceoffs. The
tests know the "true" lines and units, so they can check the shift-chart
logic actually recovers them.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Tuple


def team_players(team: str, base: int) -> Dict[str, Any]:
    fwd_lines = [[base + i * 3 + j for j in range(3)] for i in range(4)]       # L, C, R
    d_pairs = [[base + 20 + i * 2 + j for j in range(2)] for i in range(3)]
    goalies = [base + 30, base + 31]
    pos = {}
    for line in fwd_lines:
        pos[line[0]], pos[line[1]], pos[line[2]] = "L", "C", "R"
    for pair in d_pairs:
        for p in pair:
            pos[p] = "D"
    for g in goalies:
        pos[g] = "G"
    pp1 = fwd_lines[0] + [fwd_lines[1][1], d_pairs[0][0]]
    pp2 = [fwd_lines[1][0], fwd_lines[1][2], fwd_lines[2][1], d_pairs[1][0], d_pairs[1][1]]
    pk = [fwd_lines[3][0], fwd_lines[3][1], d_pairs[2][0], d_pairs[2][1]]
    return {"team": team, "lines": fwd_lines, "pairs": d_pairs, "goalies": goalies,
            "pos": pos, "pp1": pp1, "pp2": pp2, "pk": pk}


def make_game(game_id: int = 2025020001, date: str = "2025-10-08", home: str = "CAR", away: str = "FLA",
              seed: int = 1, home_base: int = 1000, away_base: int = 2000,
              penalties: Tuple[Tuple[int, str], ...] = ((300, "away"), (1500, "home"), (2700, "away")),
              season: int = 20252026, goals: Tuple[int, int] = (3, 2),
              ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    rnd = random.Random(seed)
    H, A = team_players(home, home_base), team_players(away, away_base)
    L = 3600
    # which side is on a power play each second (None, "home", "away")
    pp_side: List[Any] = [None] * L
    for t0, who_penalized in penalties:
        benefit = "home" if who_penalized == "away" else "away"
        for s in range(t0, min(L, t0 + 120)):
            pp_side[s] = benefit

    on_ice: Dict[int, List[bool]] = {}
    def mark(pid: int, s: int):
        on_ice.setdefault(pid, [False] * L)[s] = True

    for T in (H, A):
        side = "home" if T is H else "away"
        f_lens, d_lens = [50, 45, 40, 35], [60, 55, 50]
        f_cycle = [(i, n) for i, n in enumerate(f_lens)]
        d_cycle = [(i, n) for i, n in enumerate(d_lens)]
        f_sched, d_sched = [], []
        while len(f_sched) < L:
            for i, n in f_cycle:
                f_sched += [i] * n
        while len(d_sched) < L:
            for i, n in d_cycle:
                d_sched += [i] * n
        for s in range(L):
            pp = pp_side[s]
            if pp == side:
                t_in = s - max(t0 for t0, _ in penalties if t0 <= s)
                unit = T["pp1"] if t_in < 70 else T["pp2"]
                for p in unit:
                    mark(p, s)
            elif pp is not None:
                for p in T["pk"]:
                    mark(p, s)
            else:
                for p in T["lines"][f_sched[s]]:
                    mark(p, s)
                for p in T["pairs"][d_sched[s]]:
                    mark(p, s)

    for T in (H, A):                      # starting goalie plays every second
        for s in range(L):
            mark(T["goalies"][0], s)

    shifts = []
    for pid, arr in on_ice.items():
        team = home if pid < away_base else away
        s = 0
        while s < L:
            if arr[s]:
                e = s
                while e < L and arr[e] and (e == s or (e % 1200) != 0):
                    e += 1
                shifts.append({"player_id": pid, "team": team, "start": s, "end": e})
                s = e
            else:
                s += 1

    roster = {}
    for T in (H, A):
        for pid, p in T["pos"].items():
            roster[pid] = {"name": f"{T['team']} Player {pid}", "team": T["team"], "pos": p}

    def sit(s: int) -> str:
        pp = pp_side[min(s, L - 1)]
        if pp == "home":
            return "1451"
        if pp == "away":
            return "1541"
        return "1551"

    events: List[Dict[str, Any]] = []
    def ev(typ, s, owner, **details):
        period = s // 1200 + 1
        events.append({"type": typ, "period": period, "period_type": "REG", "sec": s, "sort": len(events),
                       "situation": sit(s), "owner": owner,
                       "defending_side": "left" if period in (1, 3) else "right", "details": details})

    score = {home: 0, away: 0}
    for per in range(3):
        ev("faceoff", per * 1200, home, winningPlayerId=H["lines"][0][1], losingPlayerId=A["lines"][0][1],
           xCoord=0, yCoord=0)
    goals_left = {home: goals[0], away: goals[1]}
    for s in range(20, L - 10, 37):
        attacking = home if rnd.random() < 0.55 else away
        T = H if attacking == home else A
        O = A if attacking == home else H
        period = s // 1200 + 1
        home_right = period in (1, 3)                 # home defends left -> attacks right
        sign = 1 if (attacking == home) == home_right else -1
        on = [p for p in (T["lines"][0] + T["lines"][1] + T["pairs"][0] + T["pp1"] + T["pp2"]
                          + T["lines"][2] + T["lines"][3] + T["pairs"][1] + T["pairs"][2] + T["pk"])
              if on_ice.get(p, [False] * L)[s]]
        shooter = on[0] if on else T["lines"][0][0]
        x, y = sign * rnd.uniform(40, 85), rnd.uniform(-20, 20)
        goalie = O["goalies"][0]
        r = rnd.random()
        if r < 0.12 and goals_left[attacking] > 0:
            goals_left[attacking] -= 1
            score[attacking] += 1
            ev("goal", s, attacking, scoringPlayerId=shooter, assist1PlayerId=T["lines"][0][1],
               goalieInNetId=goalie, xCoord=x, yCoord=y, shotType=rnd.choice(["wrist", "snap", "slap"]), zoneCode="O")
        elif r < 0.6:
            ev("shot-on-goal", s, attacking, shootingPlayerId=shooter, goalieInNetId=goalie,
               xCoord=x, yCoord=y, shotType=rnd.choice(["wrist", "snap", "slap"]), zoneCode="O")
        elif r < 0.8:
            ev("missed-shot", s, attacking, shootingPlayerId=shooter, xCoord=x, yCoord=y,
               shotType=rnd.choice(["wrist", "snap", "slap"]), zoneCode="O")
        else:
            ev("blocked-shot", s, other_team(attacking, home, away), shootingPlayerId=shooter,
               blockingPlayerId=O["pairs"][0][0], xCoord=x, yCoord=y, zoneCode="D")
        if rnd.random() < 0.3:
            ev("hit", s + 2, attacking, hittingPlayerId=shooter, xCoord=-x, yCoord=y)
    events.sort(key=lambda e: (e["sec"], e["sort"]))

    # box score consistent with the events and shifts
    sog = {}
    goals = {}
    for e in events:
        d = e["details"]
        if e["type"] == "goal":
            goals[d["scoringPlayerId"]] = goals.get(d["scoringPlayerId"], 0) + 1
            sog[d["scoringPlayerId"]] = sog.get(d["scoringPlayerId"], 0) + 1
        elif e["type"] == "shot-on-goal":
            sog[d["shootingPlayerId"]] = sog.get(d["shootingPlayerId"], 0) + 1
    skaters, goalies = [], []
    for T in (H, A):
        for pid, p in T["pos"].items():
            if p == "G":
                continue
            skaters.append({"player_id": pid, "team": T["team"], "name_short": f"P. {pid}", "pos": p,
                            "goals": goals.get(pid, 0), "assists": 0, "pim": 0, "hits": 0, "blocks": 0,
                            "sog": sog.get(pid, 0), "pp_goals": 0, "toi": sum(on_ice.get(pid, [])),
                            "shifts": 10, "plus_minus": 0})
        O = A if T is H else H
        sa = sum(1 for e in events if e["type"] in ("shot-on-goal", "goal") and e["owner"] == O["team"])
        ga = score[O["team"]]
        goalies.append({"player_id": T["goalies"][0], "team": T["team"], "name_short": "G. One", "toi": 3600,
                        "starter": True, "decision": "W" if score[T["team"]] > ga else "L",
                        "shots_against": sa, "saves": sa - ga, "goals_against": ga})
        goalies.append({"player_id": T["goalies"][1], "team": T["team"], "name_short": "G. Two", "toi": 0,
                        "starter": False, "decision": None, "shots_against": 0, "saves": 0, "goals_against": 0})

    game = {"game_id": game_id, "season": season, "game_type": 2, "date": date, "home": home, "away": away,
            "home_score": score[home], "away_score": score[away], "state": "OFF", "last_period": "REG",
            "start_utc": f"{date}T23:00:00Z"}
    box = {"home": home, "away": away, "skaters": skaters, "goalies": goalies}
    pbp = {"home": home, "away": away, "roster": roster, "events": events}
    truth = {"H": H, "A": A, "score": score}
    return game, box, pbp, shifts, truth


def other_team(t: str, home: str, away: str) -> str:
    return away if t == home else home


TEAM_BASE = {"CAR": 1000, "FLA": 2000, "NYR": 3000, "BOS": 4000}


def make_league(today: str = "2026-11-10"):
    """Two seasons of games among four teams, plus future games from `today`.

    Returns (schedule_rows, games_by_id) where games_by_id maps a completed
    game's id to the (game, box, pbp, shifts) fixture tuple.
    """
    import datetime as dt
    teams = list(TEAM_BASE)
    pairs = [("FLA", "CAR"), ("NYR", "BOS"), ("CAR", "NYR"), ("BOS", "FLA"), ("CAR", "BOS"), ("FLA", "NYR")]
    rows, games = [], {}
    t = dt.date.fromisoformat(today)

    def add(season: int, start: dt.date, n_days: int, step: int, first_id: int, final_until: dt.date):
        gid = first_id
        d = start
        k = 0
        for _ in range(n_days):
            for j in range(2):
                away, home = pairs[(k + j * 3) % len(pairs)]
                gid += 1
                is_final = d < final_until
                seed = gid % 97
                g, b, p, s, truth = make_game(game_id=gid, date=d.isoformat(), home=home, away=away, seed=seed,
                                              home_base=TEAM_BASE[home], away_base=TEAM_BASE[away],
                                              season=season, goals=(seed % 4 + 1, (seed // 4) % 4 + 1))
                row = {"game_id": gid, "season": season, "game_type": 2, "date": d.isoformat(),
                       "start_utc": f"{d.isoformat()}T23:00:00Z", "away": away, "home": home,
                       "away_score": g["away_score"] if is_final else None,
                       "home_score": g["home_score"] if is_final else None,
                       "state": "OFF" if is_final else "FUT", "last_period": "REG" if is_final else None,
                       "venue": None, "neutral": False}
                if g["away_score"] == g["home_score"] and is_final:
                    row["last_period"] = "SO"
                rows.append(row)
                if is_final:
                    g.update({k2: row[k2] for k2 in ("away_score", "home_score", "last_period")})
                    games[gid] = (g, b, p, s)
            k += 1
            d += dt.timedelta(days=step if k % 3 else 1)   # every third gap is a back-to-back

    add(20252026, dt.date(2025, 10, 8), 30, 2, 2025020000, dt.date(2026, 6, 1))
    add(20262027, dt.date(2026, 10, 1), 30, 2, 2026020000, t)
    return rows, games
