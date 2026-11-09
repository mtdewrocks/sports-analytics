"""The NHL player picker list, shared by the pipeline and the API.

get_nhl_data.py writes it as nhl_players.parquet (a few KB) so the Game Log
page can fill its search box without the API downloading every game table
first. The API rebuilds it from the game files only if that file is missing.
"""
from __future__ import annotations

import pandas as pd

COLUMNS = ["id", "player", "team", "pos", "is_goalie"]


def build_player_list(skaters: pd.DataFrame, goalies: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    """Everyone with a game logged plus everyone on a current roster.

    Each player's team is their most recent one; a current roster entry
    (listed last) wins over a past game.
    """
    frames = []
    for df, is_g in ((skaters, False), (goalies, True)):
        if df is not None and not df.empty:
            order = "d" if "d" in df.columns else "date"
            last = df.sort_values(order).groupby("player_id").tail(1)
            frames.append(pd.DataFrame({
                "id": last["player_id"].astype(int), "player": last["player"].astype(str),
                "team": last["team"].astype(str),
                "pos": last["pos"].astype(str) if "pos" in last.columns else "G",
                "is_goalie": is_g,
            }))
    if rosters is not None and not rosters.empty:
        frames.append(pd.DataFrame({
            "id": rosters["player_id"].astype(int), "player": rosters["player"].astype(str),
            "team": rosters["team"].astype(str), "pos": rosters["pos"].astype(str),
            "is_goalie": rosters["pos"].astype(str) == "G",
        }))
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    allp = pd.concat(frames, ignore_index=True).drop_duplicates("id", keep="last")
    return allp.sort_values("player").reset_index(drop=True)[COLUMNS]
