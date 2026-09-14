"""Predict hit probability for a slate of games.

Lineup sources, in order of preference:
  1. --lineups your_file.csv     your own confirmed lineup data
  2. Confirmed lineups from the MLB Stats API (posted ~1-4h before game)
  3. --project                   fall back to last game's lineup (off by default)

Teams with no lineup from any allowed source are skipped with a warning.

Lineup CSV format (one row per batter):
  team,batter_id[,batter_name][,slot]
  team = MLB team name as it appears on the schedule (e.g. "Milwaukee Brewers";
  case-insensitive substring match is fine, e.g. "brewers"). batter_id = MLBAM id.

Usage:
  python src/predict_upcoming.py 2026-07-10
  The day's slate (starters known/missing, lineup status) is written to
  output/slate_{date}.csv automatically on the first run of each day and then
  REUSED on later runs -- fill in missing pitcher_id values (MLBAM ids) there
  and re-run; they're picked up automatically. Flags:
  --refresh-slate   rewrite the slate from the API (discards your edits)
  --template        write the slate and stop (no predictions)
  --starters f.csv  use a different starters file than the day's slate
  python src/predict_upcoming.py 2026-07-10 --lineups lineups.csv
  python src/predict_upcoming.py 2026-07-10 --project
  python src/predict_upcoming.py 2026-07-10 --explain pena     SHAP breakdown of
        why the model scored matching batter(s) the way it did (name substring
        or MLBAM id)
Output: output/predictions_{date}.csv

Finding MLBAM pitcher ids: the number in a Baseball Savant player URL, or
  python -c "from pybaseball import playerid_lookup; print(playerid_lookup('skenes','paul'))"
"""
import json
import sys
from datetime import date as date_cls
from pathlib import Path

import joblib
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FEAT_DIR, MODEL_DIR, OUT_DIR
from src.matchup import add_matchup_features, add_opportunity_features, CLASSES

API = "https://statsapi.mlb.com/api/v1"


def team_abbrevs():
    """MLBAM team id -> abbreviation (matches statcast home/away team codes)."""
    r = requests.get(f"{API}/teams", params={"sportId": 1}, timeout=30).json()
    return {t["id"]: t.get("abbreviation", "") for t in r.get("teams", [])}


def get_schedule(day: str):
    r = requests.get(f"{API}/schedule", params={
        "sportId": 1, "date": day, "hydrate": "probablePitcher"}, timeout=30)
    r.raise_for_status()
    return [g for d in r.json().get("dates", []) for g in d["games"]]


def pitcher_info(pid: int, season: str):
    """(hand, name, season WHIP) for a pitcher; WHIP may be None early season."""
    r = requests.get(f"{API}/people/{pid}", params={
        "hydrate": f"stats(group=[pitching],type=[season],season={season})"},
        timeout=30).json()
    person = r["people"][0]
    hand = person["pitchHand"]["code"]
    name = person.get("fullName", str(pid))
    whip = None
    try:
        whip = float(person["stats"][0]["splits"][0]["stat"]["whip"])
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return hand, name, whip


def _order_from_boxscore(box: dict, team_id: int):
    for side in ("home", "away"):
        t = box["teams"][side]
        if t["team"]["id"] == team_id:
            order = [(p.get("battingOrder", "9999"), p["person"]["id"],
                      p["person"]["fullName"]) for p in t["players"].values()
                     if p.get("battingOrder")]
            return [(pid, name) for _, pid, name in sorted(order)[:9]]
    return []


def confirmed_lineup(game_pk: int, team_id: int):
    """Official lineup for an upcoming game, if the team has posted it."""
    try:
        box = requests.get(f"{API}/game/{game_pk}/boxscore", timeout=30).json()
        return _order_from_boxscore(box, team_id)
    except Exception:
        return []


def projected_lineup(team_id: int, before: str):
    """First 9 batters from the team's last completed game."""
    r = requests.get(f"{API}/schedule", params={
        "sportId": 1, "teamId": team_id, "startDate": "2020-01-01",
        "endDate": before, "gameType": "R"}, timeout=30).json()
    pks = [g["gamePk"] for d in r.get("dates", []) for g in d["games"]
           if g["status"]["abstractGameState"] == "Final"]
    if not pks:
        return []
    box = requests.get(f"{API}/game/{pks[-1]}/boxscore", timeout=30).json()
    return _order_from_boxscore(box, team_id)


def csv_starter(starters, team_name: str):
    if starters is None:
        return None
    m = starters[starters["_team_lc"].apply(
        lambda t: t in team_name.lower() or team_name.lower() in t)]
    if m.empty or pd.isna(m["pitcher_id"].iloc[0]):
        return None
    return int(m["pitcher_id"].iloc[0])


