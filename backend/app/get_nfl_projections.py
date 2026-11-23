"""NFL projections pipeline: this week's game and player projections.

Run by .github/workflows/update_nfl_projections.yml (daily, plus Sunday
morning for the inactive/injury news). Each run refits everything from
nflverse 2021+ -- it takes a few minutes -- and writes to backend/data/nfl:

  nfl_projections.json         this week's games and players (the page)
  nfl_projection_log.parquet   every projection, last version before kickoff
  nfl_projection_plays.parquet every flagged play, last version before kickoff
  nfl_projection_record.json   both of the above graded once games are final

See nfl_sim.py for the simulation and nfl_projection_model.py for the rest.
Game lines get projections but are NOT flagged as bets: neither game model
beat the Vegas line in testing (2025-26), so the page says so.

Usage:  python backend/app/get_nfl_projections.py [--sims 4000] [--now 2026-11-10T12:00Z]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import nfl_sim as NS  # noqa: E402
import nfl_projection_model as M  # noqa: E402
import nfl_projection_edges as E  # noqa: E402
from props_config import DFS_BOOKS, SHARP_BOOKS, UNBETTABLE_BOOKS  # noqa: E402

OUT = HERE.parent / "data" / "nfl"
CACHE = HERE.parent / "data" / "nflverse_cache"
FIRST_SEASON = 2021
NV = "https://github.com/nflverse/nflverse-data/releases/download"
URLS = {
    "pbp": NV + "/pbp/play_by_play_{y}.parquet",
    "stats": NV + "/stats_player/stats_player_week_{y}.parquet",
    "snaps": NV + "/snap_counts/snap_counts_{y}.parquet",
}
GAMES_URL = NV + "/schedules/games.csv"
SKIP_STATUS = {"Out", "Doubtful", "IR", "Injured Reserve", "PUP", "Suspended"}
LOG_KEEP_SEASONS = 2
SHADOW_WEIGHTS = (0.0, 0.25)


def clean(o):
    """NaN isn't valid JSON (and FastAPI refuses it): None instead."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, np.generic):
        return clean(o.item())
    return o


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "sports-analytics"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def season_file(kind: str, y: int, current: int, cols=None) -> pd.DataFrame:
    """Past seasons are cached (nflverse rarely touches them); the current one
    is re-downloaded every run."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{kind}_{y}.parquet"
    if y == current or not path.exists():
        try:
            path.write_bytes(fetch(URLS[kind].format(y=y)))
        except Exception as e:                       # noqa: BLE001
            if not path.exists():
                print(f"  {kind} {y}: {e}")
                return pd.DataFrame()
            print(f"  {kind} {y}: download failed ({e}); using cached copy")
    return pd.read_parquet(path, columns=cols)


def kickoff_utc(g) -> pd.Timestamp:
    t = pd.Timestamp(f"{g.gameday} {g.gametime or '13:00'}").tz_localize("America/New_York")
    return t.tz_convert("UTC")


def this_week(G: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """The next week with games still to kick off -- only those games."""
    G = G.copy()
    G["kickoff"] = [kickoff_utc(g) for g in G.itertuples()]
    fut = G[(G.kickoff > now) & G.result.isna()]
    if fut.empty:
        return fut
    first = fut.sort_values("kickoff").iloc[0]
    return fut[(fut.season == first.season) & (fut.week == first.week)].sort_values("kickoff")


def load_injuries() -> pd.DataFrame:
    p = OUT / "nfl_injuries.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def candidates(PS: pd.DataFrame, U: pd.DataFrame, inj: pd.DataFrame, season: int) -> pd.DataFrame:
    """Skill players who've played for this team this season, in one of its
    last three games, and aren't ruled out."""
    cur = PS[(PS.season == season) & PS.position.isin(M.SKILL)]
    status = {}
    if not inj.empty and "gsis_id" in inj.columns:
        status = {r.gsis_id: (r.status, getattr(r, "detail", None)) for r in inj.itertuples() if r.gsis_id}
    rows = []
    for g in U.itertuples():
        for team, opp in ((g.home_team, g.away_team), (g.away_team, g.home_team)):
            t = cur[cur.team == team]
            last3 = sorted(t.week.unique())[-3:]
            pl = t[t.week.isin(last3)].sort_values("week").drop_duplicates("player_id", keep="last")
            for r in pl.itertuples():
                st, det = status.get(r.player_id, (None, None))
                if st in SKIP_STATUS:
                    continue
                rows.append({"player_id": r.player_id, "player_display_name": r.player_display_name,
                             "position": r.position, "team": team, "opponent_team": opp, "game_id": g.game_id,
                             "season": g.season, "week": g.week, "season_type": "POST" if g.game_type != "REG" else "REG",
                             "status": st, "injury": det, "headshot_url": getattr(r, "headshot_url", None)})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=4000)
    ap.add_argument("--now", default=None, help="pretend it's this UTC time (testing)")
    a = ap.parse_args()
    t0 = time.time()
    now = pd.Timestamp(a.now) if a.now else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    OUT.mkdir(parents=True, exist_ok=True)
    cal = json.loads((HERE / "nfl_projection_calibration.json").read_text())

    G = pd.read_csv(io.BytesIO(fetch(GAMES_URL)))
    G = G[G.season >= FIRST_SEASON].copy()
    U = this_week(G, now)
    if U.empty:
        print("no upcoming games -- nothing to project")
        return 0
    season, week = int(U.season.iloc[0]), int(U.week.iloc[0])
    print(f"projecting {season} week {week}: {len(U)} games")
    seasons = list(range(FIRST_SEASON, season + 1))

    P = pd.concat([season_file("pbp", y, season, M.PBP_COLS) for y in seasons], ignore_index=True)
    PS = pd.concat([season_file("stats", y, season) for y in seasons], ignore_index=True)
    SN = pd.concat([season_file("snaps", y, season) for y in seasons], ignore_index=True)
    G["gameday"] = pd.to_datetime(G.gameday)
    print(f"  data: {len(P):,} plays, {len(PS):,} player-games ({time.time() - t0:.0f}s)")

    # ---- simulation inputs
    P, S = M.prep_plays(P, G)
    league = M.fit_league(P, S)
    TS, tlg = M.sim_team_priors(S, G, U)
    L = NS.League(league, tlg.to_dict())
    pri = {(r["game_id"], r["team"]): r for r in TS[TS.game_id.isin(U.game_id)].to_dict("records")}

    # ---- ratings + market game model
    TP = M.rating_priors(P, G, U)
    GX = M.game_features(G, TP)
    gm = M.fit_game_model(GX[GX.result.notna()])
    GU = GX[GX.game_id.isin(U.game_id)].set_index("game_id")

    # ---- players
    inj = load_injuries()
    inj_status = ({r.gsis_id: (r.status, getattr(r, "detail", None)) for r in inj.itertuples() if r.gsis_id}
                  if not inj.empty and "gsis_id" in inj.columns else {})
    cand = candidates(PS, U, inj, season)
    X = M.player_features(PS, SN, G, TP, cand.drop(columns=["status", "injury", "headshot_url"]))
    models = M.train_direct(X, FIRST_SEASON + 1)
    XU = X[X._up == 1].copy()
    for st, (m, cols) in models.items():
        XU[f"d_{st}"] = m.predict(XU[cols].astype(float))
    XU = XU.drop(columns=["headshot_url"], errors="ignore").merge(cand[["player_id", "game_id", "status", "injury", "headshot_url"]], on=["player_id", "game_id"], how="left")
    SH = M.player_share_games(S, G, cand.rename(columns={"player_id": "pid"}))
    SHU = SH[(SH._up == 1) & (SH.n_prior >= 1)]
    print(f"  models fit; {len(XU)} players ({time.time() - t0:.0f}s)")

    sc = cal["sim"]
    games, players = [], []
    # context for the pick reasons (nfl_reasons.py): each team's normal
    # dropback rate this season, and what defenses allow by position
    cur = S[S.season == season]
    season_rate = cur.groupby("posteam").dropback.mean().to_dict()
    lg_rate = float(cur.dropback.mean()) if len(cur) else None
    hist = X[(X._up == 0) & (X.season == season)]
    opp_avg = {c: hist.groupby("position")[f"opp_pos_{c}"].mean().to_dict()
               for c in OPP_STATS if f"opp_pos_{c}" in hist.columns}
    sim_rates, qb_info = {}, {}
    # who's been throwing: each team's main QB over its last 5 games, and
    # every QB's yards per attempt this season (for "Wentz starting for Murray")
    qbp = PS[(PS.season == season) & (PS.position == "QB") & (PS.attempts.fillna(0) > 0)]
    ypa = (qbp.groupby("player_id").passing_yards.sum() / qbp.groupby("player_id").attempts.sum()).to_dict()
    qname = qbp.drop_duplicates("player_id").set_index("player_id").player_display_name.to_dict()
    usual_qb = {}
    for tm_, g_ in qbp.groupby("team"):
        last5 = sorted(g_.week.unique())[-5:]
        usual_qb[tm_] = g_[g_.week.isin(last5)].groupby("player_id").attempts.sum().idxmax()
    for g in U.itertuples():
        ph, pa = pri.get((g.game_id, g.home_team)), pri.get((g.game_id, g.away_team))
        if ph is None or pa is None:
            continue
        h = {"off": NS.team_params(ph, L.lg, "off"), "def": NS.team_params(ph, L.lg, "def")}
        aw = {"off": NS.team_params(pa, L.lg, "off"), "def": NS.team_params(pa, L.lg, "def")}
        rows, arrs = {}, []
        for tm in (g.home_team, g.away_team):
            r = SHU[(SHU.game_id == g.game_id) & (SHU.team == tm)].reset_index(drop=True)
            qbs = XU[(XU.game_id == g.game_id) & (XU.team == tm) & (XU.position == "QB")].sort_values("ew_pass_att", ascending=False)
            qb = qbs.player_id.iloc[0] if len(qbs) else None
            rows[tm] = (r, qb)
            u = usual_qb.get(tm)
            if qb is not None and u is not None and qb != u:
                qb_info[tm] = {"now": qname.get(qb, "backup"), "usual": qname.get(u, "starter"),
                               "now_ypa": _num(ypa.get(qb), 2), "usual_ypa": _num(ypa.get(u), 2),
                               "usual_status": (inj_status.get(u) or [None])[0]}
            arrs.append(M.player_arrays(r, qb) if len(r) else None)
        has_lines = pd.notna(g.spread_line) and pd.notna(g.total_line)
        use_pl = all(x is not None for x in arrs)
        pls = tuple(arrs) if use_pl else None
        tsp = (-g.spread_line, g.spread_line) if pd.notna(g.spread_line) else (0.0, 0.0)
        shift = [sc["yards_shift"], sc["yards_shift"]]
        if has_lines:
            # anchor each offense to its Vegas implied points: two short
            # pilot runs, each nudging the completion-yards knob
            imp = (M.implied_points(g.spread_line, g.total_line, True), M.implied_points(g.spread_line, g.total_line, False))
            for it in range(2):
                r0 = NS.simulate(L, h, aw, n=500, seed=5 + it, clock_scale=sc["clock_scale"], yards_shift=shift, players=pls, team_spread=tsp)
                got = (r0["pts_home"].mean(), r0["pts_away"].mean())
                shift = [float(np.clip(shift[i] + (imp[i] - got[i]) / sc["pts_per_yard"], -3, 6)) for i in (0, 1)]
        r = NS.simulate(L, h, aw, n=a.sims, seed=1, clock_scale=sc["clock_scale"], yards_shift=shift, players=pls, team_spread=tsp)
        for k, tm in (("home", g.home_team), ("away", g.away_team)):
            d_, r_ = float(r[f"drops_{k}"].mean()), float(r[f"runs_{k}"].mean())
            sim_rates[tm] = d_ / max(d_ + r_, 1e-9)

        # game: ratings + market model, and the sim's game flow
        gx = GU.loc[g.game_id] if g.game_id in GU.index else None
        a_margin = a_total = None
        if gx is not None and has_lines and gx[M.MARGIN_F + M.TOTAL_F].notna().all():
            a_margin = float(gm["margin"].predict(gx[M.MARGIN_F].to_frame().T.astype(float))[0])
            a_total = float(gm["total"].predict(gx[M.TOTAL_F].to_frame().T.astype(float))[0])
        margin = r["pts_home"] - r["pts_away"]
        side = {}
        for k, tm in (("home", g.home_team), ("away", g.away_team)):
            side[k] = {"team": tm, "sim_points": round(float(r[f"pts_{k}"].mean()), 1),
                       "plays": round(float(r[f"plays_{k}"].mean()), 1),
                       "dropbacks": round(float(r[f"drops_{k}"].mean()), 1),
                       "runs": round(float(r[f"runs_{k}"].mean()), 1),
                       "top_min": round(float(r[f"top_{k}"].mean()) / 60, 1),
                       "implied_points": None if not has_lines else round(imp[0 if k == "home" else 1], 1)}
        games.append({
            "game_id": g.game_id, "kickoff": g.kickoff.isoformat(), "home": g.home_team, "away": g.away_team,
            "spread_line": None if pd.isna(g.spread_line) else float(g.spread_line),
            "total_line": None if pd.isna(g.total_line) else float(g.total_line),
            "home_moneyline": None if pd.isna(g.home_moneyline) else float(g.home_moneyline),
            "away_moneyline": None if pd.isna(g.away_moneyline) else float(g.away_moneyline),
            "model_margin": None if a_margin is None else round(a_margin, 1),
            "model_total": None if a_total is None else round(a_total, 1),
            "model_home_win": None if a_margin is None else round(M.win_prob(a_margin, gm["sd"]), 3),
            "sim_home_win": round(float((margin > 0).mean() + 0.5 * (margin == 0).mean()), 3),
            "sim_margin_p10_p90": [float(np.percentile(margin, 10)), float(np.percentile(margin, 90))],
            "teams": side, "anchored": bool(has_lines),
            "roof": None if pd.isna(g.roof) else g.roof, "temp": None if pd.isna(g.temp) else float(g.temp),
            "wind": None if pd.isna(g.wind) else float(g.wind),
        })

        # players: direct model + simulation
        simd = {}
        if use_pl:
            for si, tm in ((0, g.home_team), (1, g.away_team)):
                R, qb = rows[tm]
                pl = r["players"][si]
                for i, pid in enumerate(R.pid):
                    simd[(tm, pid)] = {c: float(np.median(pl[c][:, i])) for c in ("rec", "rec_yds", "car", "rush_yds")}
                    simd[(tm, pid)]["tgt"] = float(pl["tgt"][:, i].mean())
                    simd[(tm, pid)]["car_mean"] = float(pl["car"][:, i].mean())
                    simd[(tm, pid)]["td"] = float(((pl["rec_td"][:, i] + pl["rush_td"][:, i]) > 0).mean())
                if qb is not None:
                    simd.setdefault((tm, qb), {})["pass_yds"] = float(np.median(pl["qb"]["pass_yds"]))
        for x in XU[XU.game_id == g.game_id].itertuples():
            sd_ = simd.get((x.team, x.player_id), {})
            proj = {}
            for st in ("rec", "rec_yds", "rush_att", "rush_yds", "pass_yds", "pass_att", "pass_cmp", "pass_tds"):
                pos_ok = x.position in M.SPEC[st][0]
                if not pos_ok or (M.SPEC[st][1] == "qb" and not (x.ew_pass_att >= 15)) or (M.SPEC[st][1] != "qb" and x.n_games < 2):
                    continue
                v = M.combine(st, x.position, getattr(x, f"d_{st}"), sd_.get(M.SIM_STAT.get(st, st)), cal)
                if v is not None:
                    proj[st] = round(v, 1)
            if "rush_yds" in proj or "rec_yds" in proj:
                # one number, so the parts always add up
                proj["rush_rec_yds"] = round(proj.get("rush_yds", 0.0) + proj.get("rec_yds", 0.0), 1)
            if x.n_games >= 2:
                proj["anytime_td"] = round(M.td_prob(float(x.d_any_td), sd_.get("td"), cal), 3)
            if not proj:
                continue
            players.append({
                "game_id": g.game_id, "player": x.player_display_name, "player_id": x.player_id,
                "team": x.team, "opponent": x.opponent_team, "position": x.position,
                "status": None if pd.isna(x.status) else x.status, "injury": None if pd.isna(x.injury) else x.injury,
                "headshot_url": None if pd.isna(x.headshot_url) else x.headshot_url,
                "sim_targets": round(sd_["tgt"], 1) if "tgt" in sd_ else None,
                "snap_pct": None if pd.isna(x.ew_offense_pct) else round(float(x.ew_offense_pct), 2),
                "why": {**_why(x, sd_, sim_rates, season_rate, opp_avg, games[-1]), "qb_change": qb_info.get(x.team)},
                "projection": proj,
            })
    # game-script shift: how far each team's simulated dropback rate sits from
    # its normal one, each against the league (sim this week / real this season)
    seas = [season_rate[t] for t in sim_rates if season_rate.get(t) is not None]
    if sim_rates and seas:
        ms, mr = float(np.mean(list(sim_rates.values()))), float(np.mean(seas))
        for p in players:
            w = p["why"]
            if w.get("pass_rate_sim") is not None and w.get("pass_rate_season") is not None:
                w["script_shift"] = _num((w["pass_rate_sim"] - ms) - (w["pass_rate_season"] - mr))
    print(f"  simulated {len(games)} games, {len(players)} player projections ({time.time() - t0:.0f}s)")

    # ---- edges at today's lines (the API recomputes these live)
    props_path = OUT / "NFL_Props.parquet"
    props = pd.read_parquet(props_path) if props_path.exists() else pd.DataFrame()
    excl = set(UNBETTABLE_BOOKS | SHARP_BOOKS | DFS_BOOKS)
    lines = E.main_lines(props, excl, E.MARKETS) if not props.empty else {}
    tds = E.td_prices(props, excl) if not props.empty else {}
    A = _actuals(PS).merge(PS[["game_id", "player_id", "season", "week"]], on=["game_id", "player_id"])
    A = A[A.player_id.isin({p["player_id"] for p in players})].sort_values(["season", "week"])
    rec_cols = [c for c in A.columns if c in ACTUAL or c == "rush_rec_yds"]
    recent = {pid: {c: [None if pd.isna(v) else float(v) for v in g[c].tail(E.HIST_GAMES)] for c in rec_cols}
              for pid, g in A.groupby("player_id")}
    for p in players:
        p["recent"] = {k: v for k, v in recent.get(p["player_id"], {}).items() if k in p["projection"]}
        p["lines"] = E.edges_for(p["player"], p["projection"], lines, tds, cal, p["position"], p["recent"])
    top = {(b["player"], b["market"]) for b in E.best_bets(players, "bet", E.TOP_BETS)}
    # Weight test (tracking only): what the rule would flag if our number
    # leaned less on the line -- straight model and 25% line -- for every
    # market. On 2026 weeks 3-9 those looked better for some yardage markets
    # but the sample is thin; graded beside the live weights to decide.
    # Also the live weights WITHOUT the 2-point over nudge (Nov 13 2026), to
    # see whether the nudge earns its keep.
    shadow, nudge = [], E.OVER_NUDGE
    variants = [(f"line {int(w * 100)}%", {**cal, "market_weight": {k: w for k in (cal.get("market_weight") or {})}}, nudge)
                for w in SHADOW_WEIGHTS] + [("no nudge", cal, 0.0)]
    try:
        for name, cw, nd in variants:
            E.OVER_NUDGE = nd
            for p in players:
                for m, e in E.edges_for(p["player"], p["projection"], lines, {}, cw, p["position"], p["recent"]).items():
                    if e.get("side") and e.get("price") is not None:
                        shadow.append({"season": season, "week": week, "game_id": p["game_id"],
                                       "player_id": p["player_id"], "player": p["player"], "team": p["team"],
                                       "market": m, "side": e["side"], "variant": name, "tier": e.get("tier"),
                                       "line": e.get("line"), "price": e["price"], "ev": e["ev"],
                                       "projection": e["projection"]})
    finally:
        E.OVER_NUDGE = nudge
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = {"generated_at": stamp, "season": season, "week": week, "games": games, "players": players,
           "calibration": {k: cal.get(k) for k in ("residuals", "td_map", "accuracy", "fit_on", "market_weight")},
           "model": {"sims": a.sims, "game_model_sd": round(gm["sd"], 2), "first_season": FIRST_SEASON}}
    (OUT / "nfl_projections.json").write_text(json.dumps(clean(out), separators=(",", ":"), default=str, allow_nan=False))

    # ---- logs: the latest run before kickoff wins; started games are frozen
    kick = {g["game_id"]: g["kickoff"] for g in games}
    log = pd.DataFrame([{"season": season, "week": week, "game_id": p["game_id"], "kickoff": kick[p["game_id"]],
                         "player_id": p["player_id"], "player": p["player"], "team": p["team"], "position": p["position"],
                         **{f"proj_{k}": v for k, v in p["projection"].items()}, "logged_at": stamp} for p in players])
    plays = pd.DataFrame([{"season": season, "week": week, "game_id": p["game_id"], "kickoff": kick[p["game_id"]],
                           "player_id": p["player_id"], "player": p["player"], "team": p["team"], "market": m,
                           "side": e["side"], "tier": e["tier"], "line": e.get("line"), "price": e["price"], "book": e["book"],
                           "projection": e["projection"], "ev": e["ev"],
                           "prob": e["prob_over"] if e["side"] in ("over", "yes") else e.get("prob_under"),
                           # tracking only (not on the page): does the top-15 sort pick winners?
                           "top": (p["player"], m) in top, "hist_rate": e.get("hist_rate"),
                           "prob_edge": e.get("prob_edge"), "books": e.get("books"),
                           "logged_at": stamp}
                          for p in players for m, e in p["lines"].items() if e.get("side") and e.get("price") is not None])
    kick_of = lambda df: df.assign(kickoff=df.game_id.map(kick)) if len(df) else df  # noqa: E731
    for name, new in (("nfl_projection_log.parquet", log), ("nfl_projection_plays.parquet", plays),
                      ("nfl_projection_plays_shadow.parquet", kick_of(pd.DataFrame(shadow)))):
        path = OUT / name
        if path.exists():
            old = pd.read_parquet(path)
            old = old[~old.game_id.isin(set(new.game_id) if len(new) else set())]
            old = old[old.season >= season - LOG_KEEP_SEASONS + 1]
            new = pd.concat([old, new], ignore_index=True)
        if len(new):
            new.to_parquet(path, index=False)
    print(f"  logged {len(log)} projections, {len(plays)} plays")

    # ---- grade everything that's final
    rec = grade(PS)
    (OUT / "nfl_projection_record.json").write_text(json.dumps(clean(rec), default=str, allow_nan=False))
    if rec.get("plays"):
        print(f"  record: {rec['plays']}")
    print(f"done in {time.time() - t0:.0f}s")
    return 0


