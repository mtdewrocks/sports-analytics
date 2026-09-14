"""Reduce pitch-level Statcast data to plate appearances, then build leak-free
daily feature tables:

  pa.parquet                     plate-appearance table
  batter_daily.parquet           batter overall            (batter, date)
  batter_vs_hand_daily.parquet   batter vs L/R             (batter, p_throws, date)
  pitcher_daily.parquet          pitcher overall           (pitcher, date)
  pitcher_vs_hand_daily.parquet  pitcher vs L/R            (pitcher, stand, date)
  batter_vs_class_daily.parquet  batter vs fb/br/os        (batter, pitch_class, date)
  pitcher_arsenal_daily.parquet  usage% + fastball velo    (pitcher, date)
  league_priors.json             league rates used for smoothing / fills

Every feature row keyed (entity, date) contains ONLY data from BEFORE that
date: cumulative/rolling sums are computed through each day, then that day's
own contribution is subtracted. Joining on the game date is therefore safe.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import (RAW_DIR, FEAT_DIR, ROLL_DAYS, HARD_HIT_EV, SMOOTH_PA,
                    SMOOTH_PITCHES)

HITS = {"single", "double", "triple", "home_run"}
TB = {"single": 1, "double": 2, "triple": 3, "home_run": 4}
NON_AB = {"walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_bunt",
          "sac_fly_double_play", "sac_bunt_double_play", "catcher_interf"}
BB_EVENTS = {"walk", "intent_walk"}
K_EVENTS = {"strikeout", "strikeout_double_play"}

# coarse pitch classes (robust across seasons/classification changes)
PITCH_CLASS = {
    "FF": "fb", "SI": "fb", "FT": "fb", "FC": "fb", "FA": "fb",
    "SL": "br", "CU": "br", "KC": "br", "ST": "br", "SV": "br",
    "SC": "br", "CS": "br", "KN": "br", "EP": "br",
    "CH": "os", "FS": "os", "FO": "os",
}
CLASSES = ["fb", "br", "os"]
SWINGS = {"foul", "foul_tip", "hit_into_play",
          "swinging_strike", "swinging_strike_blocked"}
WHIFFS = {"swinging_strike", "swinging_strike_blocked", "foul_tip"}

SUM_COLS = ["pa", "ab", "hit", "tb", "bb", "k", "bip", "gb", "fb", "ld",
            "hard", "ev_n", "woba_num", "woba_den"]

# last regular-season day per year (fallback postseason filter for raw files
# downloaded before game_type was kept)
REG_SEASON_END = {
    2015: "10-04", 2016: "10-02", 2017: "10-01", 2018: "10-01",
    2019: "09-29", 2020: "09-27", 2021: "10-03", 2022: "10-05",
    2023: "10-01", 2024: "09-30", 2025: "09-28",
}
VC_STATS = ["woba", "avg", "k_rate", "whiff_rate"]


def load_pitches() -> pd.DataFrame:
    files = sorted(RAW_DIR.glob("statcast_*.parquet"))
    if not files:
        raise SystemExit("No raw data in data/raw/. Run src/download_data.py first.")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df["game_date"] = pd.to_datetime(df["game_date"])
    n0 = len(df)
    end = df["game_year"].map(
        lambda y: pd.Timestamp(f"{int(y)}-{REG_SEASON_END.get(int(y), '10-03')}"))
    if "game_type" in df.columns:
        has_type = df["game_type"].notna()
        # rows with game_type: exact filter; rows without (older downloads):
        # date-based fallback
        df = df[(has_type & (df["game_type"] == "R"))
                | (~has_type & (df["game_date"] <= end))]
    else:
        df = df[df["game_date"] <= end]
    if len(df) < n0:
        print(f"regular-season filter: dropped {n0 - len(df):,} postseason pitches")
    df["pitch_class"] = df.get("pitch_type", pd.Series(index=df.index)).map(PITCH_CLASS)
    return df


def make_pa(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["events"].notna() & (df["events"] != "")].copy()
    ev = df["events"]
    df["pa"] = 1
    df["hit"] = ev.isin(HITS).astype("int8")
    df["tb"] = ev.map(TB).fillna(0).astype("int8")
    df["ab"] = (~ev.isin(NON_AB)).astype("int8")
    df["bb"] = ev.isin(BB_EVENTS).astype("int8")
    df["k"] = ev.isin(K_EVENTS).astype("int8")
    bip = df["bb_type"].notna() & (df["bb_type"] != "")
    df["bip"] = bip.astype("int8")
    df["gb"] = (df["bb_type"] == "ground_ball").astype("int8")
    df["fb"] = df["bb_type"].isin(["fly_ball", "popup"]).astype("int8")
    df["ld"] = (df["bb_type"] == "line_drive").astype("int8")
    has_ev = bip & df["launch_speed"].notna()
    df["ev_n"] = has_ev.astype("int8")
    df["hard"] = (has_ev & (df["launch_speed"] >= HARD_HIT_EV)).astype("int8")
    df["woba_num"] = pd.to_numeric(df["woba_value"], errors="coerce").fillna(0.0)
    df["woba_den"] = pd.to_numeric(df["woba_denom"], errors="coerce").fillna(0.0)
    keep = ["game_pk", "game_date", "game_year", "batter", "pitcher", "stand",
            "p_throws", "events", "at_bat_number", "inning_topbot",
            "home_team", "away_team", "pitch_class"] + SUM_COLS
    return df[keep]


def leakfree_sums(df: pd.DataFrame, keys: list, sum_cols: list) -> pd.DataFrame:
    """Per (keys, date): expanding and rolling-window sums of everything
    STRICTLY BEFORE that date."""
    day = (df.groupby(keys + ["game_date"], sort=False)[sum_cols]
             .sum().reset_index().sort_values(keys + ["game_date"])
             .reset_index(drop=True))
    gb = day.groupby(keys, sort=False)
    exp = gb[sum_cols].cumsum() - day[sum_cols]
    exp.columns = ["exp_" + c for c in sum_cols]
    di = day.set_index("game_date")
    roll = (di.groupby(keys)[sum_cols].rolling(f"{ROLL_DAYS}D").sum()
              .reset_index(drop=True) - day[sum_cols].values)
    roll.columns = ["r30_" + c for c in sum_cols]
    return pd.concat([day[keys + ["game_date"]], exp, roll], axis=1)


def league_priors(pa: pd.DataFrame) -> dict:
    s = pa[SUM_COLS].sum()
    return {
        "avg": s.hit / max(s.ab, 1), "woba": s.woba_num / max(s.woba_den, 1),
        "iso": (s.tb - s.hit) / max(s.ab, 1), "bb_rate": s.bb / s.pa,
        "k_rate": s.k / s.pa, "hit_rate": s.hit / s.pa,
        "gb_rate": s.gb / max(s.bip, 1),
        "fb_rate": s.fb / max(s.bip, 1), "ld_rate": s.ld / max(s.bip, 1),
        "hard_rate": s.hard / max(s.ev_n, 1),
    }


def _rates(f: pd.DataFrame, pre: str, priors: dict, m: float) -> pd.DataFrame:
    g = lambda c: f[pre + c]
    out = pd.DataFrame(index=f.index)
    sm = lambda num, den, prior: (num + m * prior) / (den + m)
    out[pre + "avg"] = sm(g("hit"), g("ab"), priors["avg"])
    out[pre + "woba"] = sm(g("woba_num"), g("woba_den"), priors["woba"])
    out[pre + "iso"] = sm(g("tb") - g("hit"), g("ab"), priors["iso"])
    out[pre + "bb_rate"] = sm(g("bb"), g("pa"), priors["bb_rate"])
    out[pre + "k_rate"] = sm(g("k"), g("pa"), priors["k_rate"])
    out[pre + "hit_rate"] = sm(g("hit"), g("pa"), priors["hit_rate"])
    out[pre + "gb_rate"] = sm(g("gb"), g("bip"), priors["gb_rate"])
    out[pre + "fb_rate"] = sm(g("fb"), g("bip"), priors["fb_rate"])
    out[pre + "ld_rate"] = sm(g("ld"), g("bip"), priors["ld_rate"])
    has = g("ev_n") > 0
    out[pre + "hard_rate"] = np.where(
        has, (g("hard") + m * priors["hard_rate"]) / (g("ev_n") + m), np.nan)
    out[pre + "pa_n"] = g("pa")
    return out


def daily_features(pa, keys, priors):
    f = leakfree_sums(pa, keys, SUM_COLS)
    out = pd.concat([f[keys + ["game_date", "exp_pa", "r30_pa"]],
                     _rates(f, "exp_", priors, SMOOTH_PA),
                     _rates(f, "r30_", priors, SMOOTH_PA / 2)], axis=1)
    day = pa.groupby(keys + ["game_date"], sort=False).size().reset_index(name="gp")
    day = day.sort_values(keys + ["game_date"]).reset_index(drop=True)
    gp = (day.assign(gp=1).set_index("game_date").groupby(keys)["gp"]
             .rolling(f"{ROLL_DAYS}D").sum().reset_index(drop=True) - 1)
    out["r30_games"] = gp.values
    return out.loc[:, ~out.columns.duplicated()]


def batter_vs_class_daily(pitches: pd.DataFrame) -> tuple:
    """Batter performance vs coarse pitch class (whiffs use every pitch;
    outcome stats use PA-ending pitches)."""
    d = pitches.dropna(subset=["pitch_class"]).copy()
    ending = d["events"].notna() & (d["events"] != "")
    d["swing"] = d["description"].isin(SWINGS).astype("int8")
    d["whiff"] = d["description"].isin(WHIFFS).astype("int8")
    d["pa"] = ending.astype("int8")
    d["hit"] = (ending & d["events"].isin(HITS)).astype("int8")
    d["ab"] = (ending & ~d["events"].isin(NON_AB)).astype("int8")
    d["k"] = (ending & d["events"].isin(K_EVENTS)).astype("int8")
    d["woba_num"] = np.where(ending, pd.to_numeric(d["woba_value"], errors="coerce").fillna(0.0), 0.0)
    d["woba_den"] = np.where(ending, pd.to_numeric(d["woba_denom"], errors="coerce").fillna(0.0), 0.0)
    cols = ["swing", "whiff", "pa", "hit", "ab", "k", "woba_num", "woba_den"]

    # per-class league priors
    pri = {}
    for c, grp in d.groupby("pitch_class"):
        s = grp[cols].sum()
        pri[c] = {"woba": s.woba_num / max(s.woba_den, 1),
                  "avg": s.hit / max(s.ab, 1),
                  "k_rate": s.k / max(s.pa, 1),
                  "whiff_rate": s.whiff / max(s.swing, 1)}

    parts = []
    for c in CLASSES:
        sub = d[d["pitch_class"] == c]
        if sub.empty:
            continue
        f = leakfree_sums(sub, ["batter"], cols)
        out = f[["batter", "game_date"]].copy()
        out["pitch_class"] = c
        for pre, m in (("exp_", SMOOTH_PA), ("r30_", SMOOTH_PA / 2)):
            g = lambda x: f[pre + x]
            out[pre + "woba"] = (g("woba_num") + m * pri[c]["woba"]) / (g("woba_den") + m)
            out[pre + "avg"] = (g("hit") + m * pri[c]["avg"]) / (g("ab") + m)
            out[pre + "k_rate"] = (g("k") + m * pri[c]["k_rate"]) / (g("pa") + m)
            out[pre + "whiff_rate"] = (g("whiff") + m * pri[c]["whiff_rate"]) / (g("swing") + m)
            out[pre + "pa_n"] = g("pa")
        parts.append(out)
    return pd.concat(parts, ignore_index=True), pri


def pitcher_whiff_daily(pitches: pd.DataFrame) -> pd.DataFrame:
    """Pitcher swing-and-miss quality, leak-free daily: swinging-strike rate
    (whiffs/pitch), whiff-per-swing, CSW% (called + swinging strikes per
    pitch), overall and whiff rate per pitch class."""
    d = pitches.copy()
    d["np"] = 1
    d["swing"] = d["description"].isin(SWINGS).astype("int8")
    d["whiff"] = d["description"].isin(WHIFFS).astype("int8")
    d["cs"] = (d["description"] == "called_strike").astype("int8")
    cols = ["np", "swing", "whiff", "cs"]
    tot = d[cols].sum()
    pri_swstr = tot.whiff / tot.np
    pri_wps = tot.whiff / max(tot.swing, 1)
    pri_csw = (tot.whiff + tot.cs) / tot.np

    f = leakfree_sums(d, ["pitcher"], cols)
    out = f[["pitcher", "game_date"]].copy()
    for pre, m in (("exp_", SMOOTH_PITCHES), ("r30_", SMOOTH_PITCHES / 2)):
        g = lambda x: f[pre + x]
        out[pre + "swstr"] = (g("whiff") + m * pri_swstr) / (g("np") + m)
        out[pre + "whiff_per_swing"] = (g("whiff") + m * pri_wps) / (g("swing") + m)
        out[pre + "csw"] = (g("whiff") + g("cs") + m * pri_csw) / (g("np") + m)

    # whiff rate per pitch class (how nasty is each pitch type)
    dc = d.dropna(subset=["pitch_class"])
    for c in CLASSES:
        sub = dc[dc["pitch_class"] == c]
        if sub.empty:
            continue
        pri_c = sub["whiff"].sum() / max(sub["swing"].sum(), 1)
        fc = leakfree_sums(sub, ["pitcher"], ["swing", "whiff"])
        fc_out = fc[["pitcher", "game_date"]].copy()
        for pre, m in (("exp_", SMOOTH_PITCHES / 2), ("r30_", SMOOTH_PITCHES / 4)):
            g = lambda x: fc[pre + x]
            fc_out[pre + f"whiff_{c}"] = (g("whiff") + m * pri_c) / (g("swing") + m)
        out = out.merge(fc_out, on=["pitcher", "game_date"], how="left")
    # forward-fill per pitcher: a day without e.g. offspeed pitches keeps the
    # last known rate for that class (still leak-free: all prior data)
    out = out.sort_values(["pitcher", "game_date"])
    cls_cols = [c for c in out.columns if "whiff_" in c and c.split("_")[-1] in CLASSES]
    out[cls_cols] = out.groupby("pitcher")[cls_cols].ffill()
    return out


def relief_usage_daily(pa: pd.DataFrame) -> pd.DataFrame:
    """Actual relief batters-faced per team per day (for pen-fatigue lookups)."""
    bp = bullpen_pa(pa)
    if not len(bp):
        return pd.DataFrame(columns=["def_team", "game_date", "rel_bf"])
    return (bp.groupby(["def_team", "game_date"])["pa"].sum()
              .reset_index(name="rel_bf"))


def pitcher_arsenal_daily(pitches: pd.DataFrame) -> tuple:
    d = pitches.dropna(subset=["pitch_class"]).copy()
    d["np"] = 1
    for c in CLASSES:
        d["n_" + c] = (d["pitch_class"] == c).astype("int8")
    is_fb = d["pitch_class"] == "fb"
    d["v_fb"] = np.where(is_fb, pd.to_numeric(d["release_speed"], errors="coerce").fillna(0.0), 0.0)
    d["nv_fb"] = (is_fb & d["release_speed"].notna()).astype("int8")
    cols = ["np", "n_fb", "n_br", "n_os", "v_fb", "nv_fb"]

    tot = d[cols].sum()
    usage_pri = {c: tot["n_" + c] / tot["np"] for c in CLASSES}

    f = leakfree_sums(d, ["pitcher"], cols)
    out = f[["pitcher", "game_date"]].copy()
    for pre, m in (("exp_", SMOOTH_PITCHES), ("r30_", SMOOTH_PITCHES / 2)):
        g = lambda x: f[pre + x]
        for c in CLASSES:
            out[pre + "usage_" + c] = (g("n_" + c) + m * usage_pri[c]) / (g("np") + m)
        out[pre + "velo_fb"] = np.where(g("nv_fb") > 0, g("v_fb") / g("nv_fb").clip(lower=1), np.nan)
        out[pre + "pitches"] = g("np")
    return out, usage_pri


def bullpen_pa(pa: pd.DataFrame) -> pd.DataFrame:
    """PAs thrown by relievers (any pitcher who didn't start that half)."""
    first = (pa.sort_values("at_bat_number")
               .groupby(["game_pk", "inning_topbot"], sort=False)["pitcher"]
               .first().rename("starter").reset_index())
    d = pa.merge(first, on=["game_pk", "inning_topbot"], how="left")
    d = d[d["pitcher"] != d["starter"]].copy()
    d["def_team"] = np.where(d["inning_topbot"] == "Top",
                             d["home_team"], d["away_team"])
    return d


def main():
    pitches = load_pitches()
    pa = make_pa(pitches)
    pa.to_parquet(FEAT_DIR / "pa.parquet", index=False)
    priors = league_priors(pa)
    print("league priors:", {k: round(v, 3) for k, v in priors.items()})

    for name, keys in [("batter_daily", ["batter"]),
                       ("batter_vs_hand_daily", ["batter", "p_throws"]),
                       ("pitcher_daily", ["pitcher"]),
                       ("pitcher_vs_hand_daily", ["pitcher", "stand"])]:
        f = daily_features(pa, keys, priors)
        f.to_parquet(FEAT_DIR / f"{name}.parquet", index=False)
        print(f"{name}: {len(f):,} rows")

    bp = bullpen_pa(pa)
    if len(bp):
        f = daily_features(bp, ["def_team"], priors)
        f.to_parquet(FEAT_DIR / "bullpen_daily.parquet", index=False)
        print(f"bullpen_daily: {len(f):,} rows")
    else:
        print("bullpen_daily: no relief PAs found (skipped)")

    park = daily_features(pa, ["home_team"], priors)
    park.to_parquet(FEAT_DIR / "park_daily.parquet", index=False)
    print(f"park_daily: {len(park):,} rows")

    pw = pitcher_whiff_daily(pitches)
    pw.to_parquet(FEAT_DIR / "pitcher_whiff_daily.parquet", index=False)
    print(f"pitcher_whiff_daily: {len(pw):,} rows")

    ru = relief_usage_daily(pa)
    ru.to_parquet(FEAT_DIR / "relief_usage_daily.parquet", index=False)
    print(f"relief_usage_daily: {len(ru):,} rows")

    vc, vc_pri = batter_vs_class_daily(pitches)
    vc.to_parquet(FEAT_DIR / "batter_vs_class_daily.parquet", index=False)
    print(f"batter_vs_class_daily: {len(vc):,} rows")

    ars, usage_pri = pitcher_arsenal_daily(pitches)
    ars.to_parquet(FEAT_DIR / "pitcher_arsenal_daily.parquet", index=False)
    print(f"pitcher_arsenal_daily: {len(ars):,} rows")

    json.dump({"rates": priors, "vc": vc_pri, "usage": usage_pri},
              open(FEAT_DIR / "league_priors.json", "w"), indent=2, default=float)


if __name__ == "__main__":
    main()
