"""Build the game-level modeling table: one row per (batter, game).

Label:    got_hit = 1 if the batter recorded >= 1 hit in that game.
Features: batter rolling/expanding stats (overall + vs opposing starter's
          hand) and opposing starter stats (overall + vs batter's hand),
          all strictly as-of BEFORE the game date. Joined with merge_asof
          so the most recent prior feature row is used.
"""
import sys
from pathlib import Path

import json

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FEAT_DIR, RAW_DIR
from src.matchup import add_matchup_features, add_opportunity_features, CLASSES

def asof_join(left, feats, by, prefix):
    feats = feats.sort_values("game_date")
    left = left.sort_values("game_date")
    f = feats.rename(columns={c: prefix + c for c in feats.columns
                              if c not in by + ["game_date"]})
    return pd.merge_asof(left, f, on="game_date", by=by,
                         allow_exact_matches=True, direction="backward")
    # exact matches allowed because feature rows at date d contain only pre-d data


def main():
    pa = pd.read_parquet(FEAT_DIR / "pa.parquet")

    # --- identify each game's starters ---------------------------------
    # Home pitcher starts the Top half, away pitcher the Bottom half.
    first = (pa.sort_values("at_bat_number")
               .groupby(["game_pk", "inning_topbot"], sort=False)
               .first().reset_index())
    starters = first.pivot(index="game_pk", columns="inning_topbot",
                           values="pitcher").rename(
        columns={"Top": "home_starter", "Bot": "away_starter"}).reset_index()

    # --- one row per batter-game ----------------------------------------
    grp = pa.groupby(["game_pk", "batter"], sort=False)
    g = grp.agg(game_date=("game_date", "first"),
                game_year=("game_year", "first"),
                stand=("stand", "first"),
                pa_in_game=("pa", "sum"),
                hits=("hit", "sum"),
                topbot=("inning_topbot", "first"),
                home_team=("home_team", "first"),
                away_team=("away_team", "first")).reset_index()
    g["got_hit"] = (g["hits"] > 0).astype("int8")
    g["is_home"] = (g["topbot"] == "Bot").astype("int8")

    # lineup slot: order of each batter's first PA within his team's game
    first_ab = (pa.groupby(["game_pk", "batter"], sort=False)["at_bat_number"]
                  .min().reset_index(name="first_ab"))
    g = g.merge(first_ab, on=["game_pk", "batter"], how="left")
    g["lineup_slot"] = (g.groupby(["game_pk", "topbot"])["first_ab"]
                          .rank(method="first").clip(upper=10).astype("int8"))
    g = g.merge(starters, on="game_pk", how="left")
    g["opp_starter"] = g["home_starter"].where(g["is_home"] == 0, g["away_starter"])
    g = g.dropna(subset=["opp_starter"])
    g["opp_starter"] = g["opp_starter"].astype(pa["pitcher"].dtype)

    # starter handedness
    hand = pa[["pitcher", "p_throws"]].drop_duplicates("pitcher")
    g = g.merge(hand.rename(columns={"pitcher": "opp_starter",
                                     "p_throws": "opp_hand"}),
                on="opp_starter", how="left")

    # --- feature joins ----------------------------------------------------
    bat = pd.read_parquet(FEAT_DIR / "batter_daily.parquet")
    bat_h = pd.read_parquet(FEAT_DIR / "batter_vs_hand_daily.parquet")
    pit = pd.read_parquet(FEAT_DIR / "pitcher_daily.parquet")
    pit_h = pd.read_parquet(FEAT_DIR / "pitcher_vs_hand_daily.parquet")

    g = asof_join(g, bat, ["batter"], "b_")
    g = asof_join(g.rename(columns={"opp_hand": "p_throws"}),
                  bat_h, ["batter", "p_throws"], "bh_")
    g = g.rename(columns={"p_throws": "opp_hand"})
    g = asof_join(g.rename(columns={"opp_starter": "pitcher"}),
                  pit, ["pitcher"], "p_")
    g = asof_join(g, pit_h, ["pitcher", "stand"], "ph_")
    ars = pd.read_parquet(FEAT_DIR / "pitcher_arsenal_daily.parquet")
    g = asof_join(g, ars, ["pitcher"], "ars_")
    g = g.rename(columns={"pitcher": "opp_starter"})

    # batter vs pitch class (wide: one prefix per class), then weighted matchup
    bvc = pd.read_parquet(FEAT_DIR / "batter_vs_class_daily.parquet")
    for c in CLASSES:
        sub = bvc[bvc["pitch_class"] == c].drop(columns="pitch_class")
        g = asof_join(g, sub, ["batter"], f"bvc_{c}_")
    priors = json.load(open(FEAT_DIR / "league_priors.json"))
    g = add_matchup_features(g, priors)

    # park (venue = home team's park) and opposing bullpen
    park = pd.read_parquet(FEAT_DIR / "park_daily.parquet")
    g = asof_join(g, park, ["home_team"], "park_")
    bp_file = FEAT_DIR / "bullpen_daily.parquet"
    if bp_file.exists():
        bp = pd.read_parquet(bp_file)
        g["def_team"] = g["home_team"].where(g["is_home"] == 0, g["away_team"])
        g = asof_join(g, bp, ["def_team"], "bp_")

    # expected PAs by lineup slot + home/away (league empirical); saved for
    # prediction-time use
    emp = (g.groupby(["lineup_slot", "is_home"])["pa_in_game"]
             .mean().reset_index())
    exp_map = {f"{int(r.lineup_slot)},{int(r.is_home)}": float(r.pa_in_game)
               for r in emp.itertuples()}
    json.dump(exp_map, open(FEAT_DIR / "expected_pa.json", "w"), indent=2)
    g["expected_pa"] = g.apply(
        lambda r: exp_map.get(f"{int(r.lineup_slot)},{int(r.is_home)}", 4.1), axis=1)
    g = add_opportunity_features(g)

    # rest / workload (b_ and p_ prefixes are picked up as features)
    g = g.sort_values(["batter", "game_date"]).reset_index(drop=True)
    g["b_days_rest"] = (g.groupby("batter")["game_date"].diff()
                          .dt.days.clip(upper=10))
    ones = g.assign(one=1).set_index("game_date")
    g["b_games_7d"] = (ones.groupby("batter")["one"].rolling("7D").sum()
                           .reset_index(drop=True).values - 1)
    prest = (pa[["pitcher", "game_date"]].drop_duplicates()
               .sort_values(["pitcher", "game_date"]))
    prest["p_days_rest"] = (prest.groupby("pitcher")["game_date"].diff()
                                 .dt.days.clip(upper=15))
    g = g.merge(prest.rename(columns={"pitcher": "opp_starter"}),
                on=["opp_starter", "game_date"], how="left")

    # day/night (optional; from src/fetch_game_meta.py)
    meta_file = RAW_DIR / "game_meta.parquet"
    if meta_file.exists():
        meta = pd.read_parquet(meta_file)
        g = g.merge(meta, on="game_pk", how="left")
        g["is_day"] = (g["day_night"] == "day").astype("int8")
    else:
        print("note: data/raw/game_meta.parquet not found -- day/night feature "
              "skipped (run src/fetch_game_meta.py to enable)")

    g["month"] = g["game_date"].dt.month
    g["platoon_adv"] = (g["stand"] != g["opp_hand"]).astype("int8")
    g["b_r30_pa_per_game"] = g["b_r30_pa"] / g["b_r30_games"].clip(lower=1)

    out = FEAT_DIR / "train_table.parquet"
    g.to_parquet(out, index=False)
    print(f"train table: {len(g):,} rows, base hit rate = {g.got_hit.mean():.3f} -> {out}")


if __name__ == "__main__":
    main()