OPP_STATS = ("rec", "rec_yds", "rush_yds", "pass_yds")


def _num(v, nd=3):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if np.isfinite(v) else None


def _why(x, sd_: dict, sim_rates: dict, season_rate: dict, opp_avg: dict, game: dict) -> dict:
    """Raw numbers the pick reasons are written from (nfl_reasons.py)."""
    tm = x.team
    return {
        "team_spread": _num(getattr(x, "team_spread", None), 1),       # negative = favored
        "implied_pts": _num(getattr(x, "implied_pts", None), 1),
        "total": game.get("total_line"),
        "pass_rate_sim": _num(sim_rates.get(tm)), "pass_rate_season": _num(season_rate.get(tm)),
        "script_shift": None,                         # filled once every game is simulated
        "opp_rel": {c: _num(getattr(x, f"opp_pos_{c}", None) / opp_avg[c][x.position])
                    for c in OPP_STATS if c in opp_avg and opp_avg[c].get(x.position)
                    and _num(getattr(x, f"opp_pos_{c}", None)) is not None},
        "sim_targets": _num(sd_.get("tgt"), 1), "ew_targets": _num(getattr(x, "ew_targets", None), 1),
        "sim_carries": _num(sd_.get("car_mean"), 1), "ew_carries": _num(getattr(x, "ew_rush_att", None), 1),
        "tm_out_tgt_share": _num(getattr(x, "tm_out_tgt_share", None)),
        "tm_out_carries": _num(getattr(x, "tm_out_carries", None), 1),
        "wind": _num(getattr(x, "wind", None), 0), "dome": bool(getattr(x, "dome", 0) == 1),
    }


