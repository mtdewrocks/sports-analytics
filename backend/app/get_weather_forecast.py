"""Live wind/temp/precip FORECAST for upcoming MLB and NFL games (games that
haven't started yet), from Open-Meteo (https://open-meteo.com) -- free, no
API key, global coverage (unlike the US-only National Weather Service),
which matters here since a few NFL games each season are played overseas
(London, Madrid, Munich, ...).

This is a genuine forecast, unlike the two pages this replaces:
  - the old MLB Weather page was static ballpark trivia, no live data at all
  - the old NFL Weather page was a BACKTEST of already-played games' real
    recorded conditions, not a forecast for what hasn't happened yet

Run periodically through the day (see .github/workflows/update_weather.yml)
so a forecast that firms up between runs -- wind easing, a rain chance
dropping -- reaches the page within a couple of hours, for games still
in the future at run time. A game already underway or finished by the time
this runs is simply dropped from the output on the next pass; this file is a
snapshot of what's upcoming, not history.

    python backend/app/get_weather_forecast.py

Output:
  backend/data/mlb/mlb_weather_forecast.parquet
  backend/data/nfl/nfl_weather_forecast.parquet
(either may be skipped/empty if that sport has nothing upcoming right now --
e.g. an MLB off-day, or an NFL bye week with no games left on the slate the
forecast window covers.)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

MLB_API = "https://statsapi.mlb.com/api/v1"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 30

MLB_OUT = Path(__file__).resolve().parent.parent / "data" / "mlb" / "mlb_weather_forecast.parquet"
NFL_OUT = Path(__file__).resolve().parent.parent / "data" / "nfl" / "nfl_weather_forecast.parquet"

# How many days out to ask Open-Meteo to forecast. MLB only ever needs
# today (the day-of-game slate this script keys off), but NFL games get
# announced up to a full week ahead, so this covers both in one shared call
# -- Open-Meteo's own max is 16.
FORECAST_DAYS = 10

# nflverse's schedule times (`gametime`) are published in US/Eastern
# regardless of the stadium's actual local zone -- the standard "1:00 PM
# ET" / "4:25 PM ET" / "8:15 PM ET" windows the NFL itself publishes in.
NFL_SCHEDULE_TZ = ZoneInfo("America/New_York")

HOURLY_FIELDS = "temperature_2m,precipitation_probability,wind_speed_10m,wind_gusts_10m,wind_direction_10m"

# ---------------------------------------------------------------------------
# Stadium coordinates. Approximate (city-block accuracy) is plenty for an
# hourly weather forecast -- these aren't survey coordinates.
#
# roof: "outdoor" (always weather-exposed), "retractable" (weather-exposed
# when open -- which is most MLB retractable parks most of the time, but NOT
# most NFL ones -- included anyway with the tag so the page can label it
# rather than silently guess), or "dome" (fixed roof, no plausible weather
# exposure -- included in the output so the page can show "indoors", not
# fetched from Open-Meteo at all since there's nothing to forecast).
# ---------------------------------------------------------------------------

MLB_STADIUMS: dict[str, dict] = {
    "Arizona Diamondbacks":  {"lat": 33.4455, "lon": -112.0667, "stadium": "Chase Field",                 "roof": "retractable"},
    "Atlanta Braves":        {"lat": 33.8908, "lon": -84.4678,  "stadium": "Truist Park",                 "roof": "outdoor"},
    "Baltimore Orioles":     {"lat": 39.2839, "lon": -76.6218,  "stadium": "Oriole Park at Camden Yards",  "roof": "outdoor"},
    "Boston Red Sox":        {"lat": 42.3467, "lon": -71.0972,  "stadium": "Fenway Park",                  "roof": "outdoor"},
    "Chicago Cubs":          {"lat": 41.9484, "lon": -87.6553,  "stadium": "Wrigley Field",                "roof": "outdoor"},
    "Chicago White Sox":     {"lat": 41.8299, "lon": -87.6338,  "stadium": "Rate Field",                   "roof": "outdoor"},
    "Cincinnati Reds":       {"lat": 39.0979, "lon": -84.5066,  "stadium": "Great American Ball Park",     "roof": "outdoor"},
    "Cleveland Guardians":   {"lat": 41.4962, "lon": -81.6852,  "stadium": "Progressive Field",            "roof": "outdoor"},
    "Colorado Rockies":      {"lat": 39.7559, "lon": -104.9942, "stadium": "Coors Field",                  "roof": "outdoor"},
    "Detroit Tigers":        {"lat": 42.3390, "lon": -83.0485,  "stadium": "Comerica Park",                "roof": "outdoor"},
    "Houston Astros":        {"lat": 29.7573, "lon": -95.3555,  "stadium": "Daikin Park",                  "roof": "retractable"},
    "Kansas City Royals":    {"lat": 39.0517, "lon": -94.4803,  "stadium": "Kauffman Stadium",             "roof": "outdoor"},
    "Los Angeles Angels":    {"lat": 33.8003, "lon": -117.8827, "stadium": "Angel Stadium",                "roof": "outdoor"},
    "Los Angeles Dodgers":   {"lat": 34.0739, "lon": -118.2400, "stadium": "Dodger Stadium",               "roof": "outdoor"},
    "Miami Marlins":         {"lat": 25.7781, "lon": -80.2196,  "stadium": "loanDepot park",               "roof": "retractable"},
    "Milwaukee Brewers":     {"lat": 43.0280, "lon": -87.9712,  "stadium": "American Family Field",        "roof": "retractable"},
    "Minnesota Twins":       {"lat": 44.9817, "lon": -93.2776,  "stadium": "Target Field",                 "roof": "outdoor"},
    "New York Mets":         {"lat": 40.7571, "lon": -73.8458,  "stadium": "Citi Field",                   "roof": "outdoor"},
    "New York Yankees":      {"lat": 40.8296, "lon": -73.9262,  "stadium": "Yankee Stadium",               "roof": "outdoor"},
    "Athletics":             {"lat": 38.5802, "lon": -121.5133, "stadium": "Sutter Health Park",           "roof": "outdoor"},
    "Philadelphia Phillies": {"lat": 39.9061, "lon": -75.1665,  "stadium": "Citizens Bank Park",           "roof": "outdoor"},
    "Pittsburgh Pirates":    {"lat": 40.4469, "lon": -80.0057,  "stadium": "PNC Park",                     "roof": "outdoor"},
    "San Diego Padres":      {"lat": 32.7073, "lon": -117.1566, "stadium": "Petco Park",                   "roof": "outdoor"},
    "Seattle Mariners":      {"lat": 47.5914, "lon": -122.3325, "stadium": "T-Mobile Park",                "roof": "retractable"},
    "San Francisco Giants":  {"lat": 37.7786, "lon": -122.3893, "stadium": "Oracle Park",                  "roof": "outdoor"},
    "St. Louis Cardinals":   {"lat": 38.6226, "lon": -90.1928,  "stadium": "Busch Stadium",                "roof": "outdoor"},
    "Tampa Bay Rays":        {"lat": 27.7683, "lon": -82.6534,  "stadium": "Tropicana Field",              "roof": "dome"},
    "Texas Rangers":         {"lat": 32.7473, "lon": -97.0828,  "stadium": "Globe Life Field",             "roof": "retractable"},
    "Toronto Blue Jays":     {"lat": 43.6414, "lon": -79.3894,  "stadium": "Rogers Centre",                "roof": "retractable"},
    "Washington Nationals":  {"lat": 38.8730, "lon": -77.0074,  "stadium": "Nationals Park",               "roof": "outdoor"},
}

# Keyed by the exact 'stadium' string nfl_schedule.parquet uses -- that file
# already carries a per-game venue (and covers relocations/international
# games on its own), so this only needs to add coordinates + a static roof
# classification, not a team -> venue mapping of its own.
NFL_STADIUMS: dict[str, dict] = {
    "State Farm Stadium":              {"lat": 33.5276, "lon": -112.2626, "roof": "retractable"},
    "Mercedes-Benz Stadium":           {"lat": 33.7554, "lon": -84.4008,  "roof": "retractable"},
    "M&T Bank Stadium":                {"lat": 39.2780, "lon": -76.6227,  "roof": "outdoor"},
    "Highmark Stadium":                {"lat": 42.7738, "lon": -78.7870,  "roof": "outdoor"},
    "Bank of America Stadium":         {"lat": 35.2258, "lon": -80.8528,  "roof": "outdoor"},
    "Soldier Field":                   {"lat": 41.8623, "lon": -87.6167,  "roof": "outdoor"},
    "Paycor Stadium":                  {"lat": 39.0955, "lon": -84.5160,  "roof": "outdoor"},
    "Huntington Bank Field":           {"lat": 41.5061, "lon": -81.6995,  "roof": "outdoor"},
    "AT&T Stadium":                    {"lat": 32.7473, "lon": -97.0945,  "roof": "retractable"},
    "Empower Field at Mile High":      {"lat": 39.7439, "lon": -105.0201, "roof": "outdoor"},
    "Ford Field":                      {"lat": 42.3400, "lon": -83.0456,  "roof": "dome"},
    "Lambeau Field":                   {"lat": 44.5013, "lon": -88.0622,  "roof": "outdoor"},
    "Reliant Stadium":                 {"lat": 29.6847, "lon": -95.4107,  "roof": "retractable"},
    "NRG Stadium":                     {"lat": 29.6847, "lon": -95.4107,  "roof": "retractable"},
    "Lucas Oil Stadium":               {"lat": 39.7601, "lon": -86.1639,  "roof": "retractable"},
    "EverBank Stadium":                {"lat": 30.3239, "lon": -81.6373,  "roof": "outdoor"},
    "GEHA Field at Arrowhead Stadium": {"lat": 39.0489, "lon": -94.4839,  "roof": "outdoor"},
    "SoFi Stadium":                    {"lat": 33.9535, "lon": -118.3392, "roof": "dome"},
    "Allegiant Stadium":               {"lat": 36.0909, "lon": -115.1833, "roof": "dome"},
    "Hard Rock Stadium":               {"lat": 25.9580, "lon": -80.2389,  "roof": "outdoor"},
    "U.S. Bank Stadium":               {"lat": 44.9736, "lon": -93.2575,  "roof": "dome"},
    "Gillette Stadium":                {"lat": 42.0909, "lon": -71.2643,  "roof": "outdoor"},
    "Caesars Superdome":               {"lat": 29.9511, "lon": -90.0812,  "roof": "dome"},
    "MetLife Stadium":                 {"lat": 40.8135, "lon": -74.0745,  "roof": "outdoor"},
    "Lincoln Financial Field":         {"lat": 39.9008, "lon": -75.1675,  "roof": "outdoor"},
    "Acrisure Stadium":                {"lat": 40.4468, "lon": -80.0158,  "roof": "outdoor"},
    "Lumen Field":                     {"lat": 47.5952, "lon": -122.3316, "roof": "outdoor"},
    "Levi's Stadium":                  {"lat": 37.4032, "lon": -121.9698, "roof": "outdoor"},
    "Raymond James Stadium":           {"lat": 27.9759, "lon": -82.5033,  "roof": "outdoor"},
    "Nissan Stadium":                  {"lat": 36.1665, "lon": -86.7713,  "roof": "outdoor"},
    "Northwest Stadium":               {"lat": 38.9078, "lon": -76.8645,  "roof": "outdoor"},
    # International Series venues -- open-air soccer/cricket grounds, no
    # roof to speak of, included so a London/Madrid/Munich/Rio/Melbourne
    # game still gets a real forecast instead of silently vanishing from
    # the page just because it's not a US venue.
    "Wembley Stadium":                 {"lat": 51.5560, "lon": -0.2795,   "roof": "outdoor"},
    "Tottenham Hotspur Stadium":       {"lat": 51.6043, "lon": -0.0664,   "roof": "outdoor"},
    "Bernabeu":                        {"lat": 40.4531, "lon": -3.6883,   "roof": "outdoor"},
    "Estadio Santiago Bernabeu":       {"lat": 40.4531, "lon": -3.6883,   "roof": "outdoor"},
    "Allianz Arena":                   {"lat": 48.2188, "lon": 11.6247,   "roof": "outdoor"},
    "FC Bayern Munich Stadium":        {"lat": 48.2188, "lon": 11.6247,   "roof": "outdoor"},
    "Estadio Banorte":                 {"lat": 25.6689, "lon": -100.2434, "roof": "outdoor"},
    "Maracana Stadium":                {"lat": -22.9122, "lon": -43.2302, "roof": "outdoor"},
    "Stade de France":                 {"lat": 48.9244, "lon": 2.3601,    "roof": "outdoor"},
    "Melbourne Cricket Ground":        {"lat": -37.8199, "lon": 144.9834, "roof": "outdoor"},
}


def _fetch_forecasts(locations: list[tuple[float, float]]) -> list[dict]:
    """One batched Open-Meteo call for every distinct venue this run needs
    -- Open-Meteo accepts comma-joined lat/lon lists and returns one
    forecast object per location, in the same order, so this is a single
    request regardless of how many games are on the slate."""
    if not locations:
        return []
    params = {
        "latitude": ",".join(str(lat) for lat, _ in locations),
        "longitude": ",".join(str(lon) for _, lon in locations),
        "hourly": HOURLY_FIELDS,
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "forecast_days": FORECAST_DAYS,
        "timezone": "UTC",
    }
    r = requests.get(OPEN_METEO, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    # A single-location request returns one object, not a one-element list.
    return data if isinstance(data, list) else [data]


def _nearest_hour(forecast: dict, target_utc: datetime) -> dict | None:
    """The hourly forecast row closest to target_utc, or None if the target
    falls outside this call's forecast window (e.g. a game more than
    FORECAST_DAYS out)."""
    hourly = forecast.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return None
    target = target_utc.replace(tzinfo=None)
    best_idx, best_diff = None, None
    for i, t in enumerate(times):
        ts = datetime.fromisoformat(t)
        diff = abs((ts - target).total_seconds())
        if best_diff is None or diff < best_diff:
            best_idx, best_diff = i, diff
    # More than 90 minutes from the nearest hourly point isn't a real match
    # (e.g. past the end of the forecast window) -- don't fabricate one.
    if best_idx is None or best_diff > 90 * 60:
        return None
    return {
        "temp_f": hourly["temperature_2m"][best_idx],
        "wind_mph": hourly["wind_speed_10m"][best_idx],
        "wind_gust_mph": hourly["wind_gusts_10m"][best_idx],
        "wind_dir_deg": hourly["wind_direction_10m"][best_idx],
        "precip_pct": hourly["precipitation_probability"][best_idx],
    }


def _mlb_upcoming_games() -> pd.DataFrame:
    """Today's MLB slate with each game's actual start time -- same MLB
    Stats API endpoint get_probable_starters.py already uses, kept
    independent of that script's output on purpose (self-contained, no
    ordering dependency between builders in the workflow)."""
    day = datetime.now(timezone.utc).date().isoformat()
    r = requests.get(f"{MLB_API}/schedule", params={"sportId": 1, "date": day}, timeout=TIMEOUT)
    r.raise_for_status()
    games = [g for d in r.json().get("dates", []) for g in d["games"]]

    now = datetime.now(timezone.utc)
    rows = []
    for g in games:
        # abstractGameState is "Preview" before first pitch, "Live" during,
        # "Final" after -- only forecast games that haven't started.
        if g.get("status", {}).get("abstractGameState") != "Preview":
            continue
        home = g["teams"]["home"]["team"]["name"]
        away = g["teams"]["away"]["team"]["name"]
        game_time = g.get("gameDate")  # ISO8601 UTC, e.g. "2026-09-21T23:10:00Z"
        if not game_time:
            continue
        start = datetime.fromisoformat(game_time.replace("Z", "+00:00"))
        if start < now:
            continue
        rows.append({
            "game_pk": g["gamePk"], "home_team": home, "away_team": away,
            "game_time_utc": start,
        })
    return pd.DataFrame(rows)


def _nfl_upcoming_games() -> pd.DataFrame:
    """Every scheduled-but-not-yet-played NFL game currently on the
    published schedule (this season, kickoff still in the future) -- not
    just this week's, so a Thursday run already has next Sunday's slate
    ready rather than waiting for the week to turn over."""
    from app.config import settings
    r = requests.get(f"{settings.NFL_BASE_URL}/nfl_schedule.parquet", timeout=TIMEOUT)
    r.raise_for_status()
    import io
    df = pd.read_parquet(io.BytesIO(r.content))

    now = datetime.now(timezone.utc)
    season = df["season"].max()
    df = df[(df["season"] == season) & df["gameday"].notna() & df["gametime"].notna()].copy()

    def _kickoff_utc(row) -> datetime | None:
        try:
            d = pd.to_datetime(row["gameday"]).date()
            h, m = str(row["gametime"]).split(":")[:2]
            local = datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=NFL_SCHEDULE_TZ)
            return local.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None

    df["kickoff_utc"] = df.apply(_kickoff_utc, axis=1)
    df = df[df["kickoff_utc"].notna() & (df["kickoff_utc"] > now)]
    # Already-played games (this season, still technically "future" by date
    # if the score hasn't posted yet for some data-lag reason) are excluded
    # by the score check too, belt-and-suspenders with the kickoff-time
    # filter above.
    df = df[df["home_score"].isna()]
    return df[["game_id", "week", "gameday", "gametime", "home_team", "away_team", "stadium", "kickoff_utc"]]


def build_mlb() -> pd.DataFrame:
    games = _mlb_upcoming_games()
    if games.empty:
        return games

    venues = []
    for _, g in games.iterrows():
        info = MLB_STADIUMS.get(g["home_team"])
        if info is None:
            print(f"warning: no stadium entry for MLB team '{g['home_team']}' -- skipping")
            continue
        venues.append((g, info))

    to_fetch = [(g, info) for g, info in venues if info["roof"] != "dome"]
    forecasts = _fetch_forecasts([(info["lat"], info["lon"]) for _, info in to_fetch])

    rows = []
    for (g, info), forecast in zip(to_fetch, forecasts):
        wx = _nearest_hour(forecast, g["game_time_utc"])
        rows.append({
            "game_pk": g["game_pk"], "home_team": g["home_team"], "away_team": g["away_team"],
            "stadium": info["stadium"], "roof": info["roof"],
            "game_time_utc": g["game_time_utc"].isoformat(),
            **(wx or {"temp_f": None, "wind_mph": None, "wind_gust_mph": None, "wind_dir_deg": None, "precip_pct": None}),
        })
    # Dome games -- no forecast fetched, but still listed so the page can
    # show "Indoors" instead of the game silently not appearing at all.
    for g, info in venues:
        if info["roof"] == "dome":
            rows.append({
                "game_pk": g["game_pk"], "home_team": g["home_team"], "away_team": g["away_team"],
                "stadium": info["stadium"], "roof": info["roof"],
                "game_time_utc": g["game_time_utc"].isoformat(),
                "temp_f": None, "wind_mph": None, "wind_gust_mph": None, "wind_dir_deg": None, "precip_pct": None,
            })
    return pd.DataFrame(rows)


def build_nfl() -> pd.DataFrame:
    games = _nfl_upcoming_games()
    if games.empty:
        return games

    venues = []
    for _, g in games.iterrows():
        info = NFL_STADIUMS.get(g["stadium"])
        if info is None:
            print(f"warning: no stadium entry for NFL venue '{g['stadium']}' -- skipping")
            continue
        venues.append((g, info))

    to_fetch = [(g, info) for g, info in venues if info["roof"] != "dome"]
    forecasts = _fetch_forecasts([(info["lat"], info["lon"]) for _, info in to_fetch])

    rows = []
    for (g, info), forecast in zip(to_fetch, forecasts):
        wx = _nearest_hour(forecast, g["kickoff_utc"])
        rows.append({
            "game_id": g["game_id"], "week": int(g["week"]), "home_team": g["home_team"], "away_team": g["away_team"],
            "stadium": g["stadium"], "roof": info["roof"], "kickoff_utc": g["kickoff_utc"].isoformat(),
            **(wx or {"temp_f": None, "wind_mph": None, "wind_gust_mph": None, "wind_dir_deg": None, "precip_pct": None}),
        })
    for g, info in venues:
        if info["roof"] == "dome":
            rows.append({
                "game_id": g["game_id"], "week": int(g["week"]), "home_team": g["home_team"], "away_team": g["away_team"],
                "stadium": g["stadium"], "roof": info["roof"], "kickoff_utc": g["kickoff_utc"].isoformat(),
                "temp_f": None, "wind_mph": None, "wind_gust_mph": None, "wind_dir_deg": None, "precip_pct": None,
            })
    return pd.DataFrame(rows)


def main() -> None:
    mlb = build_mlb()
    MLB_OUT.parent.mkdir(parents=True, exist_ok=True)
    if not mlb.empty:
        mlb.to_parquet(MLB_OUT, index=False)
        print(f"{len(mlb)} upcoming MLB game(s) -> {MLB_OUT}")
    else:
        print("No upcoming (not-yet-started) MLB games right now -- leaving any existing file untouched")

    nfl = build_nfl()
    NFL_OUT.parent.mkdir(parents=True, exist_ok=True)
    if not nfl.empty:
        nfl.to_parquet(NFL_OUT, index=False)
        print(f"{len(nfl)} upcoming NFL game(s) -> {NFL_OUT}")
    else:
        print("No upcoming (not-yet-started) NFL games right now -- leaving any existing file untouched")


if __name__ == "__main__":
    main()
