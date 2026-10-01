"""NHL data pipeline: schedule, box scores, play-by-play and shift charts ->
the parquet files behind every NHL page.

    python backend/app/get_nhl_data.py                  # daily incremental run
    python backend/app/get_nhl_data.py --max-games 50   # cap work (testing)
    python backend/app/get_nhl_data.py --smoke 2025020001
        # fetch + process ONE game, print what came out, write nothing --
        # the quickest way to check the parsers against the live API.

Runs from update_nhl.yml once a day. The first run backfills last season
(~1,300 games, three requests each -- roughly 20-30 minutes); after that each
run only fetches games that finished since the previous one.

SOURCE: the NHL's free public API (nhl_api.py). Not licensed for commercial
use -- see that file's header.

OUTPUTS (backend/data/nhl/, published to the data-nhl release)
-------
nhl_games.parquet          Every regular-season/playoff game of the current and
                           previous season, including future ones (schedule).
nhl_team_games.parquet     One row per team per game: goals, shots, shot
                           attempts, xG, special teams, periods, score state.
nhl_skater_games.parquet   One row per skater per game: box score + time on
                           ice, power-play time, line, power-play unit.
nhl_goalie_games.parquet   One row per goalie appearance, with xG faced.
nhl_units.parquet          Lines, defense pairs and power-play units per game,
                           built from shift charts, with on-ice results.
nhl_unit_matchups.parquet  Each line/pair's most-faced opposing line and pair.
nhl_zones.parquet          Unblocked shot attempts by rink zone, per team-game.
nhl_shots.parquet          Every unblocked attempt with xG (training data; the
                           web app doesn't load this one).
nhl_rosters.parquet        Current rosters.
nhl_xg_model.json          Coefficients of the xG model (nhl_xg.py).
nhl_meta.json              When it ran and what it did.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import nhl_api  # noqa: E402
from nhl_processing import process_game  # noqa: E402
from nhl_teams import TEAMS  # noqa: E402
import nhl_xg  # noqa: E402

OUT = HERE.parent / "data" / "nhl"
TABLES = {
    "teams": "nhl_team_games.parquet",
    "skaters": "nhl_skater_games.parquet",
    "goalies": "nhl_goalie_games.parquet",
    "units": "nhl_units.parquet",
    "unit_matchups": "nhl_unit_matchups.parquet",
    "zones": "nhl_zones.parquet",
    "shots": "nhl_shots.parquet",
}
GAME_TYPES = {2, 3}          # regular season, playoffs
SHIFT_RETRY_DAYS = 3         # re-fetch a game whose shift chart wasn't posted yet


def today_central() -> date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Chicago")).date()
    except Exception:  # noqa: BLE001
        return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def read(name: str) -> pd.DataFrame:
    p = OUT / name
    try:
        return pd.read_parquet(p) if p.exists() else pd.DataFrame()
    except Exception as e:  # noqa: BLE001
        print(f"  could not read {name}: {e}")
        return pd.DataFrame()


def fetch_schedule(seasons: List[int]) -> pd.DataFrame:
    rows: Dict[int, Dict[str, Any]] = {}
    for season in seasons:
        n = 0
        for team in TEAMS:
            try:
                for g in nhl_api.fetch_club_schedule(team, season):
                    if g["game_type"] in GAME_TYPES:
                        rows[g["game_id"]] = g
                        n += 1
            except Exception as e:  # noqa: BLE001
                print(f"  schedule {team} {season}: {e}")
        print(f"schedule {season}: {n} team-games")
    return pd.DataFrame(list(rows.values()))


def fetch_game(game: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    gid = int(game["game_id"])
    box_raw = nhl_api.fetch_boxscore(gid)
    pbp_raw = nhl_api.fetch_pbp(gid)
    if not box_raw or not pbp_raw:
        raise RuntimeError("missing boxscore or play-by-play")
    try:
        shifts = nhl_api.parse_shifts(nhl_api.fetch_shifts(gid))
    except Exception as e:  # noqa: BLE001 -- shifts are optional; the game still counts
        print(f"  shifts {gid}: {e}")
        shifts = []
    return process_game(game, nhl_api.parse_boxscore(box_raw), nhl_api.parse_pbp(pbp_raw), shifts)


def smoke(game_id: int) -> int:
    """Fetch and process one game; print a summary. Writes nothing."""
    box_raw = nhl_api.fetch_boxscore(game_id)
    if not box_raw:
        print("no boxscore for that game id")
        return 1
    game = {"game_id": game_id, "season": box_raw.get("season"), "game_type": box_raw.get("gameType"),
            "date": box_raw.get("gameDate"), "home": (box_raw.get("homeTeam") or {}).get("abbrev"),
            "away": (box_raw.get("awayTeam") or {}).get("abbrev"),
            "home_score": (box_raw.get("homeTeam") or {}).get("score"),
            "away_score": (box_raw.get("awayTeam") or {}).get("score"),
            "last_period": (box_raw.get("gameOutcome") or {}).get("lastPeriodType")}
    out = fetch_game(game)
    print(json.dumps({k: len(v) for k, v in out.items()}))
    for t in out["teams"]:
        print({k: t[k] for k in ("team", "goals_for", "goals_against", "shots_for", "cf", "cf5",
                                 "pp_opps", "pp_goals", "sec_5v5", "sec_pp", "has_shifts")})
    for u in out["units"]:
        print(f"  {u['team']} {u['unit']:4} {u['toi_together']:5}s  {u['players']}")
    sk = pd.DataFrame(out["skaters"])
    if not sk.empty:
        print(sk.sort_values("toi", ascending=False)[["player", "team", "pos", "sog", "attempts", "toi",
                                                      "pp_toi", "line", "pp_unit"]].head(12).to_string())
    print(pd.DataFrame(out["goalies"]).to_string())
    return 0


def add_derived(tables: Dict[str, pd.DataFrame], games: pd.DataFrame) -> None:
    """Rest/back-to-back flags and starter-vs-backup, computed across the whole
    table each run (cheap) rather than per game."""
    tg = tables["teams"]
    if tg.empty:
        return
    # every scheduled game (not just processed ones) counts for rest
    sched = pd.concat([
        games[["game_id", "date", "home"]].rename(columns={"home": "team"}),
        games[["game_id", "date", "away"]].rename(columns={"away": "team"}),
    ]) if not games.empty else tg[["game_id", "date", "team"]]
    sched = sched.drop_duplicates(["game_id", "team"]).copy()
    sched["d"] = pd.to_datetime(sched["date"])
    sched = sched.sort_values(["team", "d"])
    sched["rest_days"] = (sched.groupby("team")["d"].diff().dt.days - 1)
    rest = sched.set_index(["game_id", "team"])["rest_days"]
    for key in ("teams", "skaters", "goalies"):
        df = tables[key]
        if df.empty:
            continue
        r = rest.reindex(pd.MultiIndex.from_frame(df[["game_id", "team"]])).values
        df["rest_days"] = r
        df["b2b"] = df["rest_days"] == 0

    # a team's No. 1 goalie for a season = most starts; anyone else is a backup
    gg = tables["goalies"]
    if not gg.empty:
        starts = gg[gg["starter"]].groupby(["season", "team", "player_id"]).size().rename("n").reset_index()
        leader = starts.sort_values("n").groupby(["season", "team"]).tail(1).set_index(["season", "team"])["player_id"]
        gg["is_no1"] = gg["player_id"].values == leader.reindex(
            pd.MultiIndex.from_frame(gg[["season", "team"]])).values
        sk = tables["skaters"]
        if not sk.empty:
            opp_leader = leader.reindex(pd.MultiIndex.from_frame(sk[["season", "opp"]].rename(columns={"opp": "team"}))).values
            sk["opp_goalie_backup"] = sk["opp_goalie_id"].notna() & (sk["opp_goalie_id"].values != opp_leader)


def apply_xg(tables: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    shots = tables["shots"]
    if shots.empty:
        return dict(nhl_xg.PRIOR)
    model = nhl_xg.fit_model(shots)
    shots["xg"] = nhl_xg.predict(shots, model)
    ok = shots[shots["xg"].notna()].copy()
    # ids come back as floats when any row is missing one; match on ints
    for c in ("shooter_id", "goalie_id"):
        ok[c] = pd.to_numeric(ok[c], errors="coerce").fillna(-1).astype("int64")

    sk = tables["skaters"]
    if not sk.empty:
        ix = ok.groupby(["game_id", "shooter_id"])["xg"].sum()
        sk["ixg"] = ix.reindex(pd.MultiIndex.from_frame(sk[["game_id", "player_id"]])).fillna(0).round(3).values

    gg = tables["goalies"]
    if not gg.empty:
        faced = ok.groupby(["game_id", "goalie_id"]).agg(xga=("xg", "sum"), goals=("is_goal", "sum"))
        f = faced.reindex(pd.MultiIndex.from_frame(gg[["game_id", "player_id"]]))
        gg["xga"] = f["xga"].fillna(0).round(3).values
        gg["gsax"] = (f["xga"].fillna(0) - f["goals"].fillna(0)).round(3).values

    tg = tables["teams"]
    if not tg.empty:
        for col, sub in (("xgf", ok), ("xgf5", ok[ok["is5"]])):
            s = sub.groupby(["game_id", "team"])["xg"].sum()
            tg[col] = s.reindex(pd.MultiIndex.from_frame(tg[["game_id", "team"]])).fillna(0).round(3).values
        opp = tg[["game_id", "team", "xgf", "xgf5"]].rename(columns={"team": "opp", "xgf": "xga", "xgf5": "xga5"})
        tg.drop(columns=[c for c in ("xga", "xga5") if c in tg.columns], inplace=True)
        merged = tg.merge(opp, on=["game_id", "opp"], how="left")
        tables["teams"] = merged
    return model


def compact(df: pd.DataFrame) -> pd.DataFrame:
    """Smaller files and, more to the point, a smaller footprint in the web
    worker's memory: low-cardinality strings -> category, floats -> float32."""
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object and c in ("team", "opp", "pos", "line", "pp_unit", "unit", "opp_unit",
                                           "result", "team_result", "last_period", "strength",
                                           "shot_type", "zone", "event", "decision"):
            df[c] = df[c].astype("category")
        elif df[c].dtype == "float64" and c not in ("rest_days",):
            df[c] = df[c].astype("float32")
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=2000)
    ap.add_argument("--max-minutes", type=float, default=150.0)
    ap.add_argument("--smoke", type=int, default=None)
    args = ap.parse_args()
    if args.smoke:
        return smoke(args.smoke)

    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    today = today_central()
    cur = nhl_api.season_for(today)
    prev = (cur // 10000 - 1) * 10000 + cur // 10000
    seasons = [prev, cur]

    games = fetch_schedule(seasons)
    if games.empty:
        print("schedule fetch returned nothing; keeping the previous schedule")
        games = read("nhl_games.parquet")
    else:
        games = games.sort_values(["date", "game_id"]).reset_index(drop=True)

    tables = {k: read(v) for k, v in TABLES.items()}
    for k in tables:
        if not tables[k].empty and "season" in tables[k].columns:
            tables[k] = tables[k][tables[k]["season"].isin(seasons)].copy()
            # categories from an older file would block new values on concat
            for c in tables[k].select_dtypes("category").columns:
                tables[k][c] = tables[k][c].astype(object)

    done = set(tables["teams"]["game_id"].astype(int)) if not tables["teams"].empty else set()
    # games processed without a shift chart get one more look for a few days
    if not tables["teams"].empty and "has_shifts" in tables["teams"].columns:
        tg = tables["teams"]
        recent = pd.to_datetime(tg["date"]) >= pd.Timestamp(today - timedelta(days=SHIFT_RETRY_DAYS))
        retry = set(tg.loc[(~tg["has_shifts"].astype(bool)) & recent, "game_id"].astype(int))
        done -= retry
    else:
        retry = set()

    final = games[games["state"].isin(nhl_api.FINAL_STATES)] if not games.empty else games
    todo = final[~final["game_id"].astype(int).isin(done)].to_dict("records")[: args.max_games]
    print(f"{len(todo)} games to process ({len(retry)} shift-chart retries)")

    fresh: Dict[str, List[Dict[str, Any]]] = {k: [] for k in TABLES}
    ok_ids, failed = [], 0
    for i, g in enumerate(todo, 1):
        if (time.time() - started) / 60 > args.max_minutes:
            print(f"time budget reached after {i - 1} games; the rest wait for the next run")
            break
        try:
            out = fetch_game(g)
            for k in TABLES:
                fresh[k].extend(out[k])
            ok_ids.append(int(g["game_id"]))
        except Exception as e:  # noqa: BLE001 -- one bad game shouldn't sink the run
            failed += 1
            print(f"  game {g['game_id']}: {e}")
        if i % 100 == 0:
            print(f"  {i}/{len(todo)} games")

    if ok_ids:
        for k in TABLES:
            old = tables[k]
            if not old.empty:
                old = old[~old["game_id"].astype(int).isin(ok_ids)]
            new = pd.DataFrame(fresh[k])
            tables[k] = pd.concat([old, new], ignore_index=True) if not old.empty else new
    print(f"processed {len(ok_ids)} games, {failed} failed")

    model = apply_xg(tables)
    add_derived(tables, games)

    if not games.empty:
        games.to_parquet(OUT / "nhl_games.parquet", index=False)
    for k, name in TABLES.items():
        df = tables[k]
        if not df.empty:
            sort_cols = [c for c in ("date", "game_id") if c in df.columns]
            compact(df.sort_values(sort_cols).reset_index(drop=True)).to_parquet(OUT / name, index=False)

    rosters = []
    for team in TEAMS:
        try:
            rosters.extend(nhl_api.parse_roster(team, nhl_api.fetch_roster(team)))
        except Exception as e:  # noqa: BLE001
            print(f"  roster {team}: {e}")
    if rosters:
        pd.DataFrame(rosters).to_parquet(OUT / "nhl_rosters.parquet", index=False)

    (OUT / "nhl_xg_model.json").write_text(json.dumps(model, indent=1))
    (OUT / "nhl_meta.json").write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seasons": seasons, "games_processed": len(ok_ids), "games_failed": failed,
        "total_games": int(tables["teams"]["game_id"].nunique()) if not tables["teams"].empty else 0,
        "xg_model": {k: model.get(k) for k in ("kind", "n", "goal_rate", "log_loss", "trained_at")},
    }, indent=1))
    print(f"done in {(time.time() - started) / 60:.1f} min")
    # Failing every game is a real failure; some failures are normal noise.
    return 1 if todo and not ok_ids else 0


if __name__ == "__main__":
    sys.exit(main())