ACTUAL = {"rec": "receptions", "rec_yds": "receiving_yards", "rush_att": "carries", "rush_yds": "rushing_yards",
          "pass_yds": "passing_yards", "pass_att": "attempts", "pass_cmp": "completions", "pass_tds": "passing_tds"}


def _actuals(PS: pd.DataFrame) -> pd.DataFrame:
    A = PS[["game_id", "player_id"] + list(ACTUAL.values()) + ["rushing_tds", "receiving_tds"]].copy()
    A = A.rename(columns={v: k for k, v in ACTUAL.items()})
    A["rush_rec_yds"] = A.rush_yds + A.rec_yds
    A["anytime_td"] = ((A.rushing_tds.fillna(0) + A.receiving_tds.fillna(0)) > 0).astype(float)
    return A.drop(columns=["rushing_tds", "receiving_tds"])


def _profit(price: float) -> float:
    return price / 100.0 if price > 0 else 100.0 / abs(price)


def grade(PS: pd.DataFrame) -> dict:
    out = {"accuracy": None, "plays": None, "watch": None, "by_market": [], "recent": []}
    A = _actuals(PS)
    lp, pp = OUT / "nfl_projection_log.parquet", OUT / "nfl_projection_plays.parquet"
    if lp.exists():
        j = pd.read_parquet(lp).merge(A, on=["game_id", "player_id"], how="inner")
        if len(j):
            mae = {}
            for st in list(ACTUAL) + ["rush_rec_yds"]:
                c = f"proj_{st}"
                if c in j.columns:
                    d = j.dropna(subset=[c, st])
                    if len(d):
                        mae[st] = {"mae": round(float((d[c] - d[st]).abs().mean()), 2), "n": int(len(d))}
            out["accuracy"] = {"player_games": int(len(j)), "weeks": int(j[["season", "week"]].drop_duplicates().shape[0]),
                               "mae": mae}
    if pp.exists():
        pl = pd.read_parquet(pp).merge(A, on=["game_id", "player_id"], how="inner")
        graded = []
        for r in pl.to_dict("records"):
            st = "anytime_td" if r["market"] == "anytime_td" else E.MARKETS[r["market"]]
            v = r.get(st)
            if v is None or pd.isna(v):
                continue
            if r["market"] == "anytime_td":
                won, push = v > 0, False
            else:
                push = v == r["line"]
                won = (v > r["line"]) == (r["side"] == "over")
            u = 0.0 if push else (_profit(r["price"]) if won else -1.0)
            graded.append({"season": r["season"], "week": r["week"], "player": r["player"], "team": r["team"],
                           "tier": r.get("tier") or "watch",
                           "market": r["market"], "label": E.LABELS[r["market"]], "side": r["side"], "line": r["line"],
                           "price": r["price"], "book": r["book"], "projection": r["projection"], "result": float(v),
                           "outcome": "push" if push else ("win" if won else "loss"), "units": round(u, 3),
                           "top": r.get("top"), "hist_rate": r.get("hist_rate"), "ev": r.get("ev"),
                           "books": r.get("books")})

        def summ(rows):
            if not rows:
                return None
            dec = [g for g in rows if g["outcome"] != "push"]
            w = sum(g["outcome"] == "win" for g in rows)
            return {"plays": len(rows), "wins": w, "losses": sum(g["outcome"] == "loss" for g in rows),
                    "win_pct": round(100 * w / len(dec), 1) if dec else None,
                    "units": round(sum(g["units"] for g in rows), 2),
                    "roi_pct": round(100 * sum(g["units"] for g in rows) / len(rows), 1)}
        out["plays"] = summ([g for g in graded if g["tier"] == "bet"])
        out["watch"] = summ([g for g in graded if g["tier"] != "bet"])
        out["by_market"] = [{"market": m, "label": E.LABELS[m], **summ([g for g in graded if g["market"] == m])}
                            for m in sorted({g["market"] for g in graded})]
        out["recent"] = sorted(graded, key=lambda g: (g["season"], g["week"]), reverse=True)[:30]
        out["tracking"] = tracking(graded, summ)
        sp = OUT / "nfl_projection_plays_shadow.parquet"
        if sp.exists():
            sh = pd.read_parquet(sp).merge(A, on=["game_id", "player_id"], how="inner")
            rows = []
            for r in sh.to_dict("records"):
                v = r.get(E.MARKETS.get(r["market"], ""))
                if v is None or pd.isna(v):
                    continue
                push, won = v == r["line"], (v > r["line"]) == (r["side"] == "over")
                rows.append({"variant": r.get("variant"), "market": r["market"], "side": r["side"], "tier": r.get("tier"),
                             "outcome": "push" if push else ("win" if won else "loss"),
                             "units": 0.0 if push else (_profit(r["price"]) if won else -1.0)})
            # the live rule, same markets, for the side-by-side
            allw = rows + [{**g, "variant": "live"} for g in graded if g["market"] != "anytime_td"]
            out["tracking"]["variants"] = {
                v: {"bets": summ([g for g in allw if g["variant"] == v and g["tier"] == "bet"]),
                    "overs_share": round(sum(g["side"] == "over" for g in allw if g["variant"] == v)
                                         / max(1, sum(g["variant"] == v for g in allw)), 3)}
                for v in sorted({g["variant"] for g in allw}, key=str)}
            out["tracking"]["variant_market_side"] = {
                f"{v} | {m} {sd}": summ([g for g in allw if g["variant"] == v and g["market"] == m and g["side"] == sd])
                for v, m, sd in sorted({(g["variant"], g["market"], g["side"]) for g in allw}, key=str)}
    return out


