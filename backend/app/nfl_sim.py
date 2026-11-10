"""Play-by-play NFL game simulation.

Every game is played out N times, one snap at a time, with the score, clock,
field position, down and distance tracked in each copy. What comes out is a
distribution -- of the score, the winner, each team's plays, time of
possession and pass/run split, and (with the player layer) every player's
stats -- rather than an average.

What drives each snap (fit on 2021-24 play-by-play, see sim_fit in the
pipeline):

  PLAY CALL  P(dropback) from down, distance, field position, score
             margin, time left and two-minute situations (a logistic fit on
             ~130k plays), shifted by the offense's pass rate over expected
             -- so a team that's behind throws more, a team that's ahead
             runs, and each team keeps its own lean.
  CLOCK      Seconds off the clock per snap, drawn from what actually
             happened in that situation: ~38 s after a run or completion in
             normal play, ~5 s after an incompletion, far less in the two-
             minute drill or when the trailing team is using timeouts. Each
             offense's own tempo scales the normal-situation draw. Time of
             possession and plays per game come out of this, not out of an
             average.
  RESULT     Sack / scramble / interception / completion / incompletion
             rates and yards on runs and completions: league distributions
             shifted by this offense and this defense.
  4TH DOWN   Go / field goal / punt from what teams actually do at that
             field position and distance, with a late-and-trailing switch.
  KICKS      Field-goal make chance by distance; punt net and kickoff
             starting spot from recent seasons.

Vectorised over the N copies, so a game takes well under a second.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

HOME, AWAY = 0, 1


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


class League:
    def __init__(self, spec: dict, team_league: dict):
        self.s = spec
        self.lg = team_league
        self.call_coef = np.asarray(spec["play_call"]["coef"])
        self.call_b = spec["play_call"]["intercept"]
        self.clock = {k: np.asarray(v) for k, v in spec["clock"].items()}
        self.yards = {k: np.asarray(v) for k, v in spec["yards"].items()}
        self.punt = np.asarray(spec["punt_net"])
        self.ko = np.asarray(spec.get("kickoff_start_dist") or [spec["kickoff_start_ydl100"]])
        self.fourth = spec["fourth"]
        # lookup arrays [field-position bin, distance bin, late-and-trailing]
        self.p_go = np.zeros((9, 4, 2))
        self.p_fg = np.zeros((9, 4, 2))
        for yb in range(9):
            for db in range(4):
                for lt in range(2):
                    t = self.fourth.get(f"{yb}|{db}|{lt}") or self.fourth.get(f"{yb}|{db}|0")
                    if not t:   # unseen combination: kick if in range, else punt
                        t = {"fg": 1.0} if yb <= 4 else {"punt": 1.0}
                    self.p_go[yb, db, lt] = t.get("go", 0.0)
                    self.p_fg[yb, db, lt] = t.get("fg", 0.0)
        self.fg = spec["fg"]
        self.rates = spec["rates"]


def _call_features(down, togo, ydl, sd, gsr, two_min, spread=None):
    """spread: the offense's pregame point spread (negative = favored). With
    it, an underdog runs a little more than the score and clock alone say --
    teams play to the script they expect, not just the scoreboard."""
    sdn = np.clip(sd, -21, 21) / 21
    tfrac = gsr / 3600
    cols = [down == 1, down == 2, down == 3, np.log1p(togo), ydl / 100, sdn, tfrac, sdn * (1 - tfrac),
            two_min, two_min * (sd < 0), ydl <= 10]
    if spread is not None:
        spn = np.clip(spread, -14, 14) / 14
        cols += [spn, spn * tfrac]
    return np.stack(cols, axis=1).astype(float)


def _combine(off, deff, lg):
    """Rate for this offense vs this defense, relative to league (log5-style)."""
    return np.clip(lg * (off / lg) * (deff / lg), 1e-4, 0.95)


def team_params(pr: dict, lg: dict, side: str) -> dict:
    """Pull one team's prior ratings (dict of pr_off_* / pr_def_*) into the
    numbers the engine reads, filling gaps with league average."""
    g = lambda k: pr.get(k) if pr.get(k) is not None and np.isfinite(pr.get(k)) else lg[k.replace("pr_", "")]  # noqa: E731
    return {k: float(g(f"pr_{side}_{k}")) for k in ("proe", "sack", "scramble", "int", "cmp", "ypcmp", "ypc", "pace")}


PROE_OFF_W = 1.0       # how much of the offense's own pass lean carries over
PROE_DEF_W = 0.5       # ...and of the lean opponents have shown against this defense
PENALTY_OFF = 0.057      # per snap, 2024: offense flagged, ~7 yards, down replayed
PENALTY_DEF = 0.037      # defense flagged, ~9.5 yards, 76% an automatic first down


def simulate(league: League, home: dict, away: dict, n: int = 4000, seed: int = 0,
             home_edge_pts: float = 0.0, player_layer=None,
             clock_scale: float = 1.0, yards_shift=0.0, players=None,
             team_spread=(0.0, 0.0)) -> Dict[str, np.ndarray]:
    """home/away: {'off': team_params(..,'off'), 'def': team_params(..,'def')}.
    yards_shift: one number, or [home, away] -- how the run is anchored to
    each team's Vegas implied points.
    players: optional (home_players, away_players) from player_arrays();
    every pass then has a target and every run a ball carrier, chosen by that
    player's share IN THE CURRENT SITUATION (trailing / close / leading /
    red zone), and per-player stats are returned under "players".
    Returns per-copy arrays: points, plays, dropbacks, runs, top (seconds),
    pass_yds, rush_yds for each side."""
    rng = np.random.default_rng(seed)
    L, lg, R = league, league.lg, league.rates
    teams = (home, away)

    # matchup-specific rates, [side] = when that side has the ball
    def m(side, key, lgkey):
        o, d = teams[side]["off"], teams[1 - side]["def"]
        return _combine(o[key], d[key], lg[lgkey])
    sack = np.array([m(s, "sack", "off_sack") for s in (0, 1)])
    scram = np.array([m(s, "scramble", "off_scramble") for s in (0, 1)])
    intr = np.array([m(s, "int", "off_int") for s in (0, 1)])
    cmp_ = np.array([np.clip(teams[s]["off"]["cmp"] + teams[1 - s]["def"]["cmp"] - lg["off_cmp"], 0.4, 0.85) for s in (0, 1)])
    shift_cmp = np.array([(teams[s]["off"]["ypcmp"] - lg["off_ypcmp"]) + (teams[1 - s]["def"]["ypcmp"] - lg["def_ypcmp"]) for s in (0, 1)])
    shift_run = np.array([(teams[s]["off"]["ypc"] - lg["off_ypc"]) + (teams[1 - s]["def"]["ypc"] - lg["def_ypc"]) for s in (0, 1)])
    # pass rate over expected is in percentage points of dropback rate;
    # ~0.24 = p(1-p) at a 60% pass rate turns it into a log-odds shift
    proe = np.array([(PROE_OFF_W * (teams[s]["off"]["proe"] - lg["off_proe"]) + PROE_DEF_W * (teams[1 - s]["def"]["proe"] - lg["def_proe"])) / 100 / 0.24
                     for s in (0, 1)])
    pace = np.array([teams[s]["off"]["pace"] / lg["off_pace"] for s in (0, 1)])

    ys = np.broadcast_to(np.asarray(yards_shift, float), (2,)).copy()
    PL = None
    if players is not None:
        PL = []
        for side in (0, 1):
            pa = players[side]
            k = pa["tgt"].shape[1]
            PL.append({**pa, "cum_tgt": np.cumsum(pa["tgt"], axis=1), "cum_car": np.cumsum(pa["car"], axis=1),
                       "rec": {c: np.zeros((n, k)) for c in ("tgt", "rec", "rec_yds", "rec_td", "car", "rush_yds", "rush_td")}})
        qb_stats = {c: np.zeros((n, 2)) for c in ("att", "cmp", "pass_yds", "pass_td", "int", "scr", "scr_yds")}

    poss = rng.integers(0, 2, n)            # who receives the opening kickoff
    first_recv = poss.copy()
    ydl = L.ko[rng.integers(0, len(L.ko), n)].astype(float)
    down = np.ones(n, int)
    togo = np.full(n, 10.0)
    gsr = np.full(n, 3600.0)
    half_done = np.zeros(n, bool)
    pts = np.zeros((n, 2))
    plays = np.zeros((n, 2))
    drops = np.zeros((n, 2))
    runs = np.zeros((n, 2))
    runs1 = np.zeros((n, 2))     # first half only
    plays1 = np.zeros((n, 2))
    top = np.zeros((n, 2))
    pyds = np.zeros((n, 2))
    ryds = np.zeros((n, 2))
    ar = np.arange(n)

    def new_possession(mask, new_ydl):
        poss[mask] = 1 - poss[mask]
        ydl[mask] = np.clip(new_ydl[mask] if np.ndim(new_ydl) else new_ydl, 1, 99)
        down[mask] = 1
        togo[mask] = np.minimum(10, ydl[mask])

    def kickoff(mask):
        k = L.ko[rng.integers(0, len(L.ko), n)].astype(float)
        new_possession(mask, k)

    def draw(table, u):
        return np.interp(u, np.linspace(0, 1, len(table)), table)

    for _ in range(400):
        live = gsr > 0
        if not live.any():
            break
        # halftime: the team that didn't get the opening kick receives
        ht = live & ~half_done & (gsr <= 1800)
        if ht.any():
            poss[ht] = 1 - first_recv[ht]
            ydl[ht] = L.ko[rng.integers(0, len(L.ko), ht.sum())]
            down[ht] = 1
            togo[ht] = 10
            half_done |= ht
        p = poss
        sd = pts[ar, p] - pts[ar, 1 - p]
        hsr = np.where(gsr > 1800, gsr - 1800, gsr)
        two_min = (hsr <= 120).astype(float)
        late = gsr <= 300
        sit = np.where(two_min == 1, "two_min", np.where(late & (sd > 0), "late_lead", np.where(late & (sd < 0), "late_trail", "normal")))

        # ---- 4th down: go / field goal / punt, all copies at once
        fourth = live & (down == 4)
        go = np.zeros(n, bool)
        if fourth.any():
            yb = np.clip(np.digitize(ydl, [5, 10, 20, 30, 37, 45, 55, 65]), 0, 8)
            db = np.clip(np.digitize(togo, [1, 3, 6], right=True), 0, 3)
            lt = ((gsr <= 600) & (sd < 0)).astype(int)
            u = rng.random(n)
            pg, pf = L.p_go[yb, db, lt], L.p_fg[yb, db, lt]
            go = fourth & (u < pg)
            kick = fourth & ~go & (u < pg + pf)
            punt = fourth & ~go & ~kick
            if kick.any():
                made = kick & (rng.random(n) < _sigmoid(L.fg["intercept"] + L.fg["coef"] * (ydl + 17)))
                pts[ar[made], p[made]] += 3
                miss = kick & ~made
                gsr = np.where(kick, gsr - 5, gsr)
                if made.any():
                    gsr = np.where(made, gsr - 5 * clock_scale, gsr)
                    kickoff(made)
                if miss.any():
                    new_possession(miss, 100 - ydl - 7)
            if punt.any():
                land = ydl - draw(L.punt, rng.random(n))
                nxt = np.where(land <= 0, 80.0, 100 - land)
                gsr = np.where(punt, gsr - 6, gsr)
                new_possession(punt, nxt)
        snap = live & ((down < 4) | go)
        if not snap.any():
            continue

        # ---- penalties instead of a play (no stats, a few seconds off)
        up = rng.random(n)
        pen_o = snap & (up < PENALTY_OFF)
        pen_d = snap & ~pen_o & (up < PENALTY_OFF + PENALTY_DEF)
        if pen_o.any() or pen_d.any():
            ydl = np.where(pen_o, np.minimum(ydl + 7, 99), ydl)
            togo = np.where(pen_o, togo + 7, togo)
            auto = pen_d & (rng.random(n) < 0.76)
            ydl = np.where(pen_d, np.maximum(ydl - 9.5, 1), ydl)
            togo = np.where(auto, np.minimum(10, ydl), np.where(pen_d, np.maximum(togo - 9.5, 1), togo))
            down = np.where(auto, 1, down)
            gsr = np.where(pen_o | pen_d, gsr - 6 * clock_scale, gsr)
            snap = snap & ~pen_o & ~pen_d
            if not snap.any():
                continue

        # ---- play call
        spr = np.asarray(team_spread, float)[p] if len(L.call_coef) == 13 else None
        X = _call_features(down, togo, ydl, sd, gsr, two_min, spr)
        pdrop = _sigmoid(L.call_b + X @ L.call_coef + proe[p])
        is_pass = (rng.random(n) < pdrop) & snap
        is_run = snap & ~is_pass

        # ---- result
        u = rng.random(n)
        sk = is_pass & (u < sack[p])
        sc = is_pass & ~sk & (u < sack[p] + scram[p])
        att = is_pass & ~sk & ~sc
        u2 = rng.random(n)
        it = att & (u2 < intr[p])
        tgt_j = np.full(n, -1)
        car_j = np.full(n, -1)
        catch_m = np.ones(n)
        ypr_s = np.zeros(n)
        ypc_s = np.zeros(n)
        if PL is not None:
            state = np.where(ydl <= 20, 3, np.where(sd <= -4, 0, np.where(sd >= 4, 2, 1)))
            for side in (0, 1):
                pa = PL[side]
                for st in range(4):
                    mt = att & ~it & (p == side) & (state == st)
                    if mt.any():
                        j = (rng.random(mt.sum())[:, None] > pa["cum_tgt"][st][None, :]).sum(1)
                        j = np.minimum(j, pa["tgt"].shape[1] - 1)
                        tgt_j[mt] = j
                        catch_m[mt] = pa["catch"][j]
                        ypr_s[mt] = pa["ypr"][j]
                    mr = is_run & (p == side) & (state == st)
                    if mr.any():
                        j = (rng.random(mr.sum())[:, None] > pa["cum_car"][st][None, :]).sum(1)
                        j = np.minimum(j, pa["car"].shape[1] - 1)
                        car_j[mr] = j
                        ypc_s[mr] = pa["ypc"][j]
        pc = np.clip(cmp_[p] * catch_m, 0.05, 0.95)
        cm = att & ~it & (rng.random(n) < pc)
        yds = np.zeros(n)
        uy = rng.random(n)
        # the scoring knob (ys) moves completions only -- applying it to runs
        # too inflated team rushing by ~35 yards a game
        yds[is_run] = draw(L.yards["run"], uy[is_run]) + shift_run[p][is_run] + ypc_s[is_run]
        yds[cm] = draw(L.yards["cmp"], uy[cm]) + shift_cmp[p][cm] + ys[p][cm] + ypr_s[cm]
        yds[sk] = draw(L.yards["sack"], uy[sk])
        yds[sc] = draw(L.yards["scramble"], uy[sc])
        yds = np.round(yds)
        fum = (is_run | cm) & (rng.random(n) < R["fumble_lost"])

        plays[ar[snap], p[snap]] += 1
        drops[ar[is_pass], p[is_pass]] += 1
        runs[ar[is_run], p[is_run]] += 1
        h1 = gsr > 1800
        runs1[ar[is_run & h1], p[is_run & h1]] += 1
        plays1[ar[snap & h1], p[snap & h1]] += 1
        pyds[ar[cm], p[cm]] += yds[cm]
        pyds[ar[sk], p[sk]] += yds[sk]
        ryds[ar[is_run | sc], p[is_run | sc]] += yds[is_run | sc]
        if PL is not None:
            for side in (0, 1):
                rec = PL[side]["rec"]
                mt = att & ~it & (p == side) & (tgt_j >= 0)
                rows, cols = ar[mt], tgt_j[mt]
                np.add.at(rec["tgt"], (rows, cols), 1)
                mc = cm & (p == side) & (tgt_j >= 0)
                np.add.at(rec["rec"], (ar[mc], tgt_j[mc]), 1)
                np.add.at(rec["rec_yds"], (ar[mc], tgt_j[mc]), yds[mc])
                mr = is_run & (p == side) & (car_j >= 0)
                np.add.at(rec["car"], (ar[mr], car_j[mr]), 1)
                np.add.at(rec["rush_yds"], (ar[mr], car_j[mr]), yds[mr])
                ps_ = (p == side)
                qb_stats["att"][ar[att & ps_], side] += 1
                qb_stats["cmp"][ar[cm & ps_], side] += 1
                qb_stats["pass_yds"][ar[cm & ps_], side] += yds[cm & ps_]
                qb_stats["int"][ar[it & ps_], side] += 1
                qb_stats["scr"][ar[sc & ps_], side] += 1
                qb_stats["scr_yds"][ar[sc & ps_], side] += yds[sc & ps_]

        # clock
        stop = (att & ~cm) | it
        el = np.zeros(n)
        for s_name in ("two_min", "late_lead", "late_trail", "normal"):
            for clk in ("run", "stop"):
                msk = snap & (sit == s_name) & ((stop) if clk == "stop" else ~stop)
                if msk.any():
                    tab = L.clock.get(f"{s_name}|{clk}")
                    e = draw(tab, rng.random(msk.sum()))
                    if s_name == "normal" and clk == "run":
                        e = e * pace[p[msk]]
                    el[msk] = e * clock_scale
        top[ar[snap], p[snap]] += np.minimum(el[snap], gsr[snap])
        gsr = np.where(snap, gsr - el, gsr)

        # ---- advance
        gained = snap & ~it & ~fum
        ydl = np.where(gained, ydl - yds, ydl)
        td = gained & (ydl <= 0)
        if td.any() and PL is not None:
            for side in (0, 1):
                rec = PL[side]["rec"]
                t1 = td & cm & (p == side) & (tgt_j >= 0)
                np.add.at(rec["rec_td"], (ar[t1], tgt_j[t1]), 1)
                qb_stats["pass_td"][ar[td & cm & (p == side)], side] += 1
                t2 = td & is_run & (p == side) & (car_j >= 0)
                np.add.at(rec["rush_td"], (ar[t2], car_j[t2]), 1)
        if td.any():
            pts[ar[td], p[td]] += 6 + (rng.random(td.sum()) < R["xp"])
            gsr = np.where(td, gsr - 10 * clock_scale, gsr)
            kickoff(td)
        safety = gained & ~td & (ydl >= 100)
        if safety.any():
            pts[ar[safety], 1 - p[safety]] += 2
            new_possession(safety, np.array([65.0] * n))
        to = (it | fum) & snap
        if to.any():
            spot = np.where(it, ydl - 10, ydl - yds)
            new_possession(to, 100 - spot)
        cont = gained & ~td & ~safety
        first = cont & (yds >= togo)
        down = np.where(first, 1, np.where(cont, down + 1, down))
        togo = np.where(first, np.minimum(10, ydl), np.where(cont, togo - yds, togo))
        # failed 4th-down try: turnover on downs
        tod = cont & ~first & (down > 4)
        if tod.any():
            new_possession(tod, 100 - ydl)

    # overtime, simplified: tied games go to the side that scores first ~= the
    # stronger offense a little more often; worth 3 (or 6) points
    tie = pts[:, 0] == pts[:, 1]
    if tie.any():
        edge = 0.5 + 0.02 * np.sign(home_edge_pts)
        hw = rng.random(tie.sum()) < edge
        pts[np.where(tie)[0], np.where(hw, 0, 1)] += 3
    out_players = None
    if PL is not None:
        out_players = []
        for side in (0, 1):
            rec = PL[side]["rec"]
            q = PL[side].get("qb_col", -1)
            d = {c: v for c, v in rec.items()}
            # the QB's own rushing: scrambles plus his designed runs
            d["qb"] = {c: v[:, side] for c, v in qb_stats.items()}
            if q is not None and q >= 0:
                d["qb"]["rush_yds_total"] = d["qb"]["scr_yds"] + rec["rush_yds"][:, q]
            out_players.append(d)
    return {"players": out_players, "pts_home": pts[:, 0], "pts_away": pts[:, 1], "plays_home": plays[:, 0], "plays_away": plays[:, 1],
            "drops_home": drops[:, 0], "drops_away": drops[:, 1], "runs_home": runs[:, 0], "runs_away": runs[:, 1],
            "runs1_home": runs1[:, 0], "runs1_away": runs1[:, 1], "plays1_home": plays1[:, 0], "plays1_away": plays1[:, 1],
            "top_home": top[:, 0], "top_away": top[:, 1], "pyds_home": pyds[:, 0], "pyds_away": pyds[:, 1],
            "ryds_home": ryds[:, 0], "ryds_away": ryds[:, 1]}