def write_template(day: str):
    rows = []
    for g in get_schedule(day):
        for side, opp in (("home", "away"), ("away", "home")):
            team = g["teams"][side]["team"]
            prob = g["teams"][side].get("probablePitcher") or {}
            rows.append({
                "team": team["name"],
                "opponent": g["teams"][opp]["team"]["name"],
                "home_away": side,
                "game_time_utc": g.get("gameDate", ""),
                "pitcher_id": prob.get("id", ""),
                "pitcher_name": prob.get("fullName", ""),
                "lineup_posted": "Y" if confirmed_lineup(g["gamePk"], team["id"]) else "N",
            })
    dest = OUT_DIR / f"slate_{day}.csv"
    pd.DataFrame(rows).to_csv(dest, index=False)
    print(f"slate written -> {dest}")
    print("Fill in any blank pitcher_id values (each row = that team's own "
          "starter), save, then re-run with:")
    print(f"  python src/predict_upcoming.py {day} --starters {dest}")


def csv_lineup(lineups: pd.DataFrame, team_name: str):
    if lineups is None:
        return []
    m = lineups[lineups["_team_lc"].apply(lambda t: t in team_name.lower()
                                          or team_name.lower() in t)]
    if m.empty:
        return []
    if "slot" in m.columns:
        m = m.sort_values("slot")
    names = m["batter_name"] if "batter_name" in m.columns else m["batter_id"].astype(str)
    return list(zip(m["batter_id"].astype(int), names))[:9]