def tracking(graded: list, summ) -> dict:
    """Behind-the-scenes cuts of the bets (not shown on the page yet): the
    top-15 the page shows vs the rest, the history signal, edge size, side and
    market. Plays logged before Nov 13 2026 have no signals ('unknown')."""
    bets = [g for g in graded if g["tier"] == "bet"]
    nan = lambda v: v is None or (isinstance(v, float) and not np.isfinite(v))  # noqa: E731

    def by(fn):
        keys = sorted({fn(g) for g in bets}, key=str)
        return {str(k): summ([g for g in bets if fn(g) == k]) for k in keys}

    def ev_band(g):
        ev = g.get("ev")
        if nan(ev):
            return "unknown"
        return "5-12%" if ev < 0.12 else "12-20%" if ev < 0.20 else "20%+"
    return {
        "top15": by(lambda g: "unknown" if nan(g.get("top")) else ("top15" if g["top"] else "rest")),
        "history": by(lambda g: "unknown" if nan(g.get("hist_rate")) else
                      ("5+ of 8" if g["hist_rate"] >= E.HIST_GOOD else "under 5 of 8")),
        "ev": by(ev_band),
        "side": by(lambda g: g["side"]),
        "price": by(lambda g: "unknown" if nan(g.get("price")) else "-121 or shorter" if g["price"] <= -121
                    else "-120 to -100" if g["price"] <= -100 else "+101 to +150" if g["price"] <= 150 else "+151 and up"),
        "market_side": {f"{m} {sd}": summ([g for g in graded if g["market"] == m and g["side"] == sd])
                        for m, sd in sorted({(g["market"], g["side"]) for g in graded})},
    }


if __name__ == "__main__":
    sys.exit(main())