def latest_features(df, keys, key_vals, prefix):
    m = df
    for k, v in zip(keys, key_vals):
        m = m[m[k] == v]
    if m.empty:
        return {}
    row = m.sort_values("game_date").iloc[-1]
    return {prefix + c: row[c] for c in df.columns
            if c not in keys + ["game_date", "pitch_class"]}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    day = args[0] if args else str(date_cls.today())
    project_ok = "--project" in sys.argv
    slate_file = OUT_DIR / f"slate_{day}.csv"
    if not slate_file.exists() or "--refresh-slate" in sys.argv:
        write_template(day)
    if "--template" in sys.argv:
        return
    if "--starters" in sys.argv:
        starters = pd.read_csv(sys.argv[sys.argv.index("--starters") + 1])
    else:
        starters = pd.read_csv(slate_file)
        print(f"using starters from {slate_file} (edit it to fill in missing "
              "pitcher_id values, then re-run)")
    starters["_team_lc"] = starters["team"].str.lower().str.strip()
    lineups = None
    if "--lineups" in sys.argv:
        path = sys.argv[sys.argv.index("--lineups") + 1]
        lineups = pd.read_csv(path)
        lineups["_team_lc"] = lineups["team"].str.lower().str.strip()

    bundle = joblib.load(MODEL_DIR / "prob_model.joblib")
    gbm, iso, feats = bundle["gbm"], bundle["iso"], bundle["features"]
    th = json.load(open(MODEL_DIR / "classifier_threshold.json"))["threshold"]
    priors = json.load(open(FEAT_DIR / "league_priors.json"))
    exp_pa_file = FEAT_DIR / "expected_pa.json"
    exp_map = json.load(open(exp_pa_file)) if exp_pa_file.exists() else {}
    abbr = team_abbrevs()

    bat = pd.read_parquet(FEAT_DIR / "batter_daily.parquet")
    bat_h = pd.read_parquet(FEAT_DIR / "batter_vs_hand_daily.parquet")
    pit = pd.read_parquet(FEAT_DIR / "pitcher_daily.parquet")
    pit_h = pd.read_parquet(FEAT_DIR / "pitcher_vs_hand_daily.parquet")
    bvc = pd.read_parquet(FEAT_DIR / "batter_vs_class_daily.parquet")
    ars = pd.read_parquet(FEAT_DIR / "pitcher_arsenal_daily.parquet")
    park = pd.read_parquet(FEAT_DIR / "park_daily.parquet")
    bp_file = FEAT_DIR / "bullpen_daily.parquet"
    bp = pd.read_parquet(bp_file) if bp_file.exists() else None
    pa = pd.read_parquet(FEAT_DIR / "pa.parquet")
    stand_map = pa.groupby("batter")["stand"].agg(lambda s: s.mode().iloc[0])

    # rest/workload as of the prediction date
    day_ts = pd.Timestamp(day)
    b_last = bat.groupby("batter")["game_date"].max()
    b_7d = (bat[bat["game_date"] >= day_ts - pd.Timedelta("7D")]
              .groupby("batter").size())
    p_last = pit.groupby("pitcher")["game_date"].max()

    rows = []
    for g in get_schedule(day):
        state = g["status"]["abstractGameState"]
        if state != "Preview":
            print(f"skip {g['teams']['away']['team']['name']} @ "
                  f"{g['teams']['home']['team']['name']}: game is {state}")
            continue
        for side, opp in (("home", "away"), ("away", "home")):
            team = g["teams"][side]["team"]
            prob = g["teams"][opp].get("probablePitcher")
            sp_id = prob["id"] if prob else                 csv_starter(starters, g["teams"][opp]["team"]["name"])
            if not sp_id:
                print(f"skip {team['name']}: opponent has no probable starter "
                      "(fill one in via --template / --starters)")
                continue
            try:
                hand, sp_name, sp_whip = pitcher_info(sp_id, day[:4])
            except Exception:
                hand, sp_name, sp_whip = "R", str(sp_id), None

            lineup, src = csv_lineup(lineups, team["name"]), "csv"
            if not lineup:
                lineup, src = confirmed_lineup(g["gamePk"], team["id"]), "confirmed"
            if not lineup and project_ok:
                lineup, src = projected_lineup(team["id"], day), "projected"
            if not lineup:
                print(f"skip {team['name']}: no lineup available yet "
                      "(pass --lineups file.csv or --project, or wait until posted)")
                continue

            home_abbr = abbr.get(g["teams"]["home"]["team"]["id"], "")
            opp_abbr = abbr.get(g["teams"][opp]["team"]["id"], "")
            for slot, (pid, name) in enumerate(lineup, start=1):
                stand = stand_map.get(pid, "R")
                is_home = 1 if side == "home" else 0
                f = dict(is_home=is_home,
                         month=int(day[5:7]),
                         platoon_adv=1 if stand != hand else 0,
                         lineup_slot=min(slot, 10),
                         expected_pa=exp_map.get(f"{min(slot, 10)},{is_home}", 4.1),
                         is_day=1 if g.get("dayNight") == "day" else 0)
                if pid in b_last.index:
                    f["b_days_rest"] = min((day_ts - b_last[pid]).days, 10)
                    f["b_games_7d"] = int(b_7d.get(pid, 0))
                if sp_id in p_last.index:
                    f["p_days_rest"] = min((day_ts - p_last[sp_id]).days, 15)
                f.update(latest_features(park, ["home_team"], [home_abbr], "park_"))
                if bp is not None:
                    f.update(latest_features(bp, ["def_team"], [opp_abbr], "bp_"))
                f.update(latest_features(bat, ["batter"], [pid], "b_"))
                f.update(latest_features(bat_h, ["batter", "p_throws"], [pid, hand], "bh_"))
                f.update(latest_features(pit, ["pitcher"], [sp_id], "p_"))
                f.update(latest_features(pit_h, ["pitcher", "stand"], [sp_id, stand], "ph_"))
                f.update(latest_features(ars, ["pitcher"], [sp_id], "ars_"))
                for c in CLASSES:
                    f.update(latest_features(bvc[bvc["pitch_class"] == c],
                                             ["batter"], [pid], f"bvc_{c}_"))
                if "b_r30_pa" in f and "b_r30_games" in f:
                    f["b_r30_pa_per_game"] = f["b_r30_pa"] / max(f["b_r30_games"], 1)
                rows.append({"date": day, "game_pk": g["gamePk"],
                             "game_time": g.get("gameDate", ""),
                             "team": team["name"], "batter_name": name,
                             "batter_id": pid, "opp_starter_id": sp_id,
                             "opp_starter_name": sp_name,
                             "opp_starter_whip": sp_whip,
                             "lineup_source": src, **f})
    if not rows:
        print("No predictions generated for", day)
        return
    X = pd.DataFrame(rows)
    X = add_matchup_features(X, priors)
    X = add_opportunity_features(X)
    Xm = X.reindex(columns=feats)
    raw = gbm.predict_proba(Xm)[:, 1]
    p = iso.predict(raw)
    out = X[["date", "game_pk", "game_time", "team", "batter_name", "batter_id",
             "opp_starter_id", "opp_starter_name", "opp_starter_whip",
             "lineup_source"]].copy()
    out["home_away"] = X["is_home"].map({1: "home", 0: "away"})
    out["batting_order"] = X["lineup_slot"]
    out["expected_pa"] = X["expected_pa"].round(2)
    out["avg_vs_hand"] = X["bh_exp_avg"].round(3)        # career vs starter hand
    out["avg_vs_hand_30d"] = X["bh_r30_avg"].round(3)    # last 30 days vs hand
    out["p_hit"] = p.round(4)          # calibrated probability (honest %)
    out["raw_score"] = raw.round(6)    # fine-grained ranking (breaks p_hit ties)
    out["predict_hit"] = (p >= th).astype(int)
    try:  # per-row top SHAP drivers (skipped gracefully if shap not installed)
        import shap
        sv = shap.TreeExplainer(gbm).shap_values(Xm)
        sv = sv[1] if isinstance(sv, list) else sv
        sv = pd.DataFrame(sv, columns=feats, index=X.index)
        out["top_drivers"] = sv.apply(
            lambda r: " | ".join(f"{f}:{r[f]:+.3f}"
                                 for f in r.abs().nlargest(5).index), axis=1)
    except ImportError:
        print("note: pip install shap to get a top_drivers column")
    dest = OUT_DIR / f"predictions_{day}.csv"
    # merge with earlier runs today: a re-predicted game replaces ALL of its
    # earlier rows (handles scratches/swaps); untouched games are kept as-is
    if dest.exists():
        old = pd.read_csv(dest)
        old = old[~old["game_pk"].isin(set(out["game_pk"]))]
        out = pd.concat([old, out], ignore_index=True)
    out = out.sort_values("raw_score", ascending=False)
    out.to_csv(dest, index=False)
    print(out.head(15).to_string(index=False))
    print(f"\nsaved -> {dest}")


if __name__ == "__main__":
    main()